# Skill / MCP 版本控制重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把市场侧 skill / MCP 的版本控制规则（R1-R8）落地到代码：名称硬唯一+版本续接、用户与市场版本隔离、新增 source_user_* 快照字段、MCP 引入与 skill 对称的快照系统、收敛重复实现。

**Architecture:** 全部改动限定在 `market/` 子目录。新增两个共享工具模块（`utils/skill_md.py`、`utils/version.py`），重构 `version_service.py` 与 `service.py` 中的同名续接与快照创建逻辑，新增平行的 `mcp_version_service.py`。前端仅在 T14 隐藏一个按钮。swe 服务不动。

**Tech Stack:** Python 3.11、FastAPI、Pydantic v2、python-frontmatter、pytest。

**Spec:** `docs/superpowers/specs/2026-06-13-skill-mcp-version-control-design.md`

---

## File Structure

### 新增文件

| 路径 | 责任 |
|---|---|
| `market/src/market/utils/__init__.py` | 工具包入口（如果尚未存在则创建） |
| `market/src/market/utils/skill_md.py` | 统一的 SKILL.md frontmatter 解析（基于 `python-frontmatter`），导出 `parse_frontmatter` / `extract_version` / `extract_metadata` |
| `market/src/market/utils/version.py` | 版本号工具：`bump_patch` / `normalize_version` |
| `market/src/market/marketplace/mcp_version_service.py` | MCP 版本快照服务，与 `SkillVersionService` 对称 |
| `market/src/market/app/routers/mcp_versions.py` | MCP 版本浏览 / 切换 / 比对 / 删除 API |
| `market/tests/unit/utils/__init__.py` | 测试包入口 |
| `market/tests/unit/utils/test_skill_md.py` | `skill_md.py` 单元测试 |
| `market/tests/unit/utils/test_version.py` | `version.py` 单元测试 |
| `market/tests/unit/marketplace/test_mcp_version_service.py` | MCP 版本服务单元测试 |

### 修改文件

| 路径 | 修改点 |
|---|---|
| `market/src/market/marketplace/version_models.py` | `SkillVersion` 增 3 字段；新增 `MCPVersion` / `MCPVersionsManifest` |
| `market/src/market/marketplace/version_service.py` | `create_version_snapshot` 签名扩展；R7 修复（同版本同内容不翻 is_current）；移除局部 frontmatter/bump 实现，改用 utils |
| `market/src/market/marketplace/service.py` | `_upsert_skill_item` 改按 name 续接；`publish_mcp` 接入快照与续接；移除 `SkillNameConflictError` / `MCPNameConflictError` 同名拒绝分支；移除局部 frontmatter/bump 实现 |
| `market/src/market/marketplace/schemas.py` | `MyMCPDetail` 新增 `version_changed` / `previous_version` / `bump_reason` 三字段（用于 update_my_mcp 响应） |
| `market/src/market/app/routers/skill_versions.py` | `_update_skill_index` 切版本时同步 `MarketItem.creator_id/creator_name`（R8）；移除局部 frontmatter 解析改用 utils |
| `market/src/market/app/routers/skills_market.py` | 移除局部 `_parse_frontmatter` / `_bump_patch` 引用；`publish_skill_upload` 透传 `source_user_*` 与 `created_by`；废除"建议改名"分支 |
| `market/src/market/app/routers/skills_browse.py` | 移除局部 `_parse_frontmatter_version` / `_bump_patch_version` 引用 |
| `market/src/market/app/routers/my_mcp.py` | 移除局部 `_bump_patch`；`update_my_mcp` 改"显式 > 内容变才递增"语义；`_publish_client_to_market` 透传 `source_user_*` |
| `market/src/market/app/routers/mcp_market.py` | `upload_mcp` 透传 `source_user_id=""` / `source_user_version="v0.0.0"` |
| `market/src/market/app/main.py`（或 router 注册位置） | 注册新增的 `mcp_versions` router |
| `console/src/pages/.../my-skills/...`（位置由 T14 子任务确定） | 隐藏 `source=marketplace:*` 的 skill 的"同步到市场"按钮 |

### 测试文件

| 路径 | 用途 |
|---|---|
| `market/tests/unit/marketplace/test_version_service.py`（已有） | 增 R7 / R8 / source_user_* 字段相关用例 |
| `market/tests/unit/marketplace/test_service.py`（已有） | 增 skill / MCP 同名续接测试 |
| `market/tests/unit/marketplace/test_skills_market.py`（已有） | 增 publish-upload 续接测试 |
| `market/tests/unit/test_my_mcp.py`（已有，路径以实际为准） | 增 update_my_mcp 不变内容不 bump 的测试 |

---

## Conventions

* **Python 版本**：所有代码使用 type hints；新增模块顶部加 `# -*- coding: utf-8 -*-` 与 `from __future__ import annotations`，与现有市场代码一致。
* **测试运行**：`cd D:/smile_code/github/CoPaw && venv_market/Scripts/python -m pytest market/tests/unit/<path> -v`（Windows 下 venv_market 是市场服务的 venv）。如果 venv 路径不同，调整为 `python -m pytest`。
* **提交风格**：参考最近 commit `b9bd1632 fix: 我的技能保存时无变化不更新版本`，emoji + 中文 subject + 英文/中文 body 均可；每个 task 末尾一次提交。

---

### Task 1: 共享工具包初始化（utils/skill_md.py + utils/version.py）

**Files:**
- Create: `market/src/market/utils/skill_md.py`
- Create: `market/src/market/utils/version.py`
- Create: `market/tests/unit/utils/__init__.py`
- Create: `market/tests/unit/utils/test_skill_md.py`
- Create: `market/tests/unit/utils/test_version.py`
- Verify exists: `market/src/market/utils/__init__.py`（已存在，无需修改）

- [ ] **Step 1: 写 utils/version.py 的失败测试**

创建 `market/tests/unit/utils/__init__.py` 为空文件。

创建 `market/tests/unit/utils/test_version.py`：

```python
# -*- coding: utf-8 -*-
"""版本号工具单元测试."""

from __future__ import annotations

import pytest

from market.utils.version import bump_patch, normalize_version


class TestBumpPatch:
    def test_three_part(self):
        assert bump_patch("1.0.0") == "1.0.1"
        assert bump_patch("1.0.8") == "1.0.9"
        assert bump_patch("2.13.99") == "2.13.100"

    def test_two_part(self):
        # 1.5 → 1.5.1（与 service.py 现行 _bump_patch 行为一致）
        assert bump_patch("1.5") == "1.5.1"

    def test_invalid_format_appends_one(self):
        assert bump_patch("foo") == "foo.1"
        assert bump_patch("1.a.0") == "1.a.0.1"

    def test_empty_string(self):
        assert bump_patch("") == ".1"


class TestNormalizeVersion:
    def test_strip_v_prefix(self):
        assert normalize_version("v1.0.0") == "1.0.0"
        assert normalize_version("V2.3.4") == "2.3.4"

    def test_strip_quotes(self):
        assert normalize_version('"1.2.3"') == "1.2.3"
        assert normalize_version("'1.2.3'") == "1.2.3"

    def test_strip_quotes_and_v(self):
        assert normalize_version('"v1.2.3"') == "1.2.3"

    def test_strip_whitespace(self):
        assert normalize_version("  1.0.0  ") == "1.0.0"

    def test_empty(self):
        assert normalize_version("") == ""
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd D:/smile_code/github/CoPaw && python -m pytest market/tests/unit/utils/test_version.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'market.utils.version'`

- [ ] **Step 3: 实现 utils/version.py**

创建 `market/src/market/utils/version.py`：

```python
# -*- coding: utf-8 -*-
"""版本号操作工具.

统一替代散落在 service.py / version_service.py / skills_browse.py / my_mcp.py
的多个 _bump_patch 实现。
"""

from __future__ import annotations


def bump_patch(version: str) -> str:
    """递增版本号的 patch 部分.

    1.0.0 → 1.0.1
    1.0.8 → 1.0.9
    1.5   → 1.5.1（两段式补 .1，沿用 service.py 现行行为）
    其他无法解析格式 → '<version>.1'
    """
    parts = version.split(".")
    if len(parts) == 3:
        try:
            parts[2] = str(int(parts[2]) + 1)
            return ".".join(parts)
        except ValueError:
            pass
    return f"{version}.1"


def normalize_version(version: str) -> str:
    """去除前导 v/V 与引号、空白."""
    if not version:
        return ""
    val = version.strip()
    if (val.startswith('"') and val.endswith('"')) or (
        val.startswith("'") and val.endswith("'")
    ):
        val = val[1:-1]
    if val[:1] in ("v", "V"):
        val = val[1:]
    return val
```

> 注意：本工具与 `service.py:215-224` 的 `_bump_patch` 行为完全一致（两段式 `1.5` → `1.5.1`，不做 `1.6.0` 的 minor bump）。`version_service.py:707-730` 的 `_bump_version` 与 `skills_browse.py:386-402` 的 `_bump_patch_version` 中处理两段式时的"minor +1 补 .0"分支被舍弃，统一行为见 spec §7。

- [ ] **Step 4: 运行 utils/version.py 测试确认通过**

Run: `python -m pytest market/tests/unit/utils/test_version.py -v`

Expected: PASS（13 个用例）

- [ ] **Step 5: 写 utils/skill_md.py 的失败测试**

创建 `market/tests/unit/utils/test_skill_md.py`：

```python
# -*- coding: utf-8 -*-
"""SKILL.md frontmatter 工具单元测试."""

from __future__ import annotations

from market.utils.skill_md import (
    extract_metadata,
    extract_version,
    parse_frontmatter,
)


SAMPLE_MD = """---
name: 测试技能
description: 一个测试用的技能
version: "1.2.3"
chinese_name: 测试
---

# 测试技能

正文内容。
"""

SAMPLE_MD_NO_VERSION = """---
name: no_version_skill
description: ""
---

正文。
"""

SAMPLE_MD_V_PREFIX = """---
name: prefix_skill
version: v2.0.0
---

正文。
"""


class TestParseFrontmatter:
    def test_basic(self):
        fm = parse_frontmatter(SAMPLE_MD)
        assert fm["name"] == "测试技能"
        assert fm["description"] == "一个测试用的技能"
        assert fm["version"] == "1.2.3"
        assert fm["chinese_name"] == "测试"

    def test_no_frontmatter(self):
        fm = parse_frontmatter("# Just a heading\n\nNo fm.")
        assert fm == {}

    def test_empty_input(self):
        assert parse_frontmatter("") == {}


class TestExtractVersion:
    def test_quoted(self):
        assert extract_version(SAMPLE_MD) == "1.2.3"

    def test_no_version(self):
        assert extract_version(SAMPLE_MD_NO_VERSION) == ""

    def test_v_prefix(self):
        assert extract_version(SAMPLE_MD_V_PREFIX) == "2.0.0"

    def test_no_frontmatter(self):
        assert extract_version("plain text") == ""

    def test_empty_input(self):
        assert extract_version("") == ""


class TestExtractMetadata:
    def test_returns_known_keys(self):
        meta = extract_metadata(SAMPLE_MD)
        assert meta["name"] == "测试技能"
        assert meta["description"] == "一个测试用的技能"
        assert meta["version"] == "1.2.3"
        assert meta["chinese_name"] == "测试"

    def test_missing_keys_return_empty_string(self):
        meta = extract_metadata(SAMPLE_MD_NO_VERSION)
        assert meta["name"] == "no_version_skill"
        assert meta["description"] == ""
        assert meta["version"] == ""
        assert meta["chinese_name"] == ""
```

- [ ] **Step 6: 运行测试确认失败**

Run: `python -m pytest market/tests/unit/utils/test_skill_md.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'market.utils.skill_md'`

- [ ] **Step 7: 实现 utils/skill_md.py**

创建 `market/src/market/utils/skill_md.py`：

```python
# -*- coding: utf-8 -*-
"""SKILL.md frontmatter 解析工具.

统一替代散落在 service.py / version_service.py / skills_market.py /
skills_browse.py / skill_versions.py 的多个手写 line parser。

实现基于 python-frontmatter 包，与 swe 侧 skills_manager.py 保持一致的解析方式
（仅对 market 内部生效；swe 侧本次不改）。
"""

from __future__ import annotations

from typing import Any, Dict

import frontmatter

from .version import normalize_version


def parse_frontmatter(md_content: str) -> Dict[str, Any]:
    """解析 SKILL.md frontmatter，返回 metadata dict（无 frontmatter 时返回空 dict）."""
    if not md_content:
        return {}
    try:
        post = frontmatter.loads(md_content)
    except Exception:  # pylint: disable=broad-except
        return {}
    return dict(post.metadata or {})


def extract_version(md_content: str) -> str:
    """提取 frontmatter 中的 version 字段，去除 v 前缀与引号；不存在则返回空串."""
    fm = parse_frontmatter(md_content)
    raw = fm.get("version", "")
    if isinstance(raw, (int, float)):
        raw = str(raw)
    if not isinstance(raw, str):
        return ""
    return normalize_version(raw)


def extract_metadata(md_content: str) -> Dict[str, str]:
    """提取常用元数据字段，缺失字段返回空串.

    Returns:
        包含 name / description / version / chinese_name 的 dict。
    """
    fm = parse_frontmatter(md_content)

    def _str(key: str) -> str:
        val = fm.get(key, "")
        if isinstance(val, (int, float)):
            return str(val)
        return val if isinstance(val, str) else ""

    return {
        "name": _str("name"),
        "description": _str("description"),
        "version": extract_version(md_content),
        "chinese_name": _str("chinese_name"),
    }
```

- [ ] **Step 8: 运行 utils/skill_md.py 测试确认通过**

Run: `python -m pytest market/tests/unit/utils/test_skill_md.py -v`

Expected: PASS（11 个用例）

- [ ] **Step 9: 验证 frontmatter 包已在 market venv 中**

Run: `python -c "import frontmatter; print(frontmatter.__version__)"`

Expected: 输出版本号。如果失败：`pip install python-frontmatter`，然后将 `python-frontmatter` 加到 `market/pyproject.toml` 的 dependencies。

- [ ] **Step 10: Commit**

```bash
git add market/src/market/utils/skill_md.py market/src/market/utils/version.py market/tests/unit/utils/
git commit -m ":sparkles: feat(market/utils): 新增 skill_md / version 共享工具

- skill_md.py: 基于 python-frontmatter 的统一 frontmatter 解析与 version 提取
- version.py: 统一的 bump_patch / normalize_version
- 后续 T2 将替换市场侧 5 处 frontmatter parser + 4 处 _bump_patch 副本

Refs: docs/superpowers/specs/2026-06-13-skill-mcp-version-control-design.md §7"
```

---

### Task 2: 替换市场侧重复实现 → 共享工具

**Files:**
- Modify: `market/src/market/marketplace/version_service.py:707-767` (移除 `_bump_version`、`_extract_version_from_frontmatter[_static]`)
- Modify: `market/src/market/marketplace/service.py:215-224, 327-368` (移除 `_bump_patch`、`_parse_md_frontmatter`、`_extract_version_from_frontmatter`)
- Modify: `market/src/market/app/routers/skills_market.py:125-165, 283` (移除 `_parse_frontmatter`、不再 import `_bump_patch`)
- Modify: `market/src/market/app/routers/skills_browse.py:319-402` (移除 `_parse_frontmatter_version`、`_bump_patch_version`、`_extract_version_from_frontmatter`)
- Modify: `market/src/market/app/routers/skill_versions.py:60-97` (移除 `_parse_skill_md_frontmatter`)
- Modify: `market/src/market/app/routers/my_mcp.py:137-146` (移除 `_bump_patch`)

> **重要**：本任务只替换函数体的实现，不改变任何调用方语义。每替换一个文件先跑现有 pytest 验证不回归。

- [ ] **Step 1: 替换 version_service.py 内部实现**

修改 `market/src/market/marketplace/version_service.py`：

在文件顶部 `import` 区加：

```python
from ..utils.skill_md import extract_version as _extract_version_md
from ..utils.version import bump_patch as _shared_bump_patch
```

替换 `_bump_version` 方法（约 707-730 行）整体为：

```python
    def _bump_version(self, version: str) -> str:
        """递增版本号的 patch 部分（委托共享工具）."""
        return _shared_bump_patch(version)
```

