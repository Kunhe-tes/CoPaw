"""Privacy checks shared by the W+ SOP tooling."""

from __future__ import annotations

import re
from typing import Any, Iterable


SENSITIVE_KEY_NAMES = {
    "account",
    "accountnumber",
    "cardnbr",
    "cardnumber",
    "crdnbr",
    "custuid",
    "customerid",
    "customername",
    "客户uid",
    "客户号",
    "客户姓名",
    "卡号",
    "账号",
}

VALUE_PATTERNS = [
    ("customer UID", re.compile(r"\bPNCIF[0-9A-Za-z]{6,}\b", re.IGNORECASE)),
    ("user-specific absolute path", re.compile(r"(?:[A-Za-z]:\\Users\\|/Users/)", re.IGNORECASE)),
    ("long account-like number", re.compile(r"(?<!\d)\d{12,19}(?!\d)")),
    ("encrypted or base64-like value", re.compile(r"\b[A-Za-z0-9+/]{36,}={0,2}\b")),
]


def iter_values(value: Any, path: str = "$") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from iter_values(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_values(child, f"{path}[{index}]")
    else:
        yield path, value


def sensitive_value_findings(value: Any, path: str = "$") -> list[str]:
    findings: list[str] = []
    for item_path, item in iter_values(value, path):
        if not isinstance(item, str):
            continue
        for label, pattern in VALUE_PATTERNS:
            if pattern.search(item):
                findings.append(f"{item_path}: sensitive {label}")
    return findings


def sensitive_key_findings(value: Any, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(key).casefold())
            if normalized in SENSITIVE_KEY_NAMES:
                findings.append(f"{path}.{key}: sensitive key is not allowed")
            findings.extend(sensitive_key_findings(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(sensitive_key_findings(child, f"{path}[{index}]"))
    return findings
