# -*- coding: utf-8 -*-
"""Static validation for source-owned Python tool scripts.

The validator deliberately parses source with :mod:`ast` only.  An upload is
never imported, evaluated, or otherwise executed in the management process.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from typing import Any

from swe.envs.runtime import PROTECTED_RUNTIME_ENV_KEYS, validate_env_key

MAX_SOURCE_TOOL_BYTES = 1024 * 1024
TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_CONTRACT_ASSIGNMENTS = {
    "TOOL_NAME",
    "TOOL_DESCRIPTION",
    "TOOL_JSON_SCHEMA",
    "REQUIRED_ENV",
}
_STANDARD_LIBRARY_MODULES = frozenset(sys.stdlib_module_names) | {
    "__future__",
}


class SourceToolValidationError(ValueError):
    """Raised when a source tool does not meet the static upload contract."""


@dataclass(frozen=True)
class SourceToolContract:
    """Metadata extracted from a statically-valid source-tool script."""

    name: str
    description: str
    json_schema: dict[str, Any]
    required_env: tuple[str, ...]


def validate_source_tool_script(content: bytes) -> SourceToolContract:
    """Validate and parse the source-tool upload contract without execution."""
    if len(content) > MAX_SOURCE_TOOL_BYTES:
        raise SourceToolValidationError("script exceeds the 1 MiB limit")
    if b"\x00" in content:
        raise SourceToolValidationError("script content must be UTF-8 text")
    try:
        source = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceToolValidationError(
            "script content must be UTF-8 text",
        ) from exc
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        raise SourceToolValidationError(
            f"script has invalid Python syntax: {exc.msg}",
        ) from exc

    assignments: dict[str, Any] = {}
    entrypoint: ast.AsyncFunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            _validate_import(node)
        if _is_dynamic_import(node):
            raise SourceToolValidationError(
                "dynamic imports are not allowed in source tools",
            )

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.Assign):
            _collect_literal_assignment(node, assignments)
            continue
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "execute":
            if entrypoint is not None:
                raise SourceToolValidationError(
                    "only one execute entry is allowed",
                )
            entrypoint = node

    missing = sorted(_CONTRACT_ASSIGNMENTS - assignments.keys())
    if missing:
        raise SourceToolValidationError(
            "missing static literal contract fields: " + ", ".join(missing),
        )
    _validate_entrypoint(entrypoint)
    return SourceToolContract(
        name=_validate_tool_name(assignments["TOOL_NAME"]),
        description=_validate_description(assignments["TOOL_DESCRIPTION"]),
        json_schema=_validate_json_schema(assignments["TOOL_JSON_SCHEMA"]),
        required_env=_validate_required_env(assignments["REQUIRED_ENV"]),
    )


def _validate_import(node: ast.Import | ast.ImportFrom) -> None:
    modules = (
        (alias.name for alias in node.names)
        if isinstance(node, ast.Import)
        else (node.module or "",)
    )
    for module in modules:
        root = module.split(".", 1)[0]
        if root not in _STANDARD_LIBRARY_MODULES:
            raise SourceToolValidationError(
                f"imports must use the Python standard library only: {module}",
            )


def _is_dynamic_import(node: ast.AST) -> bool:
    """Reject runtime import primitives that could bypass static inspection."""
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Name):
        return node.func.id == "__import__"
    return (
        isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "importlib"
        and node.func.attr in {"import_module", "reload"}
    )


def _collect_literal_assignment(
    node: ast.Assign,
    assignments: dict[str, Any],
) -> None:
    if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
        return
    field = node.targets[0].id
    if field not in _CONTRACT_ASSIGNMENTS:
        return
    if field in assignments:
        raise SourceToolValidationError(
            f"{field} must be declared once as a literal",
        )
    try:
        assignments[field] = ast.literal_eval(node.value)
    except (ValueError, TypeError) as exc:
        raise SourceToolValidationError(
            f"{field} must be a static literal",
        ) from exc


def _validate_entrypoint(entrypoint: ast.AsyncFunctionDef | None) -> None:
    if entrypoint is None:
        raise SourceToolValidationError(
            "script must define async def execute(arguments, context)",
        )
    args = entrypoint.args
    names = [argument.arg for argument in args.args]
    invalid_signature_shape = any(
        (
            args.posonlyargs,
            args.vararg is not None,
            args.kwonlyargs,
            args.kwarg is not None,
            args.defaults,
            args.kw_defaults,
        ),
    )
    if names != ["arguments", "context"] or invalid_signature_shape:
        raise SourceToolValidationError(
            "execute signature must be async def execute(arguments, context)",
        )


def _validate_tool_name(value: Any) -> str:
    if not isinstance(value, str) or not TOOL_NAME_PATTERN.fullmatch(value):
        raise SourceToolValidationError(
            "TOOL_NAME must be a valid restricted identifier",
        )
    return value


def _validate_description(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceToolValidationError(
            "TOOL_DESCRIPTION must be a non-empty literal string",
        )
    return value


def _validate_json_schema(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SourceToolValidationError(
            "TOOL_JSON_SCHEMA must be an object literal",
        )
    if value.get("type") != "object":
        raise SourceToolValidationError(
            "TOOL_JSON_SCHEMA must describe an object",
        )
    return value


def _validate_required_env(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise SourceToolValidationError(
            "REQUIRED_ENV must be a literal list of environment names",
        )
    if len(value) != len(set(value)):
        raise SourceToolValidationError("REQUIRED_ENV entries must be unique")
    normalized: list[str] = []
    for key in value:
        try:
            normalized_key = validate_env_key(key)
        except ValueError as exc:
            raise SourceToolValidationError(str(exc).lower()) from exc
        if normalized_key in PROTECTED_RUNTIME_ENV_KEYS:
            raise SourceToolValidationError(
                f"protected environment key is not allowed: {normalized_key}",
            )
        normalized.append(normalized_key)
    return tuple(normalized)