替换 `_extract_version_from_frontmatter` 与 `_extract_version_from_frontmatter_static`（约 732-767 行）为：

```python
    def _extract_version_from_frontmatter(self, md_content: str) -> str:
        """从 SKILL.md frontmatter 中提取 version（委托共享工具）."""
        return _extract_version_md(md_content)

    @staticmethod
    def _extract_version_from_frontmatter_static(md_content: str) -> str:
        """从 SKILL.md frontmatter 中提取 version（静态方法，供外部调用）."""
        return _extract_version_md(md_content)
```

- [ ] **Step 2: 跑 version_service 现有测试确认无回归**

Run: `python -m pytest market/tests/unit/marketplace/test_version_service.py -v`

Expected: 全部已有用例 PASS。如果有失败，说明替换破坏了原行为，回退本步骤检查（重点是 `bump_patch("1.5")` 这类边界）。

- [ ] **Step 3: 替换 service.py 内部实现**

修改 `market/src/market/marketplace/service.py`：

顶部 import 区加：

```python
from ..utils.skill_md import extract_version as _extract_version_md
from ..utils.version import bump_patch as _shared_bump_patch
```

替换 `_bump_patch`（约 215-224 行）为：

```python
def _bump_patch(version: str) -> str:
    """Increment patch version: '1.0.0' -> '1.0.1'（委托共享工具）."""
    return _shared_bump_patch(version)
```

替换 `_extract_version_from_frontmatter`（约 352-367 行）为：

```python
def _extract_version_from_frontmatter(md_content: str) -> str:
    """从 SKILL.md frontmatter 中提取 version（委托共享工具）."""
    return _extract_version_md(md_content)
```

`_parse_md_frontmatter`（327-349 行，提取 name+description）保留——它返回 tuple 不在共享工具范围内；如果未来另起 task 整合可再处理。

- [ ] **Step 4: 跑 service.py 相关测试确认无回归**

Run: `python -m pytest market/tests/unit/marketplace/test_service.py -v`

Expected: 全部已有用例 PASS。

- [ ] **Step 5: 替换 skills_market.py 的引用**

修改 `market/src/market/app/routers/skills_market.py`：

* 第 283 行 `from ...marketplace.service import _bump_patch` 保留（service.py 里仍导出，已委托给共享工具，不需要再改 import）。
* 找到 `_parse_frontmatter` 函数（约 125-165 行），替换函数体为委托：

```python
def _parse_frontmatter(skill_md_content: str) -> tuple[str, str, str]:
    """从 SKILL.md frontmatter 解析 (name, description, version)."""
    from ...utils.skill_md import extract_metadata
    meta = extract_metadata(skill_md_content)
    return meta["name"], meta["description"], meta["version"]
```

如果原 `_parse_frontmatter` 返回的字段顺序或类型与上面不同，先 `Read` 该函数原始定义再调整本步骤。原函数是用于 `_parse_skill_metadata` 内部调用，需保持 tuple 结构。

- [ ] **Step 6: 跑 skills_market 相关测试**

Run: `python -m pytest market/tests/unit/marketplace/test_skills_market.py -v`

Expected: 全部已有用例 PASS。

- [ ] **Step 7: 替换 skills_browse.py 的引用**

修改 `market/src/market/app/routers/skills_browse.py`：

替换 `_parse_frontmatter_version`（约 356-383 行）函数体为：

```python
def _parse_frontmatter_version(skill_md_path: Path) -> str:
    """从 SKILL.md frontmatter 中提取 version（委托共享工具）."""
    from ...utils.skill_md import extract_version
    if not skill_md_path.exists():
        return ""
    try:
        return extract_version(skill_md_path.read_text(encoding="utf-8"))
    except OSError:
        return ""
```

替换 `_bump_patch_version`（约 386-402 行）为：

```python
def _bump_patch_version(version: str) -> str:
    """递增版本号 patch（委托共享工具）."""
    from ...utils.version import bump_patch
    return bump_patch(version)
```

如果文件里还有更早出现的 `_extract_version_from_frontmatter`（约 319-353 行），同样替换为：

```python
def _extract_version_from_frontmatter(skill_md_content: str) -> str:
    from ...utils.skill_md import extract_version
    return extract_version(skill_md_content)
```

- [ ] **Step 8: 跑 skills_browse 相关测试**

Run: `python -m pytest market/tests/unit/marketplace/test_skills_browse.py -v`

Expected: 全部已有用例 PASS。

注意：`bump_patch_version("1.5")` 此前返回 `"1.6.0"`，统一后会变为 `"1.5.1"`——与 service.py 的 `_bump_patch` 一致。如果有测试断言 `"1.6.0"`，按 spec 决议（统一行为）改测试断言为 `"1.5.1"`。

- [ ] **Step 9: 替换 skill_versions.py 的引用**

修改 `market/src/market/app/routers/skill_versions.py`：

替换 `_parse_skill_md_frontmatter`（约 60-97 行）函数体为：

```python
def _parse_skill_md_frontmatter(
    md_content: str,
    fallback_name: str,
    fallback_description: str,
) -> tuple[str, str]:
    """从 SKILL.md frontmatter 解析 (name, description)（委托共享工具）."""
    from ...utils.skill_md import extract_metadata
    meta = extract_metadata(md_content)
    name = meta["name"] or fallback_name
    description = meta["description"] or fallback_description
    return name, description
```

- [ ] **Step 10: 替换 my_mcp.py 的引用**

修改 `market/src/market/app/routers/my_mcp.py`：

替换 `_bump_patch`（约 137-146 行）为：

```python
def _bump_patch(version: str) -> str:
    """版本号 patch+1（委托共享工具）."""
    from ...utils.version import bump_patch
    return bump_patch(version)
```

- [ ] **Step 11: 跑全量市场测试**

Run: `python -m pytest market/tests/unit -v`

Expected: 全部 PASS。如果有任何用例因 `bump_patch("1.5")` 返回值变化而失败（应为 `"1.5.1"`），更新该测试断言；如果有用例因 frontmatter 解析行为差异（python-frontmatter 严格 vs 手写 line parser 宽容）失败，记录 fixture 内容并修复（通常是测试 fixture 的 YAML 格式问题）。

- [ ] **Step 12: Commit**

```bash
git add market/src/market market/tests/unit
git commit -m ":recycle: refactor(market): 收敛 frontmatter / bump_patch 多套实现到共享工具

- version_service.py / service.py / skills_market.py / skills_browse.py /
  skill_versions.py / my_mcp.py 均委托至 utils/skill_md / utils/version
- 统一 bump_patch(\"1.5\") 行为为 \"1.5.1\"（之前 skills_browse 副本返回 \"1.6.0\"）
- 行为对外保持兼容，仅 1 处边界统一

Refs: docs/superpowers/specs/2026-06-13-skill-mcp-version-control-design.md §7"
```

---

### Task 3: SkillVersion 模型扩展 + create_version_snapshot 新增 source_user_*

**Files:**
- Modify: `market/src/market/marketplace/version_models.py:12-22` (`SkillVersion` 增 3 字段)
- Modify: `market/src/market/marketplace/version_service.py:57-210` (`create_version_snapshot` 签名扩展)
- Test: `market/tests/unit/marketplace/test_version_service.py` (新增 source_user_* 用例)

- [ ] **Step 1: 写 source_user_* 字段失败测试**

在 `market/tests/unit/marketplace/test_version_service.py` 末尾追加：

```python
def test_create_snapshot_with_source_user(tmp_path):
    """创建快照时记录 source_user_* 字段."""
    svc = _make_version_service(tmp_path)
    skill_md = """---
name: t
version: "1.0.0"
---
正文
"""
    skill_dir = _create_skill_dir(tmp_path, "src1", "item1", skill_md=skill_md)

    version = svc.create_version_snapshot(
        source_id="src1",
        item_id="item1",
        skill_dir=skill_dir,
        creator="admin_id",
        creator_name="admin",
        source_user_id="alice_id",
        source_user_name="alice",
        source_user_version="1.5.2",
    )

    assert version.created_by == "admin_id"
    assert version.created_by_name == "admin"
    assert version.source_user_id == "alice_id"
    assert version.source_user_name == "alice"
    assert version.source_user_version == "1.5.2"


def test_create_snapshot_without_source_user_defaults_to_empty(tmp_path):
    """admin 直接 zip 上传场景：source_user_* 留空."""
    svc = _make_version_service(tmp_path)
    skill_md = """---
name: t
version: "1.0.0"
---
正文
"""
    skill_dir = _create_skill_dir(tmp_path, "src1", "item1", skill_md=skill_md)

    version = svc.create_version_snapshot(
        source_id="src1",
        item_id="item1",
        skill_dir=skill_dir,
        creator="admin_id",
        creator_name="admin",
    )

    assert version.source_user_id == ""
    assert version.source_user_name == ""
    assert version.source_user_version == ""


def test_old_versions_json_loads_with_default_empty_source_user(tmp_path):
    """向后兼容：旧 versions.json 没有 source_user_* 字段时读出来为空串."""
    svc = _make_version_service(tmp_path)
    versions_path = tmp_path / "market" / "src1" / "skill_versions" / "item1" / "versions.json"
    versions_path.parent.mkdir(parents=True, exist_ok=True)
    versions_path.write_text(
        json.dumps({
            "skill_name": "old",
            "versions": [{
                "version_id": "1.0.0",
                "created_at": "2025-01-01T00:00:00+00:00",
                "created_by": "u1",
                "created_by_name": "user1",
                "description": "legacy",
                "signature": "sig",
                "is_current": True,
                "is_initial": True,
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    listed = svc.list_versions("src1", "item1")
    assert listed["versions"][0]["source_user_id"] == ""
    assert listed["versions"][0]["source_user_name"] == ""
    assert listed["versions"][0]["source_user_version"] == ""
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest market/tests/unit/marketplace/test_version_service.py::test_create_snapshot_with_source_user market/tests/unit/marketplace/test_version_service.py::test_create_snapshot_without_source_user_defaults_to_empty market/tests/unit/marketplace/test_version_service.py::test_old_versions_json_loads_with_default_empty_source_user -v`

Expected: FAIL — `create_version_snapshot` 不接受 `source_user_*` 参数 / `SkillVersion` 没有这些字段。

- [ ] **Step 3: 在 version_models.py 给 SkillVersion 加 3 个字段**

修改 `market/src/market/marketplace/version_models.py:12-22`，将 `SkillVersion` 改为：

```python
class SkillVersion(BaseModel):
    """单个版本信息."""

    version_id: str
    created_at: str  # ISO8601 时间字符串
    created_by: str = ""  # 操作者（按按钮的人，admin 的 X-User-Id）
    created_by_name: str = ""  # 操作者名称
    description: str = ""
    signature: str = ""  # 内容签名（SHA256）
    is_current: bool = False
    is_initial: bool = False
    # 新增：内容来源用户。空串表示无来源（admin 走 zip 上传路径）
    source_user_id: str = ""
    source_user_name: str = ""
    source_user_version: str = ""
```

- [ ] **Step 4: 扩展 create_version_snapshot 签名**

修改 `market/src/market/marketplace/version_service.py:57-210` 的 `create_version_snapshot` 方法：

签名改为（在原参数末尾追加 3 个，全部带默认值确保向后兼容）：

```python
    def create_version_snapshot(
        self,
        source_id: str,
        item_id: str,
        skill_dir: Path,
        description: str = "",
        creator: str = "",
        creator_name: str = "",
        current_market_version: Optional[str] = None,
        created_at: Optional[str] = None,
        source_user_id: str = "",
        source_user_name: str = "",
        source_user_version: str = "",
    ) -> SkillVersion:
```

在创建 `SkillVersion` 实例处（约 184-193 行 `new_version = SkillVersion(...)`）追加 3 个字段：

```python
        new_version = SkillVersion(
            version_id=version_id,
            created_at=now,
            created_by=creator,
            created_by_name=creator_name,
            description=description,
            signature=signature,
            is_current=True,
            is_initial=is_initial,
            source_user_id=source_user_id,
            source_user_name=source_user_name,
            source_user_version=source_user_version,
        )
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest market/tests/unit/marketplace/test_version_service.py -v`

Expected: 全部 PASS（包含 3 个新增用例 + 所有已有用例）。

- [ ] **Step 6: Commit**

```bash
git add market/src/market/marketplace/version_models.py market/src/market/marketplace/version_service.py market/tests/unit/marketplace/test_version_service.py
git commit -m ":sparkles: feat(market/version): SkillVersion 新增 source_user_id/name/version 字段

- 用于区分操作者（created_by，admin）与内容来源用户（source_user_*）
- create_version_snapshot 签名扩展，向后兼容（默认空串）
- 旧 versions.json 通过 Pydantic 默认值平滑读取

Refs: docs/superpowers/specs/2026-06-13-skill-mcp-version-control-design.md §6.2"
```

---

### Task 4: R7 修复 + R8 切版本同步 creator_id

**Files:**
- Modify: `market/src/market/marketplace/version_service.py:125-153` (R7：同版本同内容不再翻 is_current)
- Modify: `market/src/market/app/routers/skill_versions.py:100-129` (R8：`_update_skill_index` 同步 creator_id)
- Test: `market/tests/unit/marketplace/test_version_service.py`、`test_skills_market.py`

- [ ] **Step 1: R7 失败测试**

在 `test_version_service.py` 末尾追加：

```python
def test_same_version_same_content_does_not_flip_is_current(tmp_path):
    """R7：同 version_id 同 signature 时不修改 is_current（保持原指针不变）."""
    svc = _make_version_service(tmp_path)
    skill_md_v1 = """---
name: t
version: "1.0.0"
---
v1 content
"""
    skill_md_v2 = """---
name: t
version: "1.0.1"
---
v2 content
"""
    skill_dir = _create_skill_dir(tmp_path, "src1", "item1", skill_md=skill_md_v1)

    # 创建 v1.0.0
    v1 = svc.create_version_snapshot(
        source_id="src1", item_id="item1",
        skill_dir=skill_dir, creator="u1", creator_name="user1",
    )
    assert v1.is_current is True

    # 升级到 v1.0.1
    (skill_dir / "SKILL.md").write_text(skill_md_v2, encoding="utf-8")
    v2 = svc.create_version_snapshot(
        source_id="src1", item_id="item1",
        skill_dir=skill_dir, creator="u2", creator_name="user2",
    )
    assert v2.is_current is True

    # 现在 v1.0.1 是 current。再次用 v1.0.0 内容做 snapshot（同版本同内容）
    (skill_dir / "SKILL.md").write_text(skill_md_v1, encoding="utf-8")
    svc.create_version_snapshot(
        source_id="src1", item_id="item1",
        skill_dir=skill_dir, creator="u3", creator_name="user3",
    )

    # R7：v1.0.1 仍是 current，不应被翻回 v1.0.0
    listed = svc.list_versions("src1", "item1")
    current_ids = [v["version_id"] for v in listed["versions"] if v["is_current"]]
    assert current_ids == ["1.0.1"], (
        f"R7 violated: current should remain 1.0.1, got {current_ids}"
    )
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest market/tests/unit/marketplace/test_version_service.py::test_same_version_same_content_does_not_flip_is_current -v`

Expected: FAIL — 当前实现 `version_service.py:144-145` 会强行把 v1.0.0 设为 current。

- [ ] **Step 3: 修复 R7**

修改 `market/src/market/marketplace/version_service.py:138-153`，把"同版本同内容"分支改为完全 no-op：

```python
            if (
                existing_version_info
                and existing_version_info.signature == new_signature
            ):
                # R7: 同版本同内容 → 完全 no-op
                # 不创建快照、不修改 is_current、不更新 manifest
                logger.info(
                    "Version %s already exists with same content, skipping snapshot creation (R7 no-op)",
                    version_id,
                )
                return existing_version_info
            else:
                raise ValueError(
                    f"Version {version_id} already exists with different content. "
                    f"Please specify a new version in SKILL.md or allow auto-bump.",
                )
```

注意：删除原 `for v in manifest.versions: v.is_current = ...` 与 `self._save_versions_manifest(...)` 这两行。

- [ ] **Step 4: 跑测试确认 R7 通过**

Run: `python -m pytest market/tests/unit/marketplace/test_version_service.py -v`

Expected: 全部 PASS。

- [ ] **Step 5: R8 失败测试**

在 `market/tests/unit/marketplace/test_skills_market.py` 末尾追加：

