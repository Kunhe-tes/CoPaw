#!/usr/bin/env python3
"""Render a validated W+ SOP specification as a safe static HTML file."""

from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
from typing import Any


def _text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def render_html(data: dict[str, Any]) -> str:
    stage_blocks = []
    for index, stage in enumerate(data.get("stages", []), start=1):
        execution = stage.get("execution", {})
        verification = {
            "original": "未预跑",
            "trial_run": "已预跑，待确认",
            "user_confirmed": "预跑与反馈已确认",
        }.get(stage.get("verification_mode"), "未知")
        trial_notes = stage.get("trial_notes", [])
        trial_notes_html = ""
        if trial_notes:
            items = "".join(f"<li>{escape(_text(note))}</li>" for note in trial_notes)
            trial_notes_html = f"<dt>预跑反馈</dt><dd><ul>{items}</ul></dd>"
        stage_blocks.append(
            """
            <section class="stage">
              <div class="stage-number">{index}</div>
              <div>
                <h2>{name}</h2>
                <dl>
                  <dt>入口</dt><dd>{entry}</dd>
                  <dt>数据范围</dt><dd><pre>{scope}</pre></dd>
                  <dt>判断逻辑</dt><dd>{logic}</dd>
                  <dt>输出</dt><dd>{output}</dd>
                  <dt>下一步</dt><dd>{next_action}</dd>
                  <dt>执行分类</dt><dd><span class="mode">{mode}</span></dd>
                  <dt>验证状态</dt><dd>{verification}</dd>
                  {trial_notes}
                </dl>
              </div>
            </section>
            """.format(
                index=index,
                name=escape(_text(stage.get("name", ""))),
                entry=escape(_text(stage.get("entry_point", ""))),
                scope=escape(_text(stage.get("data_scope", {}))),
                logic=escape(_text(stage.get("decision_logic", ""))),
                output=escape(_text(stage.get("output", ""))),
                next_action=escape(_text(stage.get("next_action", ""))),
                mode=escape(_text(execution.get("mode", ""))),
                verification=escape(verification),
                trial_notes=trial_notes_html,
            )
        )

    title = escape(_text(data.get("title", "W+ SOP")))
    trigger = escape(_text(data.get("trigger", "")))
    actor = escape(_text(data.get("actor", "")))
    summary = escape(_text(data.get("request_summary", "")))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{ color-scheme: light; font-family: "Microsoft YaHei", system-ui, sans-serif; }}
    body {{ margin: 0; background: #f4f7f6; color: #18332b; }}
    main {{ max-width: 980px; margin: 0 auto; padding: 40px 24px 64px; }}
    header {{ background: #0f5b47; color: white; padding: 28px; border-radius: 18px; }}
    header p {{ margin-bottom: 0; opacity: .9; }}
    .trigger {{ margin: 20px 0; padding: 16px 20px; background: #e4f0eb; border-left: 4px solid #d59b2d; }}
    .stage {{ display: grid; grid-template-columns: 42px 1fr; gap: 16px; background: white; margin: 16px 0; padding: 22px; border-radius: 16px; box-shadow: 0 8px 28px rgba(15,91,71,.08); }}
    .stage-number {{ width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center; background: #d59b2d; color: #fff; font-weight: 700; }}
    h1, h2 {{ margin-top: 0; }}
    dl {{ display: grid; grid-template-columns: 92px 1fr; gap: 10px 14px; }}
    dt {{ font-weight: 700; color: #587168; }} dd {{ margin: 0; }}
    pre {{ margin: 0; white-space: pre-wrap; font-family: inherit; }}
    ul {{ margin: 0; padding-left: 20px; }}
    .mode {{ display: inline-block; padding: 3px 9px; border-radius: 999px; background: #e4f0eb; }}
  </style>
</head>
<body><main>
  <header><h1>{title}</h1><p>{summary}</p></header>
  <div class="trigger"><strong>触发场景：</strong>{trigger}<br><strong>执行角色：</strong>{actor}</div>
  {''.join(stage_blocks)}
</main></body>
</html>"""


def write_html(data: dict[str, Any], output: Path | str) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html(data), encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sop", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with args.sop.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    write_html(data, args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
