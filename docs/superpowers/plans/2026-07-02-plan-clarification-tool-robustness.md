# Plan Clarification Tool Robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve `ask_plan_clarification` model-call success rate for common form payload drift without weakening the strict frontend card contract.

**Architecture:** Keep `PlanClarificationCard` and `PlanClarificationField` strict. Add lenient input normalization only at the tool boundary in `src/swe/agents/tools/planning.py`, then emit the existing canonical card shape. Cover the exact observed model payload and adjacent drift cases with focused unit tests.

**Tech Stack:** Python 3.12, Pydantic v2, AgentScope `Toolkit`, pytest.

---

## Scope And Impact

GitNexus impact analysis was run on the intended edit symbols on branch `subagent-mvp`:

- `_normalize_form_field`: LOW risk, 2 direct callers, 0 affected indexed execution flows.
- `_looks_like_form_field`: LOW risk, 1 direct caller, 0 affected indexed execution flows.
- `ask_plan_clarification`: LOW risk, 0 direct upstream callers in the index.

Do not modify `src/swe/app/plans/models.py`. The domain model should remain strict so malformed cards cannot leak to Console.

## File Structure

- Modify `src/swe/agents/tools/planning.py`
  - Add a Pydantic input model for form field tool schema guidance.
  - Add small normalization helpers for text aliases, field path error messages, nested JSON string options, and dict/model coercion.
  - Update `_looks_like_form_field()` and `_normalize_form_field()`.
  - Update `ask_plan_clarification()` signature/docstring so tool schema guides the model better.
- Modify `tests/unit/agents/tools/test_planning.py`
  - Add regression tests for name-only fields, options-as-fields detection, nested JSON string field options, schema guidance, and indexed error messages.
- Modify `analysis/playbook/common-errors.md`
  - Record this failure pattern and the new expected normalization behavior.

### Task 1: Add Failing Regression Tests

**Files:**
- Modify: `tests/unit/agents/tools/test_planning.py`
- Verify: `venv/bin/python -m pytest tests/unit/agents/tools/test_planning.py -q`

- [x] **Step 1: Add a test for the exact observed payload**

Add this test after `test_ask_plan_clarification_accepts_string_fields`:

```python
@pytest.mark.asyncio
async def test_ask_plan_clarification_accepts_name_only_form_fields() -> None:
    response = await ask_plan_clarification(
        prompt="为了给您定制最落地的维护策略，我们需要先对齐几个关键背景。",
        kind="form",
        fields=(
            '[{"name": "机构类型", "description": "您所在的金融机构类型", '
            '"options": ["银行", "券商", "三方财富", "保险", "其他"]}, '
            '{"name": "客户规模", "description": "您目前维护的 100w AUM 客户数量", '
            '"options": ["100户以内", "100-150户", "150-200户", "200户以上"]}, '
            '{"name": "核心痛点", "description": "您目前面临的最大挑战", '
            '"options": ["客户流失/被竞品挖角", "AUM 增长遇到瓶颈", '
            '"日常维护时间不够用", "合规与适当性压力", "产品同质化严重"]}]'
        ),
    )

    card = response.metadata["plan_interaction_card"]
    assert card["kind"] == "form"
    assert card["fields"][0] == {
        "id": "机构类型",
        "label": "机构类型",
        "type": "single_choice",
        "options": [
            {"id": "银行", "label": "银行"},
            {"id": "券商", "label": "券商"},
            {"id": "三方财富", "label": "三方财富"},
            {"id": "保险", "label": "保险"},
            {"id": "其他", "label": "其他"},
        ],
        "required": False,
        "description": "您所在的金融机构类型",
    }
```

- [x] **Step 2: Add a test for form fields passed through `options` without `label` or `type`**

```python
@pytest.mark.asyncio
async def test_ask_plan_clarification_detects_name_only_form_fields_in_options() -> None:
    response = await ask_plan_clarification(
        prompt="请补充背景。",
        kind="form",
        options=[
            {
                "name": "机构类型",
                "description": "您所在的金融机构类型",
                "options": ["银行", "券商"],
            },
            {
                "name": "核心痛点",
                "options": "[\"客户流失\", \"维护时间不够\"]",
            },
        ],
    )

    card = response.metadata["plan_interaction_card"]
    assert card["kind"] == "form"
    assert card["fields"][0]["label"] == "机构类型"
    assert card["fields"][0]["type"] == "single_choice"
    assert card["fields"][1]["options"] == [
        {"id": "客户流失", "label": "客户流失"},
        {"id": "维护时间不够", "label": "维护时间不够"},
    ]
```

- [x] **Step 3: Add a test for indexed field error messages**