```python
def test_switch_version_updates_market_item_creator(tmp_path):
    """R8：switch_version 同步更新 MarketItem.creator_id/creator_name 到目标快照来源."""
    import json
    from market.marketplace.fs import save_index, load_index
    from market.marketplace.models import MarketItem
    from market.app.routers.skill_versions import _update_skill_index

    marketplace_root = tmp_path / "market"
    source_id = "src1"
    item_id = "item1"
    skill_dir = marketplace_root / source_id / "skills" / item_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        '---\nname: t\ndescription: d\nversion: "2.0.0"\n---\n',
        encoding="utf-8",
    )

    # 起始：creator=alice，市场版本 2.0.0
    save_index(marketplace_root, source_id, [
        MarketItem(
            item_id=item_id, item_type="skill", name="t", description="d",
            version="2.0.0",
            creator_id="alice_id", creator_name="alice",
            status="active",
        )
    ])

    # 准备 versions.json：v1.0.0 source_user=bob
    versions_path = marketplace_root / source_id / "skill_versions" / item_id / "versions.json"
    versions_path.parent.mkdir(parents=True, exist_ok=True)
    versions_path.write_text(
        json.dumps({
            "skill_name": "t",
            "versions": [{
                "version_id": "1.0.0",
                "created_at": "2025-01-01T00:00:00+00:00",
                "created_by": "admin", "created_by_name": "admin",
                "source_user_id": "bob_id", "source_user_name": "bob",
                "source_user_version": "1.0.0",
                "signature": "x", "is_current": True, "is_initial": True,
                "description": "",
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    class _FakeMarketplace:
        marketplace_root = marketplace_root  # noqa: F811

    fake = _FakeMarketplace()
    fake.marketplace_root = marketplace_root

    _update_skill_index(fake, source_id, item_id, skill_dir, "1.0.0")

    items = load_index(marketplace_root, source_id)
    item = items[0]
    assert item.version == "1.0.0"
    # R8: creator_id/name 跟随目标快照的 source_user_*
    assert item.creator_id == "bob_id"
    assert item.creator_name == "bob"
```

- [ ] **Step 6: 跑测试确认失败**

Run: `python -m pytest market/tests/unit/marketplace/test_skills_market.py::test_switch_version_updates_market_item_creator -v`

Expected: FAIL — `_update_skill_index` 当前不更新 `creator_id`。

- [ ] **Step 7: 修复 R8**

修改 `market/src/market/app/routers/skill_versions.py:100-129` 的 `_update_skill_index`：

```python
def _update_skill_index(
    marketplace: object,
    source_id: str,
    item_id: str,
    skill_dir: Path,
    version_id: str,
) -> None:
    """切换版本后更新市场索引中的技能信息（R8：同步 creator_id/name）."""
    items = load_index(marketplace.marketplace_root, source_id)
    item = next((i for i in items if i.item_id == item_id), None)

    if not item:
        return

    skill_md_path = skill_dir / "SKILL.md"
    if skill_md_path.exists():
        skill_md_content = skill_md_path.read_text(encoding="utf-8")
        new_name, new_desc = _parse_skill_md_frontmatter(
            skill_md_content,
            item.name,
            item.description,
        )
        item.name = new_name
        item.description = new_desc

    item.version = version_id
    item.updated_at = datetime.now(timezone.utc).isoformat()

    # R8: 同步更新 creator_id/creator_name 到目标快照的来源
    from ...marketplace.version_service import SkillVersionService
    svc = SkillVersionService(marketplace.marketplace_root)
    manifest = svc._load_versions_manifest(source_id, item_id)
    target = next(
        (v for v in manifest.versions if v.version_id == version_id),
        None,
    )
    if target is not None:
        if target.source_user_id:
            item.creator_id = target.source_user_id
            item.creator_name = target.source_user_name or target.source_user_id
        elif target.created_by:
            item.creator_id = target.created_by
            item.creator_name = target.created_by_name or target.created_by

    save_index(marketplace.marketplace_root, source_id, items)
```

- [ ] **Step 8: 跑测试确认 R8 通过**

Run: `python -m pytest market/tests/unit/marketplace/test_skills_market.py -v`

Expected: 全部 PASS。

- [ ] **Step 9: Commit**

```bash
git add market/src/market/marketplace/version_service.py market/src/market/app/routers/skill_versions.py market/tests/unit/marketplace
git commit -m ":bug: fix(market/version): R7 修复同版本同内容不翻 is_current，R8 切版本同步 creator

- R7：multi-user 续接场景下，同 version_id+signature 视为完全 no-op
- R8：switch_version 后，MarketItem.creator_id/name 跟随目标快照 source_user_*
  无 source_user_* 时回退到 created_by

Refs: docs/superpowers/specs/2026-06-13-skill-mcp-version-control-design.md §5 R7/R8"
```

---

### Task 5: Skill 名称硬唯一（service.py / skills_market.py 续接版本）

**Files:**
- Modify: `market/src/market/marketplace/service.py:370-407` (`_upsert_skill_item` 改为按 name 续接，移除"建议改名 _1" 分支由调用方决定)
- Modify: `market/src/market/marketplace/service.py:848-930` (`publish_skill`：移除 `SkillNameConflictError` 同名拒绝分支，改为续接)
- Modify: `market/src/market/app/routers/skills_market.py:265-354` (`_process_single_skill`：同名 → 续接而非建议改名)
- Test: `market/tests/unit/marketplace/test_service.py`、`test_skills_market.py`

> 历史 SkillNameConflictError 类保留（异常类不删，避免破坏现有 import），但**触发路径**全部移除——T8 完成后没有任何代码 raise 它。后续可在独立 cleanup task 删除。

- [ ] **Step 1: 写"不同用户同名续接"失败测试**

在 `market/tests/unit/marketplace/test_service.py` 末尾追加：

```python
@pytest.mark.asyncio
async def test_publish_skill_appends_version_for_different_user(tmp_path):
    """R4：不同用户同步同名 skill → 续接到现有 MarketItem，不再抛 SkillNameConflictError。"""
    from market.marketplace.service import MarketplaceService
    from market.marketplace.schemas import PublishSkillRequest
    from market.marketplace.fs import load_index

    # 用户 A 首发
    db = _MockDb()  # 使用现有 fixture 或 mock；如不存在请按 test_service.py 已有模式构造
    svc = MarketplaceService(
        marketplace_root=tmp_path / "market",
        swe_root=tmp_path / "swe",
        db=db,
    )
    user_a_skills = tmp_path / "swe" / "alice" / "workspaces" / "default" / "skills" / "demo"
    user_a_skills.mkdir(parents=True, exist_ok=True)
    (user_a_skills / "SKILL.md").write_text(
        '---\nname: demo\ndescription: a\nversion: "1.0.0"\n---\nbody-a',
        encoding="utf-8",
    )

    item_a = await svc.publish_skill("src1", PublishSkillRequest(
        name="demo", description="a", creator_id="alice", creator_name="Alice",
        skill_name="demo", agent_id="default",
    ))

    # 用户 B 同名同步（不同 creator_id）
    user_b_skills = tmp_path / "swe" / "bob" / "workspaces" / "default" / "skills" / "demo"
    user_b_skills.mkdir(parents=True, exist_ok=True)
    (user_b_skills / "SKILL.md").write_text(
        '---\nname: demo\ndescription: b\nversion: "2.0.0"\n---\nbody-b',
        encoding="utf-8",
    )

    item_b = await svc.publish_skill("src1", PublishSkillRequest(
        name="demo", description="b", creator_id="bob", creator_name="Bob",
        skill_name="demo", agent_id="default",
    ))

    # 续接到同一个 item_id
    assert item_b.item_id == item_a.item_id
    # creator 跟随当前上传者（保持 service 现状语义，详见 §6.1）
    assert item_b.creator_id == "bob"

    # 市场上仍只有一条
    items = load_index(tmp_path / "market", "src1")
    demos = [i for i in items if i.name == "demo"]
    assert len(demos) == 1
```

> 如果 `test_service.py` 没有 `_MockDb` 或类似 fixture，先 `Read` 它的最近用例（如 `test_publish_skill_*`）拷贝其设置方式；测试 db 通常用 `unittest.mock.AsyncMock`。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest market/tests/unit/marketplace/test_service.py::test_publish_skill_appends_version_for_different_user -v`

Expected: FAIL — 当前 `publish_skill` 在 `existing != None and not overwrite` 时抛 `SkillNameConflictError`。

- [ ] **Step 3: 修改 publish_skill 移除同名拒绝**

修改 `market/src/market/marketplace/service.py:858-869`，将：

```python
        items = load_index(self.marketplace_root, source_id)
        existing = next((i for i in items if i.name == req.name), None)

        # 同名技能已存在且未选择覆盖 → 提示用户
        if existing is not None and not req.overwrite:
            raise SkillNameConflictError(
                existing_item_id=existing.item_id,
                existing_name=existing.name,
                existing_creator_id=existing.creator_id,
                existing_creator_name=existing.creator_name,
                existing_version=existing.version,
            )

        item = _upsert_skill_item(items, existing, req)
```

改为：

```python
        items = load_index(self.marketplace_root, source_id)
        existing = next((i for i in items if i.name == req.name), None)

        # R4: 同名 → 续接到现有 MarketItem，无论 creator 是否相同
        # （SkillNameConflictError 已退役，相关 422/409 响应不再产生）
        item = _upsert_skill_item(items, existing, req)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest market/tests/unit/marketplace/test_service.py -v`

Expected: 全部 PASS。如有原本断言"同名抛 SkillNameConflictError"的用例，按新逻辑改为断言"续接到同 item_id"或删除（标注 obsolete）。

- [ ] **Step 5: 写 publish_skill_upload 同名续接测试**

在 `test_skills_market.py` 末尾追加（参考已有 `_process_single_skill` 测试）：

```python
def test_process_single_skill_appends_for_existing_name(tmp_path, monkeypatch):
    """R4：admin zip 上传同名 → 续接到现有 item，不再返回 suggested_name。"""
    from market.app.routers.skills_market import _process_single_skill
    from market.marketplace.fs import load_index, save_index
    from market.marketplace.models import MarketItem
    from market.marketplace.service import MarketplaceService

    marketplace_root = tmp_path / "market"
    svc = MarketplaceService(marketplace_root=marketplace_root, swe_root=tmp_path / "swe", db=_FakeDisconnectedDb())

    # 预置一个名为 demo 的现有 MarketItem
    save_index(marketplace_root, "src1", [
        MarketItem(
            item_id="existing-id", item_type="skill", name="demo",
            description="a", version="1.0.0",
            creator_id="alice", creator_name="Alice", status="active",
        )
    ])

    # 准备一份 zip 解压后的目录
    skill_dir = tmp_path / "extract" / "demo"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        '---\nname: demo\ndescription: b\nversion: "2.0.0"\n---\nbody-b',
        encoding="utf-8",
    )

    name, conflict, _ = _process_single_skill(
        skill_dir, "demo", svc, "src1", "bob", "Bob",
        category_id=None, overwrite=False,
    )
    assert conflict is None, "R4 broken: same-name from different user must append, not conflict"
    assert name == "demo"

    items = load_index(marketplace_root, "src1")
    assert len(items) == 1
    assert items[0].item_id == "existing-id"  # 续接到原 id
    assert items[0].version == "2.0.0"  # SKILL.md 显式 version
    assert items[0].creator_id == "bob"  # 当前上传者
```

`_FakeDisconnectedDb` 为简单替代品（仅需 `is_connected=False`）；如该 fixture 已存在沿用。

- [ ] **Step 6: 跑测试确认失败**

Run: `python -m pytest market/tests/unit/marketplace/test_skills_market.py::test_process_single_skill_appends_for_existing_name -v`

Expected: FAIL — 当前 `_process_single_skill` 在 `existing.status == "active" and not overwrite` 时返回 `{"skill_name": ..., "suggested_name": "<name>_1"}`。

- [ ] **Step 7: 修改 _process_single_skill 移除同名拒绝**

修改 `market/src/market/app/routers/skills_market.py:294-302`，将：

```python
    if existing:
        # 不允许覆盖时，返回冲突提示
        if not overwrite and existing.status == "active":
            return (
                None,
                {"skill_name": name, "suggested_name": f"{name}_1"},
                name,
            )

        # 允许覆盖时，更新现有条目
        # 版本策略：SKILL.md 有版本则使用，否则自动递增
        now = datetime.now(timezone.utc).isoformat()
        ...
```

改为（移除 `if not overwrite and existing.status == "active"` 分支）：

```python
    if existing:
        # R4: 同名 → 续接到现有条目（无论 creator 是否相同）
        # 旧的 suggested_name 提示已退役
        now = datetime.now(timezone.utc).isoformat()
        existing.created_at = now
        existing.status = "active"
        existing.description = description
        existing.version = (
            version if version else _bump_patch(existing.version)
        )
        existing.creator_id = user_id
        existing.creator_name = user_name
        existing.category_id = category_id
        existing.updated_at = now
        item = existing
    else:
        ...
```

- [ ] **Step 8: 跑全市场测试确认无回归**

Run: `python -m pytest market/tests/unit -v`

Expected: 全部 PASS。如有遗留旧用例断言 `suggested_name` 出现，按新逻辑修正断言或标注为 obsolete 并删除。

- [ ] **Step 9: Commit**

```bash
git add market/src/market/marketplace/service.py market/src/market/app/routers/skills_market.py market/tests/unit/marketplace/test_service.py market/tests/unit/marketplace/test_skills_market.py
git commit -m ':boom: feat(market/skill): R4 名称硬唯一，同名一律续接版本

- service.publish_skill: 移除同名拒绝分支，不再抛 SkillNameConflictError
- skills_market._process_single_skill: 移除 \"suggested_name\" 提示，同名直接续接
- 不同用户同步同名 skill 不再被建议改名 _1，市场上一个 name 永远只有一条 MarketItem

BREAKING CHANGE: 客户端不再收到 409 + suggested_name 响应。前端的 \"建议改名\" UI 需在 T14 一并清理。

Refs: docs/superpowers/specs/2026-06-13-skill-mcp-version-control-design.md §5 R4'
```

---

### Task 6: publish_skill / publish_skill_upload 透传 source_user_*

**Files:**
- Modify: `market/src/market/marketplace/service.py:848-930` (`publish_skill` 把 `req.creator_id` 当 source_user，`req.skill_name` 提取真实 version_text 作 source_user_version)
- Modify: `market/src/market/app/routers/skills_market.py:265-354` (`_process_single_skill` 透传 source_user_id="" / source_user_version="v0.0.0"，created_by=操作者)
- Modify: `market/src/market/app/routers/skills_market.py:357+` (`publish_skill_upload` 把 X-User-Id 当 created_by，source_user_id="" 显式传入)
- Test: `market/tests/unit/marketplace/test_service.py`、`test_skills_market.py`

- [ ] **Step 1: 写 publish_skill 透传测试**

在 `test_service.py` 追加：

```python
@pytest.mark.asyncio
async def test_publish_skill_records_source_user_from_creator(tmp_path):
    """R6：admin 走 PublishSkillRequest 时，source_user_id=req.creator_id。
    source_user_version=被引用用户工作区里 SKILL.md 的真实版本。"""
    from market.marketplace.service import MarketplaceService, SkillVersionService
    from market.marketplace.schemas import PublishSkillRequest

    svc = MarketplaceService(tmp_path / "market", tmp_path / "swe", _MockDb())

    # 在 alice 工作区放一个 v1.5.2 的 demo skill
    user_dir = tmp_path / "swe" / "alice" / "workspaces" / "default" / "skills" / "demo"
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "SKILL.md").write_text(
        '---\nname: demo\ndescription: d\nversion: "1.5.2"\n---\nbody',
        encoding="utf-8",
    )

    item = await svc.publish_skill("src1", PublishSkillRequest(
        name="demo", description="d",
        creator_id="alice",  # ← 内容来源用户
        creator_name="Alice",
        skill_name="demo", agent_id="default",
    ))

    # 检查快照：source_user_id 应为 alice，source_user_version 为 1.5.2
    vsvc = SkillVersionService(tmp_path / "market")
    listed = vsvc.list_versions("src1", item.item_id)
    snap = listed["versions"][0]
    assert snap["source_user_id"] == "alice"
    assert snap["source_user_name"] == "Alice"
    assert snap["source_user_version"] == "1.5.2"
