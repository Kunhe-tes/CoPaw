# -*- coding: utf-8 -*-
import pytest

from swe.app.source_tools.validation import (
    SourceToolValidationError,
    validate_source_tool_script,
)

VALID_SCRIPT = """
TOOL_NAME = "lookup_invoice"
TOOL_DESCRIPTION = "Look up an invoice in the tenant system."
TOOL_JSON_SCHEMA = {
    "type": "object",
    "properties": {"invoice_id": {"type": "string"}},
    "required": ["invoice_id"],
}
REQUIRED_ENV = ["INVOICE_API_TOKEN"]

async def execute(arguments, context):
    return {"invoice_id": arguments["invoice_id"], "tenant": context["tenant_id"]}
"""


def test_accepts_static_source_tool_contract():
    contract = validate_source_tool_script(VALID_SCRIPT.encode())

    assert contract.name == "lookup_invoice"
    assert contract.required_env == ("INVOICE_API_TOKEN",)
    assert contract.json_schema["required"] == ["invoice_id"]


@pytest.mark.parametrize(
    "script, message",
    [
        (
            VALID_SCRIPT.replace(
                'TOOL_NAME = "lookup_invoice"',
                "TOOL_NAME = name",
            ),
            "literal",
        ),
        (
            VALID_SCRIPT.replace(
                "async def execute(arguments, context):",
                "def execute(arguments, context):",
            ),
            "async",
        ),
        (
            VALID_SCRIPT.replace(
                'REQUIRED_ENV = ["INVOICE_API_TOKEN"]',
                'REQUIRED_ENV = ["HOME"]',
            ),
            "protected",
        ),
        (
            VALID_SCRIPT.replace(
                'TOOL_NAME = "lookup_invoice"',
                'TOOL_NAME = "bad-name"',
            ),
            "identifier",
        ),
        (
            VALID_SCRIPT.replace(
                "async def execute(arguments, context):",
                "async def execute(payload, context):",
            ),
            "signature",
        ),
        (
            VALID_SCRIPT.replace(
                "async def execute(arguments, context):",
                "async def execute(arguments, context):\n    import made_up_dependency",
            ),
            "imports",
        ),
    ],
)
def test_rejects_non_static_or_unsafe_contract(script, message):
    with pytest.raises(SourceToolValidationError, match=message):
        validate_source_tool_script(script.encode())


def test_rejects_non_utf8_and_oversize():
    with pytest.raises(SourceToolValidationError, match="UTF-8"):
        validate_source_tool_script(b"\xff")

    with pytest.raises(SourceToolValidationError, match="1 MiB"):
        validate_source_tool_script(b"x" * (1024 * 1024 + 1))


def test_rejects_duplicate_required_environment_keys():
    script = VALID_SCRIPT.replace(
        '["INVOICE_API_TOKEN"]',
        '["INVOICE_API_TOKEN", "INVOICE_API_TOKEN"]',
    )

    with pytest.raises(SourceToolValidationError, match="unique"):
        validate_source_tool_script(script.encode())


def test_rejects_dynamic_imports_even_when_importlib_is_standard_library():
    script = VALID_SCRIPT.replace(
        'return {"invoice_id": arguments["invoice_id"], "tenant": context["tenant_id"]}',
        'return __import__("external_package")',
    )

    with pytest.raises(SourceToolValidationError, match="dynamic imports"):
        validate_source_tool_script(script.encode())
