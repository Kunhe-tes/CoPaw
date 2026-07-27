# -*- coding: utf-8 -*-
"""Trusted resolution of Console-selected skills for one agent turn."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape

import frontmatter

from ...agents.skills_manager import (
    resolve_effective_skill_dir,
    resolve_effective_skills,
)


@dataclass(frozen=True)
class SkillUseDirective:
    name: str
    description: str
    path: Path

    def render(self) -> str:
        return f"""<SKILL-USE-V1>
<instruction>
用户显式选择了下面 <name> 指定的技能。请先使用 read_file 工具读取 <path> 指定的 SKILL.md 文件。读取后必须严格按照该技能说明执行本轮任务：
- 不要跳过任何步骤，也不要把步骤改写成泛化或概括的回答；
- 不要重复询问技能文档中已经明确给出的内容；
- 不要凭猜测代替技能中明确的指令；
- 技能文档中提到的相对脚本、资源、模板路径，都必须按 <path> 指定的 SKILL.md 所在目录解析；执行脚本时请使用绝对路径，或把 cwd 设置为该技能目录；
- 始终使用中文回答。
</instruction>
<name>{escape(self.name)}</name>
<description>{escape(self.description)}</description>
<path>{escape(str(self.path))}</path>
</SKILL-USE-V1>"""


def build_skill_use_directives(
    *,
    workspace_dir: Path,
    channel: str,
    selected_skill_names: Iterable[object],
) -> list[SkillUseDirective]:
    """Resolve selected names to readable effective skills."""
    effective_names = set(resolve_effective_skills(workspace_dir, channel))
    directives: list[SkillUseDirective] = []
    seen: set[str] = set()

    for raw_name in selected_skill_names:
        if not isinstance(raw_name, str):
            continue
        name = raw_name.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        if name not in effective_names:
            continue
        skill_dir = resolve_effective_skill_dir(workspace_dir, name)
        skill_path = skill_dir / "SKILL.md" if skill_dir is not None else None
        if skill_path is None or not skill_path.is_file():
            continue
        try:
            content = skill_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        try:
            description = str(
                frontmatter.loads(content).get("description") or "",
            )
        except (ValueError, TypeError):
            description = ""
        directives.append(
            SkillUseDirective(
                name=name,
                description=description,
                path=skill_path.resolve(),
            ),
        )

    return directives