```

> 注意：本测试假设 `publish_skill` 调用方（admin 端点）将 `X-User-Id` 也透传过来。本任务只改 service 层接收并转发；端点层透传由 router 路径覆盖（同 step 5 一并加）。当前 `publish_skill` 签名 `publish_skill(self, source_id, req)` 没有 `operator_id`/`operator_name` 参数——本步骤需要在 step 3 给 `publish_skill` 增参（带默认值，向后兼容）。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest market/tests/unit/marketplace/test_service.py::test_publish_skill_records_source_user_from_creator -v`

Expected: FAIL — `source_user_*` 字段为空串（当前 `create_version_snapshot` 调用未传这些参数）。

- [ ] **Step 3: 修改 publish_skill 透传 source_user_***

修改 `market/src/market/marketplace/service.py:848-930` 的 `publish_skill`：

签名改为（追加两个可选参数）：

```python
    async def publish_skill(
        self,
        source_id: str,
        req: PublishSkillRequest,
        operator_id: str = "",
        operator_name: str = "",
    ) -> MarketItem:
```

`operator_id`/`operator_name` 默认空串向后兼容；优先使用 operator，否则回退到 `req.creator_*`（保留旧行为）。

在文件中调用 `version_svc.create_version_snapshot(...)` 处（约 897-906 行）改为：

```python
        # 创建版本快照
        # source_user_*：内容来源是 req.creator_*（PublishSkillRequest 显式指定）
        # created_by_*：操作者（admin），若未传则与 source_user 相同（向后兼容）
        source_user_version = ""
        skill_md_path = skill_dir / "SKILL.md"
        if skill_md_path.exists():
            try:
                from ..utils.skill_md import extract_version
                source_user_version = extract_version(
                    skill_md_path.read_text(encoding="utf-8"),
                )
            except OSError:
                pass

        version_svc = SkillVersionService(self.marketplace_root)
        try:
            version_svc.create_version_snapshot(
                source_id=source_id,
                item_id=item.item_id,
                skill_dir=skill_dir,
                description=f"上架版本 {item.version}",
                creator=operator_id or req.creator_id,
                creator_name=operator_name or req.creator_name,
                current_market_version=item.version,
                source_user_id=req.creator_id,
                source_user_name=req.creator_name,
                source_user_version=source_user_version,
            )
        except Exception as e:
            logger.warning("Failed to create version snapshot: %s", e)
```

- [ ] **Step 4: 修改路由层透传 operator**

修改 `market/src/market/app/routers/skills_market.py:475-498`（`publish_skill` 路由）：

```python
@router.post(
    "/market/skills",
    response_model=MarketSkillResponse,
    status_code=status.HTTP_201_CREATED,
)
async def publish_skill(
    req: PublishSkillRequest,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
):
    """上架技能（管理员）."""
    source_id = require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = request.app.state.marketplace
    operator_name = decode_user_name(x_user_name) or ""
    item = await svc.publish_skill(
        source_id, req,
        operator_id=x_user_id or "",
        operator_name=operator_name,
    )
    # SkillNameConflictError 已不再抛出（T5），原 except 分支可移除
    return MarketSkillResponse(...)  # 字段保持原样
```

> 完整 MarketSkillResponse 字段见 schemas.py:34-50，保持不变。原 `try/except SkillNameConflictError` 块整体删除，因为 T5 后不再抛出。

- [ ] **Step 5: 跑 publish_skill 测试通过**

Run: `python -m pytest market/tests/unit/marketplace/test_service.py -v`

Expected: 全部 PASS。

- [ ] **Step 6: 写 publish_skill_upload (admin zip) source_user_*=空 测试**

在 `test_skills_market.py` 追加：

```python
def test_process_single_skill_admin_zip_source_user_is_empty(tmp_path):
    """R6：admin 走 publish-upload (zip) → source_user_id="" / source_user_version="v0.0.0"."""
    from market.app.routers.skills_market import _process_single_skill
    from market.marketplace.service import MarketplaceService, SkillVersionService

    marketplace_root = tmp_path / "market"
    svc = MarketplaceService(marketplace_root, tmp_path / "swe", _FakeDisconnectedDb())

    skill_dir = tmp_path / "extract" / "newdemo"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        '---\nname: newdemo\ndescription: d\nversion: "1.0.0"\n---\nbody',
        encoding="utf-8",
    )

    name, conflict, _ = _process_single_skill(
        skill_dir, "newdemo", svc, "src1", "admin_id", "Admin",
        category_id=None, overwrite=False,
    )
    assert conflict is None
    assert name == "newdemo"

    vsvc = SkillVersionService(marketplace_root)
    items = list(_get_items_for_test(marketplace_root, "src1"))  # 用 fs.load_index
    item = next(i for i in items if i.name == "newdemo")
    listed = vsvc.list_versions("src1", item.item_id)
    snap = listed["versions"][0]
    assert snap["created_by"] == "admin_id"
    assert snap["source_user_id"] == ""           # admin zip 路径
    assert snap["source_user_version"] == "v0.0.0"
```

> `_get_items_for_test` 仅是辅助；可直接 `from market.marketplace.fs import load_index` 替代。

- [ ] **Step 7: 跑测试确认失败**

Run: `python -m pytest market/tests/unit/marketplace/test_skills_market.py::test_process_single_skill_admin_zip_source_user_is_empty -v`

Expected: FAIL — `_process_single_skill` 当前没传 source_user_*。

- [ ] **Step 8: 修改 _process_single_skill 透传**

修改 `market/src/market/app/routers/skills_market.py:340-352` 的 `version_svc.create_version_snapshot` 调用：

```python
    # 创建版本快照
    # admin zip 路径：source_user_id="" 表示无来源；source_user_version="v0.0.0"（spec R6）
    version_svc = SkillVersionService(svc.marketplace_root)
    try:
        version_svc.create_version_snapshot(
            source_id=source_id,
            item_id=item.item_id,
            skill_dir=market_skill_dir,
            description="",
            creator=user_id,  # 操作者 = admin
            creator_name=user_name,
            current_market_version=item.version,
            source_user_id="",  # admin zip 上传无内容来源
            source_user_name="",
            source_user_version="v0.0.0",
        )
    except Exception as e:
        logger.warning("Failed to create version snapshot: %s", e)
```

- [ ] **Step 9: 跑全 skills_market 测试**

Run: `python -m pytest market/tests/unit/marketplace/test_skills_market.py -v`

Expected: 全部 PASS。

- [ ] **Step 10: Commit**

```bash
git add market/src/market/marketplace/service.py market/src/market/app/routers/skills_market.py market/tests/unit/marketplace/
git commit -m ":sparkles: feat(market/skill): publish_skill / publish-upload 透传 source_user_*

- publish_skill (PublishSkillRequest): source_user_id=req.creator_id
  source_user_version=该用户工作区 SKILL.md 中的版本
  created_by=operator_id（X-User-Id, admin）
- publish_skill_upload (admin zip): source_user_id=\"\", source_user_version=\"v0.0.0\"
  created_by=admin
- 区分操作者与内容来源用户，支持 R5/R6 快照归属

Refs: docs/superpowers/specs/2026-06-13-skill-mcp-version-control-design.md §5 R5/R6"
```

---

### Task 7: update_my_mcp 行为修正（显式 > 内容变才递增）+ 响应增字段

**Files:**
- Modify: `market/src/market/app/routers/my_mcp.py:533-591` (`update_my_mcp` 重构 version 处理)
- Modify: `market/src/market/app/routers/my_mcp.py` 中 `MyMCPDetail` 定义 或 `marketplace/schemas.py` (`MyMCPDetail` 增 `version_changed`/`previous_version`/`bump_reason`)
- Test: 新增 `market/tests/unit/test_my_mcp_update.py`（如已有同主题文件则追加）

> R2：MCP 编辑时——
> 1. body 显式带 `version` → 用之，`bump_reason="explicit"`
> 2. body 没带 + 字段实际有变化（除时间戳外） → patch+1，`bump_reason="auto"`
> 3. body 没带 + 字段无实际变化 → 保持原版本号，`bump_reason="unchanged"`

- [ ] **Step 1: 找到 MyMCPDetail 定义位置**

Run: `grep -n "class MyMCPDetail" market/src/market/app/routers/my_mcp.py market/src/market/marketplace/schemas.py`

记录返回的位置。后续所有"修改 MyMCPDetail" 的步骤以该位置为准。

- [ ] **Step 2: 写失败测试**

创建 `market/tests/unit/test_my_mcp_update.py`：

```python
# -*- coding: utf-8 -*-
"""update_my_mcp 版本递增行为测试 (R2 / T7)."""

from __future__ import annotations

import pytest
from datetime import datetime
from fastapi.testclient import TestClient

# 视项目实际入口调整 import
from market.app.main import app


def _headers(user_id="admin", user_name="Admin", manager=True):
    h = {"X-User-Id": user_id, "X-User-Name": user_name, "X-Source-Id": "src1"}
    if manager:
        h["X-Manager"] = "true"
    return h


@pytest.fixture
def client(tmp_path, monkeypatch):
    # TODO: 按 market/tests/unit 现有 conftest 构造 TestClient + tmp swe_root
    # 如已有 fixture 直接复用
    return TestClient(app)


def _create_mcp(client, key="m1"):
    r = client.post("/market/my-mcp", headers=_headers(), json={
        "client_key": key, "name": key,
        "transport": "stdio", "command": "/bin/true",
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_update_with_explicit_version_uses_it(client):
    _create_mcp(client)
    r = client.put("/market/my-mcp/m1", headers=_headers(), json={
        "version": "9.9.9",
        "description": "updated",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "9.9.9"
    assert body["bump_reason"] == "explicit"
    assert body["version_changed"] is True
    assert body["previous_version"] == "1.0.0"


def test_update_without_explicit_version_when_content_changed_bumps(client):
    _create_mcp(client)
    r = client.put("/market/my-mcp/m1", headers=_headers(), json={
        "description": "new description",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "1.0.1"
    assert body["bump_reason"] == "auto"
    assert body["version_changed"] is True
    assert body["previous_version"] == "1.0.0"


def test_update_without_changes_does_not_bump(client):
    """R2：body 不变内容 → 版本不动，bump_reason=unchanged。"""
    detail = _create_mcp(client)
    initial_version = detail["version"]
    # 用相同字段重复 PUT
    r = client.put("/market/my-mcp/m1", headers=_headers(), json={
        "name": detail["name"],
        "description": detail.get("description", ""),
    })
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == initial_version  # 版本未变
    assert body["bump_reason"] == "unchanged"
    assert body["version_changed"] is False
    assert body["previous_version"] == initial_version
```

> conftest/fixture 缺失时按已有 `market/tests/unit/marketplace/test_*.py` 风格补：通常构造 swe_root tmp 目录、临时 agent.json、注入到 `app.state`。如时间紧张可用 `httpx.AsyncClient` 直接调端点函数。

- [ ] **Step 3: 跑测试确认失败**

Run: `python -m pytest market/tests/unit/test_my_mcp_update.py -v`

Expected: FAIL — 当前 `update_my_mcp` 不读 body.version、不返回新 3 字段、每次都 bump。

- [ ] **Step 4: 给 MyMCPDetail 加 3 个响应字段**

按 Step 1 找到的位置修改 `MyMCPDetail`（schemas.py 或 my_mcp.py），追加：

```python
class MyMCPDetail(BaseModel):
    # ... 原字段不变 ...
    version_changed: bool = False
    previous_version: str = ""
    bump_reason: Literal["explicit", "auto", "unchanged", ""] = ""
```

`Literal` 已在文件顶部 imported。`bump_reason` 默认空串以兼容创建/列表场景下的响应。

- [ ] **Step 5: 重构 update_my_mcp 版本逻辑**

修改 `market/src/market/app/routers/my_mcp.py:533-591`：

```python
@router.put("/{client_key}", response_model=MyMCPDetail)
async def update_my_mcp(
    request: Request,
    client_key: str = FastAPIPath(...),
    body: MyMCPUpdateRequest = Body(...),
) -> MyMCPDetail:
    """更新 MCP 配置（R2：显式 > 内容变才递增）."""
    context, agent_config = load_agent_config_for_request(request)
    mark_request_state(request, context)

    if agent_config.mcp is None or client_key not in agent_config.mcp.clients:
        raise HTTPException(
            404,
            detail=_mcp_client_not_found_detail(client_key),
        )

    existing = agent_config.mcp.clients[client_key]
    update_data = body.model_dump(exclude_unset=True)

    if _is_distributed_from_market(existing):
        for field in SENSITIVE_FIELDS:
            if field in update_data:
                raise HTTPException(
                    403,
                    detail=f"Cannot modify '{field}' for distributed MCP",
                )

    merged_data = existing.model_dump(mode="json")
    previous_version = merged_data.get("version") or "1.0.0"

    if "env" in update_data and update_data["env"] is not None:
        update_data["env"] = restore_original_values(
            update_data["env"], existing.env or {},
        )
    if "headers" in update_data and update_data["headers"] is not None:
        update_data["headers"] = restore_original_values(
            update_data["headers"], existing.headers or {},
        )

    # R2 版本决策
    explicit_version = update_data.pop("version", None)
    merged_data.update(update_data)
    merged_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    # 计算"内容是否真有变化"——比较除 version/updated_at 外的字段
    content_changed = False
    for k, v in update_data.items():
        if k in ("version", "updated_at"):
            continue
        if existing.model_dump(mode="json").get(k) != v:
            content_changed = True
            break

    if explicit_version:
        merged_data["version"] = explicit_version
        bump_reason = "explicit"
    elif content_changed:
        merged_data["version"] = _bump_patch(previous_version)
        bump_reason = "auto"
    else:
        merged_data["version"] = previous_version
        bump_reason = "unchanged"

    updated_client = MCPClientConfig.model_validate(merged_data)
    agent_config.mcp.clients[client_key] = updated_client
    save_agent_config_for_request(context, agent_config, request)

    await _log_my_mcp_operation(request, context, "edit", updated_client.name)

    detail = _mask_sensitive_values(updated_client)
    detail.client_key = client_key
    detail.version_changed = (merged_data["version"] != previous_version)
    detail.previous_version = previous_version
    detail.bump_reason = bump_reason
    return detail
```

> 注意 `MyMCPUpdateRequest` 是否已含 `version` 字段——如未含，先在 `MyMCPUpdateRequest` 加 `version: Optional[str] = None`。

- [ ] **Step 6: 跑测试确认通过**

Run: `python -m pytest market/tests/unit/test_my_mcp_update.py -v`

Expected: 全部 PASS（3 个用例）。

- [ ] **Step 7: 跑全市场测试无回归**

Run: `python -m pytest market/tests/unit -v`

Expected: 全部 PASS。

- [ ] **Step 8: Commit**

```bash
git add market/src/market/app/routers/my_mcp.py market/src/market/marketplace/schemas.py market/tests/unit/test_my_mcp_update.py
git commit -m ':bug: fix(market/my-mcp): R2 版本决策——显式 > 内容变才递增

- update_my_mcp: body 含 version → 用之 (explicit)；
  无 version + 内容变 → patch+1 (auto)；
  无 version + 内容未变 → 保持原版本 (unchanged)
- MyMCPDetail 新增 version_changed / previous_version / bump_reason 三响应字段
  前端可据此提示 \"未递增\"
- 修复每次 PUT 都强制 bump 的现状

Refs: docs/superpowers/specs/2026-06-13-skill-mcp-version-control-design.md §5 R2'
```

---

### Task 8: 新增 MCPVersion 模型 + MCPVersionService 平行快照能力

**Files:**
- Modify: `market/src/market/marketplace/version_models.py` (追加 `MCPVersion` / `MCPVersionsManifest`)
- Create: `market/src/market/marketplace/mcp_version_service.py`
- Create: `market/tests/unit/marketplace/test_mcp_version_service.py`

> 设计与 `SkillVersionService` 完全对称。signature 仅对 `mcp.json` 反序列化后做 canonical JSON dump 再 SHA256（spec §6.3 决议）。

- [ ] **Step 1: 在 version_models.py 追加 MCPVersion / MCPVersionsManifest**

修改 `market/src/market/marketplace/version_models.py`，在 `VersionsManifest` 之后追加：

