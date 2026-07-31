#!/usr/bin/env python3
"""Render a validated W+ SOP specification as a Markdown file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def render_md(data: dict[str, Any]) -> str:
    lines = [
        f"# {data.get('title', 'W+ SOP')}",
        "",
        f"**触发场景**: {data.get('trigger', '')}",
        "",
        f"**执行角色**: {data.get('actor', '')}",
        "",
        f"**请求摘要**: {data.get('request_summary', '')}",
        "",
        f"**状态**: {'✅ 完成' if data.get('status') == 'complete' else '⚠️ 被阻塞'}",
        "",
        "---",
        "",
        "## 执行环节",
        ""
    ]

    for index, stage in enumerate(data.get("stages", []), start=1):
        execution = stage.get("execution", {})
        verification = stage.get("verification_mode", "original")

        # 验证模式标签
        verify_label = {
            "original": "📝 原始",
            "trial_run": "🔧 试运行",
            "user_confirmed": "✅ 已确认"
        }.get(verification, "📝 原始")

        lines.extend([
            f"### 环节 {index}: {stage.get('name', '')}",
            "",
            f"- **入口**: {stage.get('entry_point', '')}",
            f"- **数据范围**: {_text(stage.get('data_scope', {}))}",
            f"- **判断逻辑**: {stage.get('decision_logic', '')}",
            f"- **输出**: {stage.get('output', '')}",
            f"- **下一步**: {stage.get('next_action', '')}",
            f"- **执行方式**: `{execution.get('mode', '')}`",
            f"- **验证状态**: {verify_label}",
            ""
        ])

        # 试运行反馈记录
        trial_notes = stage.get("trial_notes", [])
        if trial_notes:
            lines.append("**试运行反馈**:")
            for note in trial_notes:
                lines.append(f"- {note}")
            lines.append("")

    # 能力快照
    capability_snapshot = data.get("capability_snapshot", [])
    if capability_snapshot:
        lines.extend([
            "---",
            "",
            "## 能力快照",
            ""
        ])
        for cap in capability_snapshot:
            lines.extend([
                f"### {cap.get('name', '')}",
                "",
                f"- **能力ID**: `{cap.get('id', '')}`",
                f"- **验证状态**: {cap.get('verification_status', '')}",
                f"- **适配器**: `{cap.get('adapter', {}).get('name', '')}`",
                f"- **命令**: `{cap.get('adapter', {}).get('command', '')}`",
                ""
            ])

    # 待澄清问题
    open_questions = data.get("open_questions", [])
    if open_questions:
        lines.extend([
            "---",
            "",
            "## 待澄清问题",
            ""
        ])
        for q in open_questions:
            lines.append(f"- {q}")
        lines.append("")

    return "\n".join(lines)


def write_md(data: dict[str, Any], output: Path | str) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_md(data), encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sop", type=Path, help="Path to sop_spec.json")
    parser.add_argument("output", type=Path, help="Output path for .md file")
    args = parser.parse_args()

    with args.sop.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    output_path = write_md(data, args.output)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
