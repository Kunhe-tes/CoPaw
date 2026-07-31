#!/usr/bin/env python3
"""根据能力注册表生成 W+ 平台功能树与澄清知识图。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = SKILL_ROOT / "references" / "capability-registry.json"
DEFAULT_OUTPUT = SKILL_ROOT / "references" / "platform-function-map.md"

STATUS_LABELS = {
    "verified": "已验证",
    "partial": "部分验证",
    "unverified": "未验证",
}

AREA_ORDER = ["重要商机", "客户资产", "客户收益", "客户流水", "客户交易"]


def _md(value: Any) -> str:
    """转义会破坏 Markdown 表格的字符。"""

    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _status(capability: dict[str, Any]) -> str:
    raw = capability.get("verification_status", "unverified")
    return STATUS_LABELS.get(raw, raw)


def _path(capability: dict[str, Any]) -> str:
    evidence = capability.get("ui_evidence") or []
    return "；".join(_md(item) for item in evidence) if evidence else "入口未记录，需向用户确认"


def _input_summary(capability: dict[str, Any]) -> str:
    inputs = capability.get("inputs") or []
    if not inputs:
        return "无已记录入参"

    values = []
    for item in inputs:
        requirement = "必填" if item.get("required") else "可选"
        values.append(f"`{_md(item.get('name', 'unknown'))}`（{requirement}）")
    return "、".join(values)


def _output_summary(capability: dict[str, Any]) -> str:
    outputs = capability.get("outputs") or []
    if not outputs:
        return "输出字段未形成文档，不得推断"
    names = "、".join(f"`{_md(item.get('name', 'unknown'))}`" for item in outputs)
    return f"已记录字段：{names}"


def _group_capabilities(capabilities: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for capability in capabilities:
        groups.setdefault(capability.get("business_area", "其他"), []).append(capability)
    return groups


def _tree_lines(capabilities: list[dict[str, Any]]) -> list[str]:
    groups = _group_capabilities(capabilities)
    lines = ["```text", "W+ 平台"]

    opportunity_areas = [area for area in AREA_ORDER if area == "重要商机" and area in groups]
    insight_areas = [area for area in AREA_ORDER if area != "重要商机" and area in groups]
    remaining = sorted(set(groups) - set(AREA_ORDER))

    if opportunity_areas:
        lines.append("├─ 商机")
        lines.append("│  └─ 商机中心 → 重要商机")
        items = groups["重要商机"]
        for index, capability in enumerate(items):
            connector = "└─" if index == len(items) - 1 else "├─"
            lines.append(
                "│     "
                f"{connector} {capability['name']} → {capability['description']} "
                f"[OpenCLI: {capability['adapter']['name']}; {_status(capability)}]"
            )

    if insight_areas or remaining:
        lines.append("└─ 客户洞察（进入前需有用户确认或已验证来源的 custUid）")
        ordered_areas = insight_areas + remaining
        for area_index, area in enumerate(ordered_areas):
            area_last = area_index == len(ordered_areas) - 1
            area_connector = "└─" if area_last else "├─"
            area_prefix = "   " if area_last else "│  "
            lines.append(f"   {area_connector} {area}")
            items = groups[area]
            for item_index, capability in enumerate(items):
                item_connector = "└─" if item_index == len(items) - 1 else "├─"
                lines.append(
                    f"   {area_prefix}{item_connector} {capability['name']} → "
                    f"{capability['description']} "
                    f"[OpenCLI: {capability['adapter']['name']}; {_status(capability)}]"
                )

    lines.append("```")
    return lines


def _graph_lines(capabilities: list[dict[str, Any]]) -> list[str]:
    groups = _group_capabilities(capabilities)
    lines = [
        "```mermaid",
        "flowchart TD",
        '    request["客户经理的模糊需求"] --> clarify["定位业务动作与平台入口"]',
        '    clarify --> opp["商机 / 重要商机"]',
        '    clarify --> known["已知客户 / 已确认 custUid"]',
        '    opp -. "页面导航或业务关联" .-> insight["客户洞察"]',
        '    known -->|已确认输入| insight',
    ]

    node_by_id: dict[str, str] = {}
    for index, capability in enumerate(capabilities, start=1):
        node = f"cap{index}"
        node_by_id[capability["id"]] = node
        label = (
            f"{capability['name']}<br/>{capability['adapter']['name']}<br/>"
            f"{_status(capability)}"
        ).replace('"', "'")
        lines.append(f'    {node}["{label}"]')

    for capability in capabilities:
        node = node_by_id[capability["id"]]
        if capability.get("business_area") == "重要商机":
            lines.append(f"    opp --> {node}")
        else:
            lines.append(f"    insight --> {node}")

    lines.extend(
        [
            '    analysis["按用户确认的口径分析与判断"]',
            '    followup["人工跟进 / 记录 / 其他未开放写操作"]',
        ]
    )
    for capability in capabilities:
        node = node_by_id[capability["id"]]
        lines.append(f'    {node} -. "结果字段按文档状态校验" .-> analysis')
    lines.extend(
        [
            "    analysis --> followup",
            "```",
        ]
    )
    return lines


def render_platform_function_map(registry: dict[str, Any]) -> str:
    """把注册表渲染为稳定、可审查的中文平台功能知识文件。"""

    capabilities = registry.get("capabilities") or []
    lines = [
        "# W+ 平台功能说明（澄清知识）",
        "",
        "> 本文件由 `references/capability-registry.json` 生成。它把已知 OpenCLI 的功能描述、页面入口和流程关系组织成平台功能树与知识图，供 SOP 澄清时定位能力使用；它不是 W+ 全量产品手册，也不是 OpenCLI 执行编排。",
        "",
        "## 目录",
        "",
        "- 使用边界",
        "- 平台功能树",
        "- 平台功能知识图",
        "- OpenCLI 能力说明",
        "- 在澄清中的使用方法",
        "",
        "## 使用边界",
        "",
        "- 图中的页面连线是页面导航关系，不代表可执行数据依赖。只有注册表明确记录了输出字段，而且后续能力明确接受该字段时，才可以把两个 OpenCLI 视为可编排的数据链路。",
        "- 客户洞察类能力所需的 `custUid` 必须由用户输入或已验证的前序输出提供。当前商机列表能力的输出字段尚未文档化，不能假设它们会返回 `custUid`。",
        "- `部分验证` 或 `未验证` 的能力只能作为待确认选项，不能升级为已验证事实。",
        "- 当前登记能力均为只读查询。分析判断、创建待办、写商机、客户沟通、配置调整和跟进记录等动作，应标为 `analysis`、`human_action` 或 `unsupported`，不能伪装成 OpenCLI 写能力。",
        "- 如果本说明与用户当前说法冲突，以用户当前说法为准，并把差异记录为知识更新候选。",
        "",
        "## 平台功能树",
        "",
        *_tree_lines(capabilities),
        "",
        "## 平台功能知识图",
        "",
        "这张图用于澄清时定位“从哪里进入、能查询什么、哪里需要人工判断”。虚线表示知识关联或待校验结果，不表示可直接执行的参数传递。",
        "",
        *_graph_lines(capabilities),
        "",
        "## OpenCLI 能力说明",
        "",
        "| 功能域 | 能力与用途 | 页面/流程证据 | 入参摘要 | 输出状态 | 能力标识 | OpenCLI 适配器 | 验证状态 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for capability in capabilities:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(capability.get("business_area", "其他")),
                    f"{_md(capability['name'])}：{_md(capability['description'])}",
                    _path(capability),
                    _input_summary(capability),
                    _output_summary(capability),
                    f"`{_md(capability['id'])}`",
                    f"`{_md(capability['adapter']['name'])}`",
                    _status(capability),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 在澄清中的使用方法",
            "",
            "1. 根据用户原始需求，在功能树中定位最接近的模块与功能域；找不到时，不要硬套现有能力。",
            "2. 用知识图把需求拆成真实业务动作，例如“查询商机名单 → 查看客户明细 → 按确认口径判断 → 人工跟进”，但先让用户确认动作顺序。",
            "3. 在当前环节提问时，只把本图中有注册表证据的页面、数据范围和 OpenCLI 能力作为选项；字段、阈值和业务规则仍需用户确认。",
            "4. 选择能力后，回到能力注册表核对完整入参、允许值、输出文档状态和验证状态，不要仅凭本图生成执行参数。",
            "5. 若需要从商机名单进入客户洞察，必须先确认 `custUid` 的来源；在列表输出契约未补齐前，将该衔接记录为缺口，而不是自动编排。",
            "",
            f"生成来源版本：`{_md(registry.get('catalog_version', 'unknown'))}`；能力数量：`{len(capabilities)}`。",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 W+ 平台功能树与知识图")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    output = render_platform_function_map(registry)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")
    print(f"已生成：{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