```python
class MCPVersion(BaseModel):
    """单个 MCP 版本信息（与 SkillVersion 字段对齐）."""

    version_id: str
    created_at: str
    created_by: str = ""
    created_by_name: str = ""
    description: str = ""
    signature: str = ""
    is_current: bool = False
    is_initial: bool = False
    source_user_id: str = ""
    source_user_name: str = ""
    source_user_version: str = ""


class MCPVersionsManifest(BaseModel):
    """MCP 版本清单文件结构."""

    client_key: str = ""
    name: str = ""
    versions: list[MCPVersion] = Field(default_factory=list)
```

- [ ] **Step 2: 写 mcp_version_service 失败测试**

创建 `market/tests/unit/marketplace/test_mcp_version_service.py`：

```python
# -*- coding: utf-8 -*-
"""MCP 版本管理服务单元测试."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from market.marketplace.mcp_version_service import MCPVersionService


def _write_mcp_json(item_dir: Path, content: dict) -> Path:
    item_dir.mkdir(parents=True, exist_ok=True)
    p = item_dir / "mcp.json"
    p.write_text(
        json.dumps(content, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return p


def test_create_initial_snapshot(tmp_path):
    svc = MCPVersionService(tmp_path / "market")
    item_dir = tmp_path / "market" / "src1" / "mcp" / "item1"
    _write_mcp_json(item_dir, {
        "name": "demo", "transport": "stdio", "command": "/bin/true",
    })
    v = svc.create_version_snapshot(
        source_id="src1", item_id="item1",
        mcp_dir=item_dir, version_id="1.0.0",
        creator="admin", creator_name="admin",
        source_user_id="alice", source_user_name="Alice",
        source_user_version="1.0.0",
    )
    assert v.version_id == "1.0.0"
    assert v.is_initial is True
    assert v.is_current is True
    assert v.source_user_id == "alice"


def test_create_two_snapshots_only_latest_is_current(tmp_path):
    svc = MCPVersionService(tmp_path / "market")
    item_dir = tmp_path / "market" / "src1" / "mcp" / "item1"
    _write_mcp_json(item_dir, {"name": "demo", "transport": "stdio", "command": "/a"})
    svc.create_version_snapshot(
        source_id="src1", item_id="item1", mcp_dir=item_dir,
        version_id="1.0.0", creator="admin", creator_name="admin",
    )
    _write_mcp_json(item_dir, {"name": "demo", "transport": "stdio", "command": "/b"})
    svc.create_version_snapshot(
        source_id="src1", item_id="item1", mcp_dir=item_dir,
        version_id="1.0.1", creator="admin", creator_name="admin",
    )
    listed = svc.list_versions("src1", "item1")
    versions = listed["versions"]
    currents = [v for v in versions if v["is_current"]]
    assert len(currents) == 1
    assert currents[0]["version_id"] == "1.0.1"


def test_signature_canonical_json_only(tmp_path):
    """同语义不同 key 顺序的 mcp.json 应产生相同 signature。"""
    svc = MCPVersionService(tmp_path / "market")
    item_dir = tmp_path / "market" / "src1" / "mcp" / "item1"

    p = item_dir / "mcp.json"
    item_dir.mkdir(parents=True, exist_ok=True)
    p.write_text('{"a": 1, "b": 2}', encoding="utf-8")
    sig1 = svc._calculate_signature(item_dir)

    p.write_text('{"b": 2, "a": 1}', encoding="utf-8")
    sig2 = svc._calculate_signature(item_dir)

    assert sig1 == sig2


def test_same_version_same_content_no_op(tmp_path):
    """R7：MCP 同样适用——同 version_id 同 signature 不翻 is_current。"""
    svc = MCPVersionService(tmp_path / "market")
    item_dir = tmp_path / "market" / "src1" / "mcp" / "item1"
    _write_mcp_json(item_dir, {"name": "demo", "transport": "stdio", "command": "/a"})
    svc.create_version_snapshot(
        source_id="src1", item_id="item1", mcp_dir=item_dir,
        version_id="1.0.0", creator="admin", creator_name="admin",
    )
    _write_mcp_json(item_dir, {"name": "demo", "transport": "stdio", "command": "/b"})
    svc.create_version_snapshot(
        source_id="src1", item_id="item1", mcp_dir=item_dir,
        version_id="1.0.1", creator="admin", creator_name="admin",
    )
    # 当前 current=1.0.1。再用 1.0.0 同内容做 snapshot
    _write_mcp_json(item_dir, {"name": "demo", "transport": "stdio", "command": "/a"})
    svc.create_version_snapshot(
        source_id="src1", item_id="item1", mcp_dir=item_dir,
        version_id="1.0.0", creator="admin", creator_name="admin",
    )
    listed = svc.list_versions("src1", "item1")
    currents = [v for v in listed["versions"] if v["is_current"]]
    assert [c["version_id"] for c in currents] == ["1.0.1"]
```

- [ ] **Step 3: 跑测试确认失败**

Run: `python -m pytest market/tests/unit/marketplace/test_mcp_version_service.py -v`

Expected: FAIL — `MCPVersionService` 不存在。

- [ ] **Step 4: 实现 mcp_version_service.py**

创建 `market/src/market/marketplace/mcp_version_service.py`：

```python
# -*- coding: utf-8 -*-
"""MCP 版本管理服务.

存储结构（与 SkillVersionService 平行）：
    <marketplace_root>/<source_id>/mcp_versions/<item_id>/
    ├── versions.json
    ├── v1.0.0/
    │   └── mcp.json
    └── v1.0.1/
        └── mcp.json
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .version_models import MCPVersion, MCPVersionsManifest

logger = logging.getLogger(__name__)


def _atomic_write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


class MCPVersionService:
    """MCP 版本管理服务（与 SkillVersionService 对称）."""

    def __init__(self, marketplace_root: Path):
        self.marketplace_root = Path(marketplace_root)

    # --- public ---------------------------------------------------------

    def create_version_snapshot(
        self,
        source_id: str,
        item_id: str,
        mcp_dir: Path,
        version_id: str,
        creator: str = "",
        creator_name: str = "",
        description: str = "",
        source_user_id: str = "",
        source_user_name: str = "",
        source_user_version: str = "",
    ) -> MCPVersion:
        """创建 MCP 版本快照."""
        manifest = self._load_manifest(source_id, item_id)
        is_initial = len(manifest.versions) == 0

        new_signature = self._calculate_signature(mcp_dir)

        # R7: 同 version_id 同 signature → no-op
        existing = next(
            (v for v in manifest.versions if v.version_id == version_id),
            None,
        )
        if existing is not None:
            if existing.signature == new_signature:
                logger.info(
                    "MCP version %s already exists with same content (R7 no-op)",
                    version_id,
                )
                return existing
            raise ValueError(
                f"MCP version {version_id} already exists with different content. "
                f"Please specify a new version.",
            )

        # 复制文件到版本目录
        version_dir = self._get_version_dir(source_id, item_id, version_id)
        if version_dir.exists():
            shutil.rmtree(version_dir)
        version_dir.mkdir(parents=True)
        src_mcp_json = mcp_dir / "mcp.json"
        if src_mcp_json.exists():
            shutil.copy2(src_mcp_json, version_dir / "mcp.json")

        # 翻转 is_current
        for v in manifest.versions:
            v.is_current = False

        new_version = MCPVersion(
            version_id=version_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            created_by=creator,
            created_by_name=creator_name,
            description=description,
            signature=new_signature,
            is_current=True,
            is_initial=is_initial,
            source_user_id=source_user_id,
            source_user_name=source_user_name,
            source_user_version=source_user_version,
        )
        manifest.versions.append(new_version)
        # client_key/name 由调用方在更新 MarketItem 时维护，本服务不强制
        self._save_manifest(source_id, item_id, manifest)
        logger.info("Created MCP version snapshot %s for item %s", version_id, item_id)
        return new_version

    def list_versions(self, source_id: str, item_id: str) -> dict[str, Any]:
        manifest = self._load_manifest(source_id, item_id)
        versions = sorted(
            manifest.versions, key=lambda v: v.created_at, reverse=True,
        )
        return {
            "client_key": manifest.client_key,
            "name": manifest.name,
            "versions": [v.model_dump() for v in versions],
        }

    def switch_version(
        self,
        source_id: str,
        item_id: str,
        target_version_id: str,
        current_mcp_dir: Path,
    ) -> dict[str, Any]:
        manifest = self._load_manifest(source_id, item_id)
        target = next(
            (v for v in manifest.versions if v.version_id == target_version_id),
            None,
        )
        if target is None:
            return {"success": False, "message": f"Version {target_version_id} not found"}

        target_dir = self._get_version_dir(source_id, item_id, target_version_id)
        if not (target_dir / "mcp.json").exists():
            return {"success": False, "message": f"Version dir {target_version_id} missing mcp.json"}

        current_mcp_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target_dir / "mcp.json", current_mcp_dir / "mcp.json")

        previous = next((v for v in manifest.versions if v.is_current), None)
        for v in manifest.versions:
            v.is_current = (v.version_id == target_version_id)
        self._save_manifest(source_id, item_id, manifest)

        return {
            "success": True,
            "previous_version": previous.version_id if previous else "",
            "current_version": target_version_id,
            "message": f"Switched to version {target_version_id}",
        }

    # --- internal -------------------------------------------------------

    def _get_version_root(self, source_id: str, item_id: str) -> Path:
        return self.marketplace_root / source_id / "mcp_versions" / item_id

    def _get_version_dir(self, source_id: str, item_id: str, version_id: str) -> Path:
        return self._get_version_root(source_id, item_id) / version_id

    def _get_manifest_path(self, source_id: str, item_id: str) -> Path:
        return self._get_version_root(source_id, item_id) / "versions.json"

    def _load_manifest(self, source_id: str, item_id: str) -> MCPVersionsManifest:
        path = self._get_manifest_path(source_id, item_id)
        if not path.exists():
            return MCPVersionsManifest()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return MCPVersionsManifest(**data)
        except (json.JSONDecodeError, KeyError):
            return MCPVersionsManifest()

    def _save_manifest(
        self,
        source_id: str,
        item_id: str,
        manifest: MCPVersionsManifest,
    ) -> None:
        path = self._get_manifest_path(source_id, item_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(path, manifest.model_dump())

    def _calculate_signature(self, mcp_dir: Path) -> str:
        """SHA256(canonical_json(mcp.json))；mcp.json 缺失时返回空 sha 之 hash."""
        mcp_json_path = mcp_dir / "mcp.json"
        if not mcp_json_path.exists():
            return hashlib.sha256(b"").hexdigest()
        try:
            data = json.loads(mcp_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # 落到原始字节做 hash，避免完全失败
            return hashlib.sha256(mcp_json_path.read_bytes()).hexdigest()
        canonical = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest market/tests/unit/marketplace/test_mcp_version_service.py -v`

Expected: 全部 PASS（4 个用例）。

- [ ] **Step 6: Commit**

```bash
git add market/src/market/marketplace/version_models.py market/src/market/marketplace/mcp_version_service.py market/tests/unit/marketplace/test_mcp_version_service.py
git commit -m ":sparkles: feat(market/mcp): 新增 MCPVersion 模型与 MCPVersionService

- 与 SkillVersionService 字段、API 完全对称
- 存储路径 <root>/<source>/mcp_versions/<item_id>/{versions.json, v<x.y.z>/mcp.json}
- signature: SHA256(canonical_json(mcp.json))，仅 mcp.json 内容
- R7 同样适用：同 version_id 同 signature 视为 no-op

Refs: docs/superpowers/specs/2026-06-13-skill-mcp-version-control-design.md §6.3"
```

---

### Task 9: publish_mcp 接入快照 + 名称硬唯一续接

**Files:**
- Modify: `market/src/market/marketplace/service.py:1933-2105` (`_apply_publish_update` + `publish_mcp`：移除同名拒绝、调用 MCPVersionService)
- Modify: `market/src/market/app/routers/my_mcp.py:657-684` (`_publish_client_to_market` 透传 source_user_*)
- Modify: `market/src/market/app/routers/mcp_market.py:236-304` (`upload_mcp` 透传 source_user_id="" / source_user_version="v0.0.0")
- Test: `market/tests/unit/marketplace/test_service.py`

- [ ] **Step 1: 写 publish_mcp 续接 + 快照失败测试**

在 `test_service.py` 末尾追加：

```python
@pytest.mark.asyncio
async def test_publish_mcp_appends_for_different_user(tmp_path):
    """R4：不同用户同名 MCP → 续接到现有 item，并创建 MCPVersion 快照。"""
    from market.marketplace.service import MarketplaceService
    from market.marketplace.schemas import PublishMCPRequest
    from market.marketplace.fs import load_index
    from market.marketplace.mcp_version_service import MCPVersionService

    svc = MarketplaceService(tmp_path / "market", tmp_path / "swe", _MockDb())

    # alice 首发
    item_a = await svc.publish_mcp("src1", PublishMCPRequest(
        client_key="m1", name="demo", description="a",
        creator_id="alice", creator_name="Alice",
        config={"name": "demo", "transport": "stdio", "command": "/a"},
        version="1.0.0",
    ))

    # bob 同名同步（不同 creator_id），不带 overwrite 也不应抛异常
    item_b = await svc.publish_mcp("src1", PublishMCPRequest(
        client_key="m1", name="demo", description="b",
        creator_id="bob", creator_name="Bob",
        config={"name": "demo", "transport": "stdio", "command": "/b"},
        version="2.0.0",
    ))

    assert item_b.item_id == item_a.item_id
    items = load_index(tmp_path / "market", "src1")
    demos = [i for i in items if i.name == "demo"]
    assert len(demos) == 1

    # 快照里应有两个版本
    vsvc = MCPVersionService(tmp_path / "market")
    listed = vsvc.list_versions("src1", item_a.item_id)
    ids = sorted(v["version_id"] for v in listed["versions"])
    assert ids == ["1.0.0", "2.0.0"]
    # 最新快照 source_user 是 bob
    current = next(v for v in listed["versions"] if v["is_current"])
    assert current["version_id"] == "2.0.0"
    assert current["source_user_id"] == "bob"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest market/tests/unit/marketplace/test_service.py::test_publish_mcp_appends_for_different_user -v`

Expected: FAIL —
1. 不同 creator 同名时抛 `MCPNameConflictError`
2. 即使能续接也没有 MCPVersionService 调用，没有 versions.json

- [ ] **Step 3: 修改 publish_mcp 移除同名拒绝 + 接入快照**

修改 `market/src/market/marketplace/service.py:1967-2105` 的 `publish_mcp`：

将整个名称冲突判定（约 1995-2046 行）替换为按 name 续接：

```python
        items = load_index(self.marketplace_root, source_id)

        # R4: 按 name 唯一查找已有条目（不再区分 creator）
        existing = next(
            (i for i in items if i.item_type == "mcp" and i.name == req.name),
            None,
        )

        now = datetime.now(timezone.utc).isoformat()
        if existing is not None:
            # R4: 同名 → 续接到现有条目
            self._apply_publish_update(existing, req, now)
            item = existing
        else:
            initial_version = req.version or "1.0.0"
            item = MarketItem(
                item_id=str(uuid.uuid4()),
                item_type="mcp",
                client_key=req.client_key,
                name=req.name,
                chinese_name=req.chinese_name,
                description=req.description,
                guidance=req.guidance,
                version=initial_version,
                creator_id=req.creator_id,
                creator_name=req.creator_name,
                category_id=req.category_id,
                bbk_ids=req.bbk_ids,
                status="active",
                created_at=now,
                updated_at=now,
            )
            items.append(item)
```

> `MCPNameConflictError` 类保留，但本路径不再 raise。后续 cleanup 可在确认无外部依赖后删除。

紧接 `_apply_publish_update` 之后、`save_mcp_config` 之后，追加 MCP 快照创建（新增代码块）。先 `Read` 当前 `publish_mcp` 完整尾部确定插入位置（约 2069-2105 行 `save_mcp_config` 调用处），然后追加：