```python
@pytest.mark.asyncio
async def test_ask_plan_clarification_reports_indexed_field_id_errors() -> None:
    with pytest.raises(
        ValueError,
        match=r"clarification fields\[0\] id is required; provide id, key, name, label, or title",
    ):
        await ask_plan_clarification(
            prompt="请补充背景。",
            kind="form",
            fields=[{"description": "缺少字段名"}],
        )
```

- [x] **Step 4: Update schema guidance test**

Extend `test_ask_plan_clarification_tool_schema_guides_choice_kind`:

```python
    defs = schema["function"]["parameters"]["$defs"]
    field_schema = defs["PlanClarificationFormFieldInput"]
    assert "name" in field_schema["properties"]
    assert "label" in field_schema["properties"]
    assert "options" in field_schema["properties"]
    assert properties["fields"]["anyOf"][0]["items"] == {
        "$ref": "#/$defs/PlanClarificationFormFieldInput",
    }
```

- [x] **Step 5: Run tests and confirm they fail for the expected reason**

Run:

```bash
venv/bin/python -m pytest tests/unit/agents/tools/test_planning.py -q
```

Expected before implementation:

- The name-only field test fails with `clarification field label is required`.
- The schema guidance extension fails because `fields.items` is still an unstructured object.

### Task 2: Implement Lenient Field Normalization

**Files:**
- Modify: `src/swe/agents/tools/planning.py`
- Test: `tests/unit/agents/tools/test_planning.py`

- [x] **Step 1: Add schema input model and constants**

Add imports:

```python
from pydantic import BaseModel, ConfigDict, Field
```

Add after `_SUPPORTED_FORM_FIELD_TYPES`:

```python
_FORM_FIELD_ID_KEYS = ("id", "key", "name", "label", "title")
_FORM_FIELD_LABEL_KEYS = ("label", "title", "name", "key", "id")
_FORM_FIELD_HINT_KEYS = frozenset(
    {"description", "label", "options", "placeholder", "required", "title", "type"},
)


class PlanClarificationFormFieldInput(BaseModel):
    """Lenient tool input shape for model-generated clarification form fields."""

    model_config = ConfigDict(extra="allow")

    id: str | None = Field(default=None, description="Stable field id.")
    key: str | None = Field(default=None, description="Field key alias for id.")
    name: str | None = Field(
        default=None,
        description="Field name. If label is omitted, this is used as the visible label.",
    )
    label: str | None = Field(default=None, description="Visible field label.")
    title: str | None = Field(default=None, description="Visible field title alias.")
    type: Literal["single_choice", "multi_choice", "text"] | None = Field(
        default=None,
        description="Control type. Omit it to infer from options.",
    )
    options: list[Any] | str | None = Field(
        default=None,
        description="Choice options as an array or a JSON string array.",
    )
    placeholder: str | None = Field(default=None, description="Text input placeholder.")
    required: bool | None = Field(default=None, description="Whether the field is required.")
    description: str | None = Field(default=None, description="Short help text.")
```

- [x] **Step 2: Add helper functions**

Add before `_looks_like_form_field()`:

```python
def _field_error_path(index: int | None, suffix: str) -> str:
    if index is None:
        return f"field {suffix}"
    return f"fields[{index}] {suffix}"


def _first_non_empty_text(data: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _coerce_form_field_object(field: Any, index: int | None = None) -> dict[str, Any]:
    if isinstance(field, BaseModel):
        field = field.model_dump(exclude_none=True)
    if not isinstance(field, dict):
        raise ValueError(
            f"clarification {_field_error_path(index, 'must be an object')}",
        )
    return field
```

- [x] **Step 3: Update form field detection**

Replace `_looks_like_form_field()` with:

```python
def _looks_like_form_field(option: Any) -> bool:
    """根据常见字段约定判断 options 是否实际承载表单字段定义。"""
    if isinstance(option, BaseModel):
        option = option.model_dump(exclude_none=True)
    if not isinstance(option, dict):
        return False

    has_stable_name = any(
        isinstance(option.get(key), str) and option[key].strip()
        for key in ("id", "key", "name")
    )
    has_label_with_type = (
        any(
            isinstance(option.get(key), str) and option[key].strip()
            for key in ("label", "title")
        )
        and isinstance(option.get("type"), str)
        and option["type"].strip()
    )
    has_field_hint = any(key in option for key in _FORM_FIELD_HINT_KEYS)
    return (has_stable_name and has_field_hint) or has_label_with_type
```

- [x] **Step 4: Update form field normalization**

Change the signature:

```python
def _normalize_form_field(
    field: dict[str, Any] | PlanClarificationFormFieldInput,
    index: int | None = None,
) -> dict[str, Any]:
```

At the top of the function, add:

```python
    field = _coerce_form_field_object(field, index)
```

Replace `field_id` and `label` handling with:

```python
    field_id = _first_non_empty_text(field, _FORM_FIELD_ID_KEYS)
    if field_id is None:
        raise ValueError(
            f"clarification {_field_error_path(index, 'id is required; provide id, key, name, label, or title')}",
        )

    label = _first_non_empty_text(field, _FORM_FIELD_LABEL_KEYS)
    if label is None:
        raise ValueError(
            f"clarification {_field_error_path(index, 'label is required; provide label or name')}",
        )
```

Replace choice options handling with:

```python
    if normalized_type in {"single_choice", "multi_choice"}:
        raw_options = _coerce_json_array(
            field.get("options"),
            "fields[].options" if index is None else f"fields[{index}].options",
        )
        if not raw_options:
            raise ValueError(
                f"clarification {_field_error_path(index, f'{field_id} requires options')}",
            )
        normalized["options"] = [
            _normalize_choice_option(option) for option in raw_options
        ]
```

- [x] **Step 5: Preserve indexed errors in list normalization**

Replace the body of `_normalize_form_fields()` after `fields = _coerce_json_array(...)` with:

```python
    return [
        _normalize_form_field(field, index)
        for index, field in enumerate(fields)
    ]
```

### Task 3: Improve Tool Schema And Prompt Guidance

**Files:**
- Modify: `src/swe/agents/tools/planning.py`
- Test: `tests/unit/agents/tools/test_planning.py`

- [x] **Step 1: Change the `fields` annotation**

Update `ask_plan_clarification()`:

```python
    fields: list[PlanClarificationFormFieldInput] | str | None = None,
```

- [x] **Step 2: Expand the function docstring with a concrete form example**

Replace the one-line docstring with:

```python
    """生成计划澄清卡片，让前端用结构化控件收集下一轮回复。

    Form example:
    fields=[
        {
            "name": "机构类型",
            "label": "机构类型",
            "type": "single_choice",
            "options": ["银行", "券商"],
            "description": "您所在的金融机构类型",
        }
    ]
    """
```

- [x] **Step 3: Run schema test**

Run:

```bash
venv/bin/python -m pytest tests/unit/agents/tools/test_planning.py::test_ask_plan_clarification_tool_schema_guides_choice_kind -q
```

Expected: PASS and `fields.items` references `PlanClarificationFormFieldInput`.

### Task 4: Update Playbook

**Files:**
- Modify: `analysis/playbook/common-errors.md`

- [x] **Step 1: Add the new failure pattern under the existing `ask_plan_clarification` section**

Add to symptoms:

```markdown
- 模型把表单字段写成 `{"name": "机构类型", "description": "...", "options": [...]}`，没有提供 `label`，后端报 `clarification field label is required`
```

Add to typical causes:

```markdown
- 部分模型会把 `name` 同时当字段标识和展示标签使用，而工具入口只把 `name` 当 `id` 兜底
- 字段内部的 `options` 也可能被再次序列化为 JSON 字符串
```

Add to first-stage handling:

```markdown
- 表单字段展示名按 `label/title/name/key/id` 顺序兜底，字段标识按 `id/key/name/label/title` 顺序兜底
- 只有工具入口做宽松归一化，`PlanClarificationCard` 和 `PlanClarificationField` 继续保持严格协议
- 错误信息需要带 `fields[index]`，便于从工具调用日志直接定位失败字段
```

### Task 5: Verification

**Files:**
- Verify only; no additional source files.

- [x] **Step 1: Run focused tests**

```bash
venv/bin/python -m pytest tests/unit/agents/tools/test_planning.py -q
```

Expected:

```text
all tests passed
```

- [x] **Step 2: Run the exact observed payload manually**

```bash
venv/bin/python -c 'import asyncio; from swe.agents.tools.planning import ask_plan_clarification; fields = "[{\"name\": \"机构类型\", \"description\": \"您所在的金融机构类型\", \"options\": [\"银行\", \"券商\", \"三方财富\", \"保险\", \"其他\"]}]"; response = asyncio.run(ask_plan_clarification(prompt="p", kind="form", fields=fields)); print(response.metadata["plan_interaction_card"]["fields"][0])'
```

Expected output includes:

```text
'id': '机构类型'
'label': '机构类型'
'type': 'single_choice'
```

- [x] **Step 3: Run GitNexus change detection**

Use MCP:

```text
mcp__gitnexus.detect_changes(repo="CoPaw", branch="subagent-mvp", scope="all")
```

Expected:

- Changed symbols limited to `src/swe/agents/tools/planning.py`, `tests/unit/agents/tools/test_planning.py`, and `analysis/playbook/common-errors.md`.
- Risk remains LOW or otherwise explicitly reviewed before continuing.

## Non-Goals

- Do not add type aliases like `radio`, `select`, or `checkbox` in this change. That was item 4 and is intentionally out of scope.
- Do not relax `PlanClarificationCard` or `PlanClarificationField`.
- Do not change Console rendering logic.