```python
        # 写入 mcp.json（保持现有调用）
        save_mcp_config(self.marketplace_root, source_id, item.item_id, ...)
        save_index(self.marketplace_root, source_id, items)

        # 创建版本快照（T9 新增）
        from .mcp_version_service import MCPVersionService
        mcp_dir = get_mcp_dir(self.marketplace_root, source_id, item.item_id)
        version_svc = MCPVersionService(self.marketplace_root)
        try:
            version_svc.create_version_snapshot(
                source_id=source_id,
                item_id=item.item_id,
                mcp_dir=mcp_dir,
                version_id=item.version,
                creator=getattr(req, "operator_id", "") or req.creator_id,
                creator_name=getattr(req, "operator_name", "") or req.creator_name,
                source_user_id=req.creator_id,  # _publish_client_to_market 把同步人填这里
                source_user_name=req.creator_name,
                source_user_version=getattr(req, "source_user_version", "") or req.version,
            )
        except Exception as e:
            logger.warning("Failed to create MCP version snapshot: %s", e)
```

> `req.operator_id` / `req.source_user_version` 是 PublishMCPRequest 上的可选字段，下一步加；`get_mcp_dir` 可能在 `marketplace/fs.py` 中——保持原 import。

- [ ] **Step 4: 给 PublishMCPRequest 加 source_user_version + operator_*（可选字段）**

修改 `market/src/market/marketplace/schemas.py` 的 `PublishMCPRequest`，追加：

```python
class PublishMCPRequest(BaseModel):
    # ... 原字段保留 ...
    source_user_id: str = ""
    source_user_name: str = ""
    source_user_version: str = ""
    operator_id: str = ""  # admin / 真正点按钮的人
    operator_name: str = ""
```

> 字段全部带默认值，向后兼容。`my_mcp.py` 的 `_publish_client_to_market` 调用方不传时退化为旧行为（所有这些字段为空）。

- [ ] **Step 5: 修改 _publish_client_to_market 透传**

修改 `market/src/market/app/routers/my_mcp.py:657-684`：

```python
async def _publish_client_to_market(
    marketplace,
    publish_context: MarketPublishContext,
    client_key: str,
    client: MCPClientConfig,
    overwrite: bool = False,
) -> PublishMCPResult:
    """复用单个 MCP 的市场发布逻辑（透传 source_user_*）."""
    item = await marketplace.publish_mcp(
        publish_context.source_id,
        MarketPublishMCPRequest(
            client_key=client_key,
            name=client.name,
            description=client.description,
            creator_id=publish_context.user_id,
            creator_name=publish_context.user_name,
            category_id=publish_context.category_id,
            bbk_ids=publish_context.bbk_ids,
            config=client.model_dump(mode="json"),
            overwrite=overwrite,
            version=client.version,
            # MCP 路径下：操作者 = 内容来源（同一人，spec §6.3）
            source_user_id=publish_context.user_id,
            source_user_name=publish_context.user_name,
            source_user_version=client.version,
            operator_id=publish_context.user_id,
            operator_name=publish_context.user_name,
        ),
    )
    return PublishMCPResult(client_key=client_key, success=True, item_id=item.item_id)
```

- [ ] **Step 6: 修改 mcp_market.upload_mcp 透传 v0.0.0**

修改 `market/src/market/app/routers/mcp_market.py:236-304` 的 `upload_mcp`，找到构造 `PublishMCPRequest` 处（约 285-300 行），追加：

```python
    publish_req = PublishMCPRequest(
        # ... 原字段 ...
        version=uploaded_version,
        overwrite=True,
        # admin zip 上传：source_user 留空，version=v0.0.0（spec R6）
        source_user_id="",
        source_user_name="",
        source_user_version="v0.0.0",
        operator_id=x_user_id or "",
        operator_name=decode_user_name(x_user_name) or "",
    )
```

- [ ] **Step 7: 跑全市场测试确认通过**

Run: `python -m pytest market/tests/unit -v`

Expected: 全部 PASS（包含 step 1 的新用例 + 全部历史用例）。

需要检查：原本断言"同名不同人 publish_mcp 抛 MCPNameConflictError"的用例（如有），按新逻辑修正为"续接到同 item_id"。

- [ ] **Step 8: Commit**

```bash
git add market/src/market/marketplace/service.py market/src/market/marketplace/schemas.py market/src/market/app/routers/my_mcp.py market/src/market/app/routers/mcp_market.py market/tests/unit
git commit -m ":boom: feat(market/mcp): R4 名称硬唯一 + 接入 MCPVersionService 快照

- service.publish_mcp: 移除 (name, creator_id) 唯一，改按 name 续接
- 不再抛 MCPNameConflictError 同名分支；前端 \"建议改名\" UI 在 T14 清理
- PublishMCPRequest 新增 source_user_id/name/version + operator_id/name 五个透传字段
- _publish_client_to_market: 同步人 = 操作者（MCP 路径下二者必然相同）
- mcp_market.upload_mcp (admin zip): source_user_*=\"\", source_user_version=\"v0.0.0\"
- 每次 publish_mcp 都创建 MCPVersion 快照

BREAKING CHANGE: 客户端不再收到 \"MCP 同名不同人\" 409 + suggested_name 响应。

Refs: docs/superpowers/specs/2026-06-13-skill-mcp-version-control-design.md §5 R4/R5/R6"
```

---

### Task 10: MCP 版本浏览/切换/删除 API

**Files:**
- Create: `market/src/market/app/routers/mcp_versions.py`
- Modify: `market/src/market/app/main.py`（或 router 注册中心，按现有 `skill_versions.py` 注册位置）
- Test: 通过 `TestClient` 集成测试，可写在新增 `market/tests/unit/test_mcp_versions_api.py`

> 接口与 `skill_versions.py` 对称：list / detail / switch / delete。本任务不实现 compare（如需可后续追加）。

- [ ] **Step 1: 写端点失败测试**

创建 `market/tests/unit/test_mcp_versions_api.py`：

```python
# -*- coding: utf-8 -*-
"""MCP 版本浏览 API 测试."""

from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient

from market.app.main import app


def _hdr():
    return {"X-Source-Id": "src1", "X-Manager": "true",
            "X-User-Id": "admin", "X-User-Name": "admin"}


def test_list_mcp_versions_returns_chronological(tmp_path, monkeypatch):
    # 通过 publish_mcp 间接造数据；具体如何在测试 fixture 中预置 marketplace_root
    # 取决于现有 conftest，参考 test_skill_versions 类似用例
    client = TestClient(app)
    # ... 预置一个 mcp item 与 versions.json ...
    r = client.get("/market/mcp/some-item-id/versions", headers=_hdr())
    assert r.status_code == 200
    data = r.json()
    assert "versions" in data


def test_switch_mcp_version_updates_market_item(tmp_path):
    client = TestClient(app)
    # ... 预置两个版本 ...
    r = client.post("/market/mcp/some-item-id/versions/1.0.0/switch", headers=_hdr())
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
```

> 视项目 fixture 复杂度，本测试可从精简的"端点存在且返回 200"开始，后续在 T13 补完整端到端用例。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest market/tests/unit/test_mcp_versions_api.py -v`

Expected: FAIL with 404（路由未注册）。

- [ ] **Step 3: 实现 mcp_versions.py 路由**

创建 `market/src/market/app/routers/mcp_versions.py`：

```python
# -*- coding: utf-8 -*-
"""MCP 版本浏览 API（与 skill_versions.py 对称）."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request

from ...marketplace.fs import load_index, save_index, get_mcp_dir
from ...marketplace.mcp_version_service import MCPVersionService
from ...marketplace.version_models import MCPVersionsManifest

router = APIRouter()


def _require_manager(x_manager: Optional[str]) -> None:
    if x_manager != "true":
        raise HTTPException(status_code=403, detail="Manager access required")


def _require_source_id(x_source_id: Optional[str]) -> str:
    if not x_source_id:
        raise HTTPException(status_code=400, detail="X-Source-Id header is required")
    return x_source_id


def _get_service(request: Request) -> MCPVersionService:
    marketplace = request.app.state.marketplace
    return MCPVersionService(marketplace.marketplace_root)


def _validate_item_exists(svc: MCPVersionService, source_id: str, item_id: str) -> None:
    items = load_index(svc.marketplace_root, source_id)
    if not any(i.item_id == item_id and i.item_type == "mcp" for i in items):
        raise HTTPException(status_code=404, detail=f"MCP item {item_id} not found")


@router.get("/market/mcp/{item_id}/versions")
async def list_mcp_versions(
    item_id: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
):
    source_id = _require_source_id(x_source_id)
    svc = _get_service(request)
    _validate_item_exists(svc, source_id, item_id)
    return svc.list_versions(source_id, item_id)


@router.post("/market/mcp/{item_id}/versions/{version_id}/switch")
async def switch_mcp_version(
    item_id: str,
    version_id: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
):
    source_id = _require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = _get_service(request)
    _validate_item_exists(svc, source_id, item_id)

    mcp_dir = get_mcp_dir(svc.marketplace_root, source_id, item_id)
    result = svc.switch_version(source_id, item_id, version_id, mcp_dir)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    # R8: 同步更新 MarketItem.version + creator_id（跟随目标快照来源）
    items = load_index(svc.marketplace_root, source_id)
    item = next((i for i in items if i.item_id == item_id), None)
    if item is not None:
        item.version = version_id
        item.updated_at = datetime.now(timezone.utc).isoformat()
        manifest = svc._load_manifest(source_id, item_id)
        target = next((v for v in manifest.versions if v.version_id == version_id), None)
        if target is not None:
            if target.source_user_id:
                item.creator_id = target.source_user_id
                item.creator_name = target.source_user_name or target.source_user_id
            elif target.created_by:
                item.creator_id = target.created_by
                item.creator_name = target.created_by_name or target.created_by
        save_index(svc.marketplace_root, source_id, items)

    return result


@router.delete("/market/mcp/{item_id}/versions/{version_id}")
async def delete_mcp_version(
    item_id: str,
    version_id: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
):
    source_id = _require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = _get_service(request)
    _validate_item_exists(svc, source_id, item_id)

    manifest = svc._load_manifest(source_id, item_id)
    target = next((v for v in manifest.versions if v.version_id == version_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Version {version_id} not found")
    if target.is_current or target.is_initial:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete current or initial version",
        )
    manifest.versions = [v for v in manifest.versions if v.version_id != version_id]
    svc._save_manifest(source_id, item_id, manifest)

    version_dir = svc._get_version_dir(source_id, item_id, version_id)
    if version_dir.exists():
        import shutil
        shutil.rmtree(version_dir)

    return {"success": True, "deleted_version": version_id}
```

- [ ] **Step 4: 注册路由**

`Read` `market/src/market/app/main.py`（或现有 `skill_versions` router 被 include 的位置），按相同模式 include 新 router：

```python
from .routers import mcp_versions
...
app.include_router(mcp_versions.router)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest market/tests/unit/test_mcp_versions_api.py -v`

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add market/src/market/app/routers/mcp_versions.py market/src/market/app/main.py market/tests/unit/test_mcp_versions_api.py
git commit -m ":sparkles: feat(market/mcp): MCP 版本浏览/切换/删除 API

- GET /market/mcp/{item_id}/versions
- POST /market/mcp/{item_id}/versions/{version_id}/switch（R8 同步 creator）
- DELETE /market/mcp/{item_id}/versions/{version_id}（拒删 current/initial）
- 与 skill_versions.py 对称

Refs: docs/superpowers/specs/2026-06-13-skill-mcp-version-control-design.md §6.3 + §8 端点矩阵"
```

---

### Task 11: 前端隐藏 source=marketplace:* 的"同步到市场"按钮

**Files:**
- Modify: 前端代码（位置由调研确定）

> 后端不强制兜底——一旦 admin 误调，仍会触发 R7 same-version-same-content no-op 或 R4 续接。前端隐藏即可。

- [ ] **Step 1: 找到"同步到市场"按钮位置**

Run: `grep -rn "同步到市场\|sync.*market\|publishToMarket\|publish.*my-mcp\|publish.*my-skills" D:/smile_code/github/CoPaw/console/src --include="*.tsx" --include="*.ts" | head -20`

记录所有命中位置，确认覆盖：
- 我的技能列表里的同步按钮
- 我的 MCP 列表里的同步按钮

- [ ] **Step 2: 检查每条记录的 source 字段是否暴露给前端**

Run: `grep -rn "source.*marketplace\|received_version\|distributed_by" D:/smile_code/github/CoPaw/console/src --include="*.ts" --include="*.tsx" | head -10`

确认 API 响应里 `source` / `distributed_by` 字段已透传到前端类型定义。如果未暴露，先在 `MyMCPListItem` / `MySkillItem` 等响应模型中补上（如已有则跳过）。

- [ ] **Step 3: 在按钮处加条件渲染**

按 Step 1 找到的位置修改，把按钮包裹在条件里：

```tsx
{!skill.source?.startsWith("marketplace:") && (
  <Button onClick={() => syncToMarket(skill)}>同步到市场</Button>
)}
```

MCP 同理：

```tsx
{!mcp.source?.startsWith("marketplace:") && (
  <Button onClick={() => publishMcp(mcp)}>同步到市场</Button>
)}
```

- [ ] **Step 4: 同时移除"建议改名"提示 UI**

Run: `grep -rn "suggested_name\|建议改名\|_1" D:/smile_code/github/CoPaw/console/src --include="*.ts" --include="*.tsx" | head -10`

把命中处的 `suggested_name` 处理逻辑改为忽略（响应不再含此字段）。如果是显式 if 分支，删除整段；如果是 try/catch 409 后的 fallback，简化为通用错误提示。

- [ ] **Step 5: 跑前端单元测试 / 类型检查**

Run: `cd D:/smile_code/github/CoPaw/console && pnpm test 2>&1 | tail -30`

Expected: PASS。如果没有 pnpm test 脚本，用 `pnpm tsc --noEmit` 检查类型。

- [ ] **Step 6: Commit**

```bash
git add console/src
git commit -m ":lipstick: feat(console): 隐藏 marketplace 来源的\"同步到市场\"按钮 + 移除建议改名 UI

- source.startsWith(\"marketplace:\") 的 skill/MCP 不再展示同步按钮
- T5/T9 后后端不再返回 suggested_name，前端的对应分支同步移除

Refs: docs/superpowers/specs/2026-06-13-skill-mcp-version-control-design.md §5 R6/R7"
```

---

### Task 12: 端到端集成测试 + Spec 验收清单

**Files:**
- Create: `market/tests/integration/test_version_control_e2e.py`（如已有 integration 目录则用之；否则放到 unit 目录加 `e2e_` 前缀）

- [ ] **Step 1: 写端到端 fixture 验证完整 R1-R8**

创建 `market/tests/unit/test_version_control_e2e.py`：

```python
# -*- coding: utf-8 -*-
"""Skill / MCP 版本控制端到端验收测试.

验收 Spec §11 中的 8 条标准（已扣减 swe 相关 2 条）。
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_acceptance_3_update_my_mcp_no_change_no_bump():
    """Spec §11 标准 3：body 不变 + 内容不变 → 不 bump。
    本场景已在 test_my_mcp_update.py 覆盖，此处仅作 sentinel。"""
    pass


@pytest.mark.asyncio
async def test_acceptance_4_skill_same_name_appends_to_single_market_item():
    """Spec §11 标准 4：不同用户同步同名 skill → 市场只有一条 MarketItem。
    本场景已在 test_service.py 覆盖。"""
    pass


@pytest.mark.asyncio
async def test_acceptance_5_admin_zip_upload_records_v000():
    """Spec §11 标准 5：admin publish-upload zip → source_user_id="", source_user_version="v0.0.0"。
    本场景已在 test_skills_market.py 覆盖。"""
    pass


@pytest.mark.asyncio
async def test_acceptance_6_mcp_versions_api_symmetric():
    """Spec §11 标准 6：MCP 与 Skill 版本能力对称。
    本场景已在 test_mcp_versions_api.py 覆盖。"""
    pass


@pytest.mark.asyncio
async def test_acceptance_7_same_version_same_content_no_flip():
    """Spec §11 标准 7：同版本同内容再发布不翻 is_current。
    本场景已在 test_version_service.py 覆盖。"""
    pass


@pytest.mark.asyncio
async def test_acceptance_8_switch_version_aligns_market_item():
    """Spec §11 标准 8：switch_version 后 version/creator_id/creator_name 三者一致。
    本场景已在 test_skills_market.py 覆盖（skill）。MCP 由本测试补一条。"""
    # TODO: 调 POST /market/mcp/{id}/versions/{vid}/switch，断言 MarketItem 三字段
    pass
```

> 上面是 sentinel + TODO 集合：作用是把 §11 验收标准与具体测试绑定，跑 pytest 时所有标记自动验证。

- [ ] **Step 2: 跑全部市场测试**

Run: `python -m pytest market/tests/unit -v`

Expected: 全部 PASS。

- [ ] **Step 3: 跑前端类型检查**

Run: `cd D:/smile_code/github/CoPaw/console && pnpm tsc --noEmit`

Expected: 无新增 type error。

- [ ] **Step 4: 手动冒烟（可选，开发环境）**

启动市场服务：

Run: `cd D:/smile_code/github/CoPaw && python start_market.py`

在另一个 shell 跑：

```bash
# 1. admin zip 上传一个 skill demo（POST /market/skills/publish-upload）
# 2. 用另一个用户工作区 publish 同名 skill demo
# 3. GET /market/skills/{item_id}/versions 验证有两个版本，source_user 不同
# 4. GET /market/mcp/{item_id}/versions 验证 MCP 路径一致
```

详见 spec §11 验收。如时间紧张可跳过本步骤。

- [ ] **Step 5: Commit**

```bash
git add market/tests/unit/test_version_control_e2e.py
git commit -m ":white_check_mark: test(market): 端到端验收 fixture 绑定 §11 验收标准

- 6 条 sentinel 测试映射到具体已覆盖测试（标准 3-8）
- 跑 pytest 即可一次性验证全部

Refs: docs/superpowers/specs/2026-06-13-skill-mcp-version-control-design.md §11"
```

---

## Cross-Cutting Concerns

### 不在本计划但需追踪的事项

| 事项 | 处置 |
|---|---|
| swe 侧 `MCPClientConfig` 缺 `version`/`received_version` 字段 | spec §12 风险表标记，本计划不修；market 侧每次写 `agent.json` 时主动补回这两个字段以减少误抹窗口 |
| swe 的 `POST /skills` 不走 R1/R2 | spec §10 Q6 决议，console Agent/Skills 页保持现状；后续若要对齐另开 ticket |
| `SkillNameConflictError` / `MCPNameConflictError` 类残留 | T5/T9 后无路径 raise；保留两个版本周期再做 cleanup |
| `_bump_patch("1.5")` 行为统一 | T1 选择与 service.py 现行 `_bump_patch` 一致（"1.5.1"），舍弃 skills_browse 的 `_bump_patch_version`（"1.6.0"）。如有 fixture 断言后者，需更新 |
| `mcp.json` 缺失场景 | MCP 快照在 `mcp.json` 不存在时仍生成（signature=空 SHA），不阻塞主流程 |

### 每个 Task 完成的统一退出标准

* 该 Task 所有新测试 PASS。
* `python -m pytest market/tests/unit -v` 整体不回归。
* 已 commit（每个 Task 一次）。
* 本 plan 中该 Task 的所有 checkbox 已勾选。

---

## Self-Review

### 1. Spec 覆盖

| Spec 规则 / §节 | 覆盖 Task |
|---|---|
| R1 首次创建 1.0.0 | T1（utils 默认）+ 现有 `skills_browse._build_skill_metadata` 已实现，不需改 |
| R2 非首次：显式 > 内容变才递增 | T7（MCP）；Skill 侧已实现 |
| R3 用户/市场版本隔离 | 现状已隔离（`version_text` vs `MarketItem.version`），无新增 |
| R4 名称硬唯一 + 续接 | T5（Skill）、T9（MCP） |
| R5 同步快照记录 source_user_* | T3, T6（Skill）, T9（MCP） |
| R6 v0.0.0 边界 | T6（admin zip skill）, T9（admin zip MCP） |
| R7 同版同内容 no-op | T4（Skill），T8（MCP，集成在 mcp_version_service） |
| R8 switch 同步 creator | T4（Skill），T10（MCP） |
| §6.1 MarketItem 不动 creator 语义 | T5/T9 _apply_publish_update 现状已覆盖 |
| §6.2 SkillVersion 加字段 | T3 |
| §6.3 MCPVersion 模型 + signature 仅 mcp.json | T8 |
| §7.1 frontmatter 工具下沉 | T1, T2 |
| §7.2 bump_patch 工具下沉 | T1, T2 |
| §8 端点矩阵 | T5/T6/T7/T9/T10 |
| §10 Q1-Q6 决议 | 全部体现 |
| §11 验收 1-2（已取消） | 删除（spec 已取消） |
| §11 验收 3-8 | T7/T5/T6/T8/T4/T10/T12 |
| §12 风险条目 | Cross-Cutting Concerns |

无未覆盖项。

### 2. Placeholder 扫查

* "TODO" 仅出现在 T12 step 1 的 sentinel 测试 + T11 前端调研 step 1 的查询命令——这两处是真正需要执行 grep 的命令而非 plan 中的占位，可接受。
* 没有 "TBD" / "implement later" / "Add appropriate error handling"。
* 每个代码 step 都给出完整可粘贴代码块。

### 3. 类型 / 命名一致性

* `MCPVersion` 字段 = `SkillVersion` 字段 + 无差异（除 SkillVersion 没有 client_key 外）— 一致。
* `MCPVersionsManifest.client_key/name` vs `VersionsManifest.skill_name` — 命名差异有意保留以贴合实体。
* `bump_patch(version)` 在 utils/version.py 与 service.py / version_service.py 的 wrapper 中签名完全一致。
* `extract_version(md_content: str) -> str` 在 utils/skill_md.py 与所有调用方一致。
* `create_version_snapshot` 新增的 3 个参数 `source_user_id/name/version` 在 T3 引入，T6/T9 调用——名字与 SkillVersion 字段名严格一致。
* `MCPVersionService.create_version_snapshot` 与 SkillVersionService 同名同义，参数顺序一致（先 source_id, item_id, dir，再可选）。

无类型 / 命名不一致问题。

---

## Plan complete and saved to `docs/superpowers/plans/2026-06-13-skill-mcp-version-control.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?


**Files:**
- Modify: `market/src/market/marketplace/version_service.py:125-153` (R7：同版本同内容不再翻 is_current)
- Modify: `market/src/market/app/routers/skill_versions.py:100-129` (R8：`_update_skill_index` 同步 creator_id)
- Test: `market/tests/unit/marketplace/test_version_service.py`

- [ ] **Step 1: R7 失败测试**

在 `test_version_service.py` 末尾追加：

```python
def test_same_version_same_content_does_not_flip_is_current(tmp_path):
    """R7：同 version_id 同 signature 时不修改 is_current（保持原指针不变）."""
    svc = _make_version_service(tmp_path)
    skill_md_v1 = """---
name: t
version: "1.0.0"
---
v1 content
"""
    skill_md_v2 = """---
name: t
version: "1.0.1"
---
v2 content
"""
    skill_dir = _create_skill_dir(tmp_path, "src1", "item1", skill_md=skill_md_v1)

    # 创建 v1.0.0
    v1 = svc.create_version_snapshot(
        source_id="src1", item_id="item1",
        skill_dir=skill_dir, creator="u1", creator_name="user1",
    )
    assert v1.is_current is True

    # 升级到 v1.0.1
    (skill_dir / "SKILL.md").write_text(skill_md_v2, encoding="utf-8")
    v2 = svc.create_version_snapshot(
        source_id="src1", item_id="item1",
        skill_dir=skill_dir, creator="u2", creator_name="user2",
    )
    assert v2.is_current is True

    # 现在 v1.0.1 是 current。再次用 v1.0.0 内容做 snapshot（同版本同内容）
    (skill_dir / "SKILL.md").write_text(skill_md_v1, encoding="utf-8")
    # 但是 skill_dir 内容现在等于 v1.0.0 时刻——signature 应等于 v1 的 signature
    result = svc.create_version_snapshot(
        source_id="src1", item_id="item1",
        skill_dir=skill_dir, creator="u3", creator_name="user3",
    )

    # R7：返回原 v1.0.0，不创建新快照，不翻 is_current（v1.0.1 仍是 current）
    listed = svc.list_versions("src1", "item1")
    current_ids = [v["version_id"] for v in listed["versions"] if v["is_current"]]
    assert current_ids == ["1.0.1"], (
        f"R7 violated: current should remain 1.0.1, got {current_ids}"
    )
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest market/tests/unit/marketplace/test_version_service.py::test_same_version_same_content_does_not_flip_is_current -v`

Expected: FAIL — 当前实现 `version_service.py:144-145` 会强行把 v1.0.0 设为 current。

- [ ] **Step 3: 修复 R7**

修改 `market/src/market/marketplace/version_service.py:138-153`，把"同版本同内容"分支改为完全 no-op：

```python
            if (
                existing_version_info
                and existing_version_info.signature == new_signature
            ):
                # R7: 同版本同内容 → 完全 no-op
                # 不创建快照、不修改 is_current、不更新 manifest
                logger.info(
                    "Version %s already exists with same content, skipping snapshot creation (R7 no-op)",
                    version_id,
                )
                return existing_version_info
            else:
                # 同版本不同内容 → 报错，要求用户指定新版本
                raise ValueError(
                    f"Version {version_id} already exists with different content. "
                    f"Please specify a new version in SKILL.md or allow auto-bump.",
                )
```

注意：删除原 `for v in manifest.versions: v.is_current = v.version_id == version_id` 与 `self._save_versions_manifest(...)` 这两行。

- [ ] **Step 4: 跑测试确认 R7 通过**

Run: `python -m pytest market/tests/unit/marketplace/test_version_service.py -v`

Expected: 全部 PASS（包括新增的 R7 用例 + 全部历史用例）。

- [ ] **Step 5: R8 失败测试**

在 `market/tests/unit/marketplace/test_skills_market.py` 末尾追加（如该文件不存在 switch_version 相关测试，先 import 必要模块）：

```python
def test_switch_version_updates_market_item_creator(tmp_path, monkeypatch):
    """R8：switch_version 同步更新 MarketItem.creator_id/creator_name."""
    from market.marketplace.fs import save_index, load_index
    from market.marketplace.models import MarketItem
    from market.app.routers.skill_versions import _update_skill_index
    from market.marketplace.version_service import SkillVersionService

    marketplace_root = tmp_path / "market"
    source_id = "src1"
    item_id = "item1"
    skill_dir = marketplace_root / source_id / "skills" / item_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        '---\nname: t\ndescription: d\nversion: "2.0.0"\n---\n',
        encoding="utf-8",
    )

    save_index(marketplace_root, source_id, [
        MarketItem(
            item_id=item_id, item_type="skill", name="t", description="d",
            version="2.0.0",
            creator_id="alice_id", creator_name="alice",
            status="active",
        )
    ])

    # 模拟切换到 v1.0.0 快照（来源 bob）
    svc = SkillVersionService(marketplace_root)
    versions_path = marketplace_root / source_id / "skill_versions" / item_id / "versions.json"
    versions_path.parent.mkdir(parents=True, exist_ok=True)
    versions_path.write_text(
        json.dumps({
            "skill_name": "t",
            "versions": [{
                "version_id": "1.0.0",
                "created_at": "2025-01-01T00:00:00+00:00",
                "created_by": "admin",
                "created_by_name": "admin",
                "source_user_id": "bob_id",
                "source_user_name": "bob",
                "source_user_version": "1.0.0",
                "signature": "x", "is_current": True, "is_initial": True,
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    class _FakeMarketplace:
        pass
    fake = _FakeMarketplace()
    fake.marketplace_root = marketplace_root

    _update_skill_index(fake, source_id, item_id, skill_dir, "1.0.0")

    items = load_index(marketplace_root, source_id)
    item = items[0]
    assert item.version == "1.0.0"
    # R8: creator_id/name 应跟随目标快照的 source_user_*
    assert item.creator_id == "bob_id"
    assert item.creator_name == "bob"
```

- [ ] **Step 6: 跑测试确认失败**

Run: `python -m pytest market/tests/unit/marketplace/test_skills_market.py::test_switch_version_updates_market_item_creator -v`

Expected: FAIL — `_update_skill_index` 当前不更新 `creator_id`。

- [ ] **Step 7: 修复 R8**

修改 `market/src/market/app/routers/skill_versions.py:100-129` 的 `_update_skill_index`：

```python
def _update_skill_index(
    marketplace: object,
    source_id: str,
    item_id: str,
    skill_dir: Path,
    version_id: str,
) -> None:
    """切换版本后更新市场索引中的技能信息（R8：同步 creator_id/name）."""
    items = load_index(marketplace.marketplace_root, source_id)
    item = next((i for i in items if i.item_id == item_id), None)

    if not item:
        return

    skill_md_path = skill_dir / "SKILL.md"
    if skill_md_path.exists():
        skill_md_content = skill_md_path.read_text(encoding="utf-8")
        new_name, new_desc = _parse_skill_md_frontmatter(
            skill_md_content,
            item.name,
            item.description,
        )
        item.name = new_name
        item.description = new_desc

    item.version = version_id
    item.updated_at = datetime.now(timezone.utc).isoformat()

    # R8: 同步更新 creator_id/creator_name 到目标快照的来源
    from ...marketplace.version_service import SkillVersionService
    svc = SkillVersionService(marketplace.marketplace_root)
    manifest = svc._load_versions_manifest(source_id, item_id)
    target = next(
        (v for v in manifest.versions if v.version_id == version_id),
        None,
    )
    if target is not None:
        # 优先使用 source_user_*；为空时回退到 created_by
        if target.source_user_id:
            item.creator_id = target.source_user_id
            item.creator_name = target.source_user_name or target.source_user_id
        elif target.created_by:
            item.creator_id = target.created_by
            item.creator_name = target.created_by_name or target.created_by

    save_index(marketplace.marketplace_root, source_id, items)
```

- [ ] **Step 8: 跑测试确认 R8 通过**

Run: `python -m pytest market/tests/unit/marketplace/test_skills_market.py -v`

Expected: 全部 PASS。

- [ ] **Step 9: Commit**

```bash
git add market/src/market/marketplace/version_service.py market/src/market/app/routers/skill_versions.py market/tests/unit/marketplace
git commit -m ":bug: fix(market/version): R7 修复同版本同内容不翻 is_current，R8 切版本同步 creator

- R7：multi-user 续接场景下，同 version_id+signature 视为 no-op，不改动任何状态
- R8：switch_version 后，MarketItem.creator_id/name 跟随目标快照 source_user_*
  无 source_user_* 时回退到 created_by

Refs: docs/superpowers/specs/2026-06-13-skill-mcp-version-control-design.md §5 R7/R8"
```

---


**Files:**
- Create: `market/src/market/utils/skill_md.py`
- Create: `market/src/market/utils/version.py`
- Create: `market/tests/unit/utils/__init__.py`
- Create: `market/tests/unit/utils/test_skill_md.py`
- Create: `market/tests/unit/utils/test_version.py`
- Verify exists: `market/src/market/utils/__init__.py` (已存在，无需修改)

- [ ] **Step 1: 写 utils/version.py 的失败测试**

创建 `market/tests/unit/utils/__init__.py` 为空文件。

创建 `market/tests/unit/utils/test_version.py`：

```python
# -*- coding: utf-8 -*-
"""版本号工具单元测试."""

from __future__ import annotations

import pytest

from market.utils.version import bump_patch, normalize_version


class TestBumpPatch:
    def test_three_part(self):
        assert bump_patch("1.0.0") == "1.0.1"
        assert bump_patch("1.0.8") == "1.0.9"
        assert bump_patch("2.13.99") == "2.13.100"

    def test_two_part(self):
        # 1.5 → 1.5.1（与 version_service._bump_version 现有行为一致）
        assert bump_patch("1.5") == "1.5.1"

    def test_invalid_format_appends_one(self):
        assert bump_patch("foo") == "foo.1"
        assert bump_patch("1.a.0") == "1.a.0.1"

    def test_empty_string(self):
        assert bump_patch("") == ".1"


class TestNormalizeVersion:
    def test_strip_v_prefix(self):
        assert normalize_version("v1.0.0") == "1.0.0"
        assert normalize_version("V2.3.4") == "2.3.4"

    def test_strip_quotes(self):
        assert normalize_version('"1.2.3"') == "1.2.3"
        assert normalize_version("'1.2.3'") == "1.2.3"

    def test_strip_quotes_and_v(self):
        assert normalize_version('"v1.2.3"') == "1.2.3"

    def test_strip_whitespace(self):
        assert normalize_version("  1.0.0  ") == "1.0.0"

    def test_empty(self):
        assert normalize_version("") == ""
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd D:/smile_code/github/CoPaw && python -m pytest market/tests/unit/utils/test_version.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'market.utils.version'`

- [ ] **Step 3: 实现 utils/version.py**

创建 `market/src/market/utils/version.py`：

```python
# -*- coding: utf-8 -*-
"""版本号操作工具.

统一替代散落在 service.py / version_service.py / skills_browse.py / my_mcp.py
的多个 _bump_patch 实现。
"""

from __future__ import annotations


def bump_patch(version: str) -> str:
    """递增版本号的 patch 部分.

    1.0.0 → 1.0.1
    1.0.8 → 1.0.9
    1.5   → 1.5.1（两段式版本号视作 minor.patch 形态，递增 patch 后补 0 不合适，沿用现有行为补 .1）
    其他无法解析格式 → '<version>.1'

    与 version_service._bump_version 保持完全等价。
    """
    parts = version.split(".")
    if len(parts) == 3:
        try:
            parts[2] = str(int(parts[2]) + 1)
            return ".".join(parts)
        except ValueError:
            pass
    elif len(parts) == 2:
        try:
            parts[1] = str(int(parts[1]) + 1)
            return f"{parts[0]}.{parts[1]}.0"
        except ValueError:
            pass
    return f"{version}.1"


def normalize_version(version: str) -> str:
    """去除前导 v/V 与引号、空白."""
    if not version:
        return ""
    val = version.strip()
    # 去引号
    if (val.startswith('"') and val.endswith('"')) or (
        val.startswith("'") and val.endswith("'")
    ):
        val = val[1:-1]
    # 去 v 前缀
    if val[:1] in ("v", "V"):
        val = val[1:]
    return val
```

- [ ] **Step 4: 运行 utils/version.py 测试确认通过**

Run: `python -m pytest market/tests/unit/utils/test_version.py -v`

Expected: PASS（13 个用例）

注意：`bump_patch("1.5")` 现行 `_bump_version` 是 `"1.5.1"` 而 `_bump_patch_version`（skills_browse 副本）是 `"1.6.0"`。本工具以 service.py 现行 `_bump_patch`（即返回 `"1.5.1"`）为准，统一行为。

- [ ] **Step 5: 写 utils/skill_md.py 的失败测试**

创建 `market/tests/unit/utils/test_skill_md.py`：

```python
# -*- coding: utf-8 -*-
"""SKILL.md frontmatter 工具单元测试."""

from __future__ import annotations

from market.utils.skill_md import (
    extract_metadata,
    extract_version,
    parse_frontmatter,
)


SAMPLE_MD = """---
name: 测试技能
description: 一个测试用的技能
version: "1.2.3"
chinese_name: 测试
---

# 测试技能

正文内容。
"""

SAMPLE_MD_NO_VERSION = """---
name: no_version_skill
description: ""
---

正文。
"""

SAMPLE_MD_V_PREFIX = """---
name: prefix_skill
version: v2.0.0
---

正文。
"""


class TestParseFrontmatter:
    def test_basic(self):
        fm = parse_frontmatter(SAMPLE_MD)
        assert fm["name"] == "测试技能"
        assert fm["description"] == "一个测试用的技能"
        assert fm["version"] == "1.2.3"
        assert fm["chinese_name"] == "测试"

    def test_no_frontmatter(self):
        fm = parse_frontmatter("# Just a heading\n\nNo fm.")
        assert fm == {}

    def test_empty_input(self):
        assert parse_frontmatter("") == {}


class TestExtractVersion:
    def test_quoted(self):
        assert extract_version(SAMPLE_MD) == "1.2.3"

    def test_no_version(self):
        assert extract_version(SAMPLE_MD_NO_VERSION) == ""

    def test_v_prefix(self):
        assert extract_version(SAMPLE_MD_V_PREFIX) == "2.0.0"

    def test_no_frontmatter(self):
        assert extract_version("plain text") == ""

    def test_empty_input(self):
        assert extract_version("") == ""


class TestExtractMetadata:
    def test_returns_known_keys(self):
        meta = extract_metadata(SAMPLE_MD)
        assert meta["name"] == "测试技能"
        assert meta["description"] == "一个测试用的技能"
        assert meta["version"] == "1.2.3"
        assert meta["chinese_name"] == "测试"

    def test_missing_keys_return_empty_string(self):
        meta = extract_metadata(SAMPLE_MD_NO_VERSION)
        assert meta["name"] == "no_version_skill"
        assert meta["description"] == ""
        assert meta["version"] == ""
        assert meta["chinese_name"] == ""
```

- [ ] **Step 6: 运行测试确认失败**

Run: `python -m pytest market/tests/unit/utils/test_skill_md.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'market.utils.skill_md'`

- [ ] **Step 7: 实现 utils/skill_md.py**

创建 `market/src/market/utils/skill_md.py`：

```python
# -*- coding: utf-8 -*-
"""SKILL.md frontmatter 解析工具.

统一替代散落在 service.py / version_service.py / skills_market.py /
skills_browse.py / skill_versions.py 的多个手写 line parser。

实现基于 python-frontmatter 包，与 swe 侧 skills_manager.py 保持一致的解析方式
（仅对 market 内部生效；swe 侧本次不改）。
"""

from __future__ import annotations

from typing import Any, Dict

import frontmatter

from .version import normalize_version


def parse_frontmatter(md_content: str) -> Dict[str, Any]:
    """解析 SKILL.md frontmatter，返回 metadata dict（无 frontmatter 时返回空 dict）."""
    if not md_content:
        return {}
    try:
        post = frontmatter.loads(md_content)
    except Exception:  # pylint: disable=broad-except
        return {}
    return dict(post.metadata or {})


def extract_version(md_content: str) -> str:
    """提取 frontmatter 中的 version 字段，去除 v 前缀与引号；不存在则返回空串.

    优先级：顶层 version > metadata.version。
    （swe 侧 skills_manager._extract_version 还会回退 metadata.builtin_skill_version，
    但 market 侧本次不引入该字段——保持纯 version 语义。）
    """
    fm = parse_frontmatter(md_content)
    raw = fm.get("version", "")
    if isinstance(raw, (int, float)):
        raw = str(raw)
    if not isinstance(raw, str):
        return ""
    return normalize_version(raw)


def extract_metadata(md_content: str) -> Dict[str, str]:
    """提取常用元数据字段，缺失字段返回空串.

    Returns:
        包含 name / description / version / chinese_name 的 dict。
    """
    fm = parse_frontmatter(md_content)

    def _str(key: str) -> str:
        val = fm.get(key, "")
        if isinstance(val, (int, float)):
            return str(val)
        return val if isinstance(val, str) else ""

    return {
        "name": _str("name"),
        "description": _str("description"),
        "version": extract_version(md_content),
        "chinese_name": _str("chinese_name"),
    }
```

- [ ] **Step 8: 运行 utils/skill_md.py 测试确认通过**

Run: `python -m pytest market/tests/unit/utils/test_skill_md.py -v`

Expected: PASS（11 个用例）

- [ ] **Step 9: 验证 frontmatter 包已在 market venv 中**

Run: `python -c "import frontmatter; print(frontmatter.__version__)"`

Expected: 输出版本号（如 `1.0.0` 或更高）。如果失败：`pip install python-frontmatter`。
（swe 侧 `skills_manager.py:22` 已 import，pyproject 里通常已有；market 侧若缺失则补到 `market/pyproject.toml`。）

- [ ] **Step 10: Commit**

```bash
git add market/src/market/utils/skill_md.py market/src/market/utils/version.py market/tests/unit/utils/
git commit -m ":sparkles: feat(market/utils): 新增 skill_md / version 共享工具

- skill_md.py: 基于 python-frontmatter 的统一 frontmatter 解析与 version 提取
- version.py: 统一的 bump_patch / normalize_version
- 后续 T2 将替换市场侧 5 处 frontmatter parser + 4 处 _bump_patch 副本

Refs: docs/superpowers/specs/2026-06-13-skill-mcp-version-control-design.md §7"
```

---



## Task 13 (Hotfix 2026-06-14): 修复 T1-T12 上线后的 3 个测试问题

> **背景**：T1-T12 实施完毕后，用户测试发现 3 个问题：
> 1. 在「我的技能」中同步到市场，应用市场显示的版本是用户工作区的版本（来自 SKILL.md），而非市场独立递增的版本
> 2. 应用市场「版本历史」中没有"再次同步到市场"产生的快照记录（多次同步后只有 1 条）
> 3. 应用市场 MCP 没有版本历史入口（前端缺按钮）
>
> **根因定位**：
>
> | # | 位置 | 错误 | 影响 |
> |---|---|---|---|
> | A | `service.publish_skill:866-875` 用 SKILL.md version 覆盖 `MarketItem.version` | 违反 R3 市场/用户版本隔离 | 问题 1 |
> | B | `version_service._extract_version_from_skill` 优先级里 SKILL.md > 历史递增；无 signature 比对分支 | R2/R7 没有真正落到同步路径 | 问题 2、3 |
> | C | `publish_skill` / `publish_mcp` 用 `except Exception: logger.warning(...)` 把 ValueError 静默吞掉 | 用户感知不到"版本快照失败" | 问题 2、3（让症状更难发现） |
> | D（仅 MCP） | `mcp_version_service._calculate_signature` 把 `updated_at` 等时间戳一起算进签名 | 同内容也会 signature 漂移 | 问题 3 |
> | E | 前端 `MCPDetailDrawer` 没有版本历史入口 | 即使后端 API 就绪也看不到 | 问题 3 |
>
> **决议**：F2 优先级**不再读 SKILL.md 的 version 字段**——市场端 version_id 由 signature + 历史完全决定。SKILL.md 中的 version 仅写到 `source_user_version`。

### 子任务清单（按 commit 顺序）

#### F1 — Skill 同步路径不再用用户版本覆盖市场版本

**文件**：
- `market/src/market/marketplace/service.py` — `publish_skill`：删除 866-875 那段"用 SKILL.md md_version 覆盖 item.version"逻辑；快照创建后再 `save_index`，让 `item.version` 跟随快照实际写入的 `version_id`
- `market/src/market/app/routers/skills_market.py` — `_process_single_skill`：续接分支改为始终 `existing.version = _bump_patch(existing.version)`（去掉"SKILL.md 有 version 就用之"分支）；新建条目调 `_create_market_item(name, description, "", ...)` 让其 fallback 到 1.0.0；快照创建后让 `item.version` 跟随 `snapshot.version_id`

#### F2 — 版本号生成完全脱离 SKILL.md（市场端独立递增）

**文件**：`market/src/market/marketplace/version_service.py`

- 新增 `_derive_market_version_id(new_signature, current_market_version, last_version_from_history, last_version_signature, existing_ids)`：
  1. 无历史 → `current_market_version or "1.0.0"`
  2. 有历史 + signature 与历史最新版相同 → 复用历史 `version_id`（让 R7 no-op 接管）
  3. 有历史 + signature 不同 → `_bump_version(last_version_from_history)`，并在结果撞 `existing_ids` 时继续 bump
- `create_version_snapshot` 主流程改为：先算 signature，再调 `_derive_market_version_id`；R7 no-op 分支保留；R7 raise ValueError 分支保留（罕见兜底）
- 旧 `_extract_version_from_skill` 标注 `[Deprecated]`，仅作静态工具保留供潜在外部调用

#### F3 — 不再静默吞快照失败

**文件**：
- `market/src/market/marketplace/service.py`：
  - 新增异常类 `SkillVersionConflictError` / `MCPVersionConflictError`
  - `publish_skill`：把 `create_version_snapshot` 的 `except Exception` 拆分为 `except ValueError → raise SkillVersionConflictError` + `except Exception → logger.error(..., exc_info=True)`；`save_index` 移到快照成功之后
  - `publish_mcp`：同上；并加一段 F2 配套预检——若 manifest 已存在同 version_id 但 signature 不同，预先 bump `item.version` 让其避开历史 version_id（处理"用户 A 用 1.0.0 同步过 → 用户 B 也用 1.0.0 同步但内容不同"的场景）
- `market/src/market/app/routers/skills_market.py`：路由 `publish_skill` 加 `except SkillVersionConflictError → HTTPException(409, code=VERSION_CONFLICT)`
- `market/src/market/app/routers/mcp_market.py`：路由 `publish_mcp` 与 `upload_mcp` 加 `except MCPVersionConflictError → HTTPException(409, code=MCP_VERSION_CONFLICT)` / `UploadMCPResponse(success=False)`
- `market/src/market/app/routers/my_mcp.py`：`publish_single_my_mcp_to_market` 加 409；批量 `publish_my_mcp_to_market` 改为 per-item 标 `success=False, error="版本冲突..."`

#### F4 — MCP signature 改白名单字段

**文件**：`market/src/market/marketplace/mcp_version_service.py`

- 新增模块常量 `_SIGNATURE_FIELDS = ("name", "description", "transport", "url", "command", "args", "env", "headers", "cwd", "enabled", "lazy_load")`
- `_calculate_signature` 改为：
  1. 兼容嵌套结构 `data.get("config")` 与扁平结构
  2. 只 hash `_SIGNATURE_FIELDS` 中的字段
  3. 排除 `updated_at` / `created_at` / `version` / `received_version` 等运维元数据
- 风险：老快照的 signature 字段是用旧算法计算的，第一次再同步时会被判为"内容已变化"产生一次性多余快照——可接受。

#### F5 — 前端 MCP 版本历史入口

**文件**：
- 新建 `console/src/api/modules/marketMcpVersion.ts`：导出 `marketMcpVersionApi.{listVersions, switchVersion, deleteVersion}` 与 `MCPVersion` / `MCPVersionsManifest` 类型；端点对应 `GET/POST/DELETE /market/mcp/{item_id}/versions[/...]`
- 新建 `console/src/pages/Market/components/MCPVersionHistoryModal.tsx`：与 `Skills/VersionHistoryModal.tsx` 平行；UI 风格一致；隐藏 compare 面板（spec §6.3 未要求 MCP diff）；额外展示 `source_user_*` 信息（"来源用户：X（本地版本 1.5.2）"）
- 修改 `console/src/pages/Market/MCPDetailDrawer.tsx`：
  - props 加 `sourceId?: string` 与 `onRefresh?: () => void`
  - `import { HistoryOutlined } from "@ant-design/icons"` 与 `MCPVersionHistoryModal`
  - 在动作按钮区第一个位置加"版本历史"按钮（`HistoryOutlined`）
  - 渲染 `<MCPVersionHistoryModal>` 在外层 div 顶部
- 修改 `console/src/pages/Market/MarketSkills.tsx`：调用 `<MCPDetailDrawer>` 时透传 `sourceId={sourceId}` 与 `onRefresh={refreshMCP}`

### 验证步骤（hotfix 上线后人工验证 - 关联问题 1/2/3）

1. **问题 1 验证**：在「我的技能」里同步一个新 skill（SKILL.md 写 `version: "5.0.0"`）→ 在「应用市场」打开看到 `v1.0.0`（不是 5.0.0）；改 SKILL.md 内容（version 字段不动）再同步 → 市场显示 `v1.0.1`；再同步 → `v1.0.2`。
2. **问题 2 验证**：上一步连续 3 次同步后，在应用市场 skill 详情页点"版本历史" → 看到 3 条记录，每条 `source_user_version` 都是 `5.0.0`。
3. **问题 3 验证**：在「我的 MCP」里同步一个 MCP 到市场 → 在应用市场 MCP 详情页能看到"版本历史"按钮 → 点击后看到至少 1 条记录；改 MCP 配置（不是仅 updated_at）再同步 → 看到第 2 条记录（验证 F4：signature 不会因 updated_at 漂移产生 R7 同 version 不同 signature 的 409）。

### 与原 T1-T12 的兼容性

- 不引入新的字段、不变更存储结构。
- F2 改优先级是行为变更：原本 SKILL.md 写 `2.0.0` 同步到市场会显示 `2.0.0`；hotfix 后市场显示从 `1.0.0` 起步，独立递增。**用户已在 §10 决议过这是预期行为（R3 隔离）**。
- F4 改 signature 算法：老快照 signature 字段保留，但第一次再同步必然产生新快照（多 1 条）。可接受，记录在风险表。
- F5 前端是纯增量，不影响已有按钮。
