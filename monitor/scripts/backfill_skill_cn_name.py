# -*- coding: utf-8 -*-
"""补齐 RMASSIST swe_skills 的中文名.

仅更新 source_id='RMASSIST' 且 cn_name 为空 / 纯英文 / 已知占位符的记录，
避免修改已有合法中文名。

用法：
    python scripts/backfill_skill_cn_name.py            # 仅预览
    python scripts/backfill_skill_cn_name.py --apply   # 写入数据库
"""

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from monitor.app.database import DatabaseConnection, get_database_config

# 已知 skill_id -> 中文名映射。
# 多个 skill_id 可能指向同一逻辑技能（如 default 与用户定制），统一指定同一中文名。
CN_NAME_MAP: dict[str, str] = {
    "customized_default_11": "代码记忆指南",
    "customized_80306348_11": "代码记忆指南",
    "customized_default_11-20260429103350": "代码记忆指南(测试版)",
    "customized_80306348_11-20260429103350": "代码记忆指南(测试版)",
    "customized_80306348_Agent_Browser": "浏览器自动化助手",
    "customized_80306348_algorithmic-poster-philosophy": "算法海报哲学生成器",
    "customized_80306348_find-skills": "技能发现助手",
    "customized_80306348_fill-metadata": "补全元数据技能",
    "customized_80306348_hook-http-demo": "HTTP 钩子示例",
    "customized_80306348_humanizer": "AI 文风去除工具",
    "customized_80306348_mermaid-diagram": "Mermaid 图表生成器",
    "customized_80306348_self-improvement": "自我提升技能",
    "customized_80306348_summarize": "文本摘要工具",
    "3be374f3-181f-492e-88a2-fbc36a9a58c1": "天气查询",
}


def is_placeholder(cn_name: str | None) -> bool:
    """判断是否属于需要替换的英文/占位符/中英混合 cn_name."""
    if not cn_name or not cn_name.strip():
        return True
    text = cn_name.strip()
    # 纯英文 / 数字 / 空格 / 下划线 / 连字符 / 冒号 / 句点 / 常见标点
    if all(
        ch.isascii() and (ch.isalnum() or ch in " _-:.(),'\"") for ch in text
    ):
        return True
    # 已知占位符
    if text.startswith("啦啦") and set(text) <= {"啦"}:
        return True
    return False


async def backfill(apply: bool) -> None:
    """预览或写入中文名补齐."""
    db = DatabaseConnection(get_database_config())
    await db.connect()
    try:
        rows = await db.fetch_all(
            """
            SELECT id, skill_id, skill_name, cn_name
            FROM swe_skills
            WHERE source_id = 'RMASSIST'
              AND skill_id IS NOT NULL
              AND TRIM(skill_id) <> ''
            ORDER BY id
            """,
        )
        updates: list[tuple[str, int, str, str, str]] = []
        skipped: list[tuple[int, str, str, str]] = []

        for row in rows:
            skill_id: str = row["skill_id"]
            current_cn: str | None = row["cn_name"]

            target_cn = CN_NAME_MAP.get(skill_id)
            if not target_cn:
                # 不在映射表中的 skill_id 不动，避免误改其他中文名
                continue
            # 已经等于目标值,无需更新
            if (current_cn or "").strip() == target_cn:
                continue
            # 不在 CN_NAME_MAP 中走 is_placeholder 检查,这里只关心显式登记的
            # skill_id：只要当前值不是目标中文名，就更新
            updates.append(
                (
                    target_cn,
                    row["id"],
                    skill_id,
                    row["skill_name"],
                    current_cn or "",
                ),
            )

        print(f"\n=== 计划更新：{len(updates)} 条 ===")
        for new_cn, _id, skill_id, skill_name, old_cn in updates:
            print(
                f"  id={_id} | skill_id={skill_id} | "
                f"skill_name={skill_name} | "
                f"{old_cn!r} -> {new_cn!r}",
            )
        print(f"\n=== 跳过（已有合法中文名）: {len(skipped)} 条 ===")
        for _id, skill_id, skill_name, cn in skipped:
            print(
                f"  id={_id} | skill_id={skill_id} | "
                f"skill_name={skill_name} | cn_name={cn!r}",
            )

        # 同时统计 swe_skills 里未命中映射、且需要补的 skill_id
        unmapped: list[tuple[int, str, str, str]] = []
        for row in rows:
            skill_id = row["skill_id"]
            if skill_id in CN_NAME_MAP:
                continue
            current_cn = row["cn_name"]
            if is_placeholder(current_cn):
                unmapped.append(
                    (
                        row["id"],
                        skill_id,
                        row["skill_name"],
                        current_cn or "",
                    ),
                )
        if unmapped:
            print(
                f"\n=== 仍有未补的 skill_id（{len(unmapped)} 条）"
                " — 需要在 CN_NAME_MAP 中追加映射 ===",
            )
            for _id, skill_id, skill_name, cn in unmapped[:20]:
                print(
                    f"  id={_id} | skill_id={skill_id} | "
                    f"skill_name={skill_name} | cn_name={cn!r}",
                )

        if not apply:
            print("\n仅检查未写入；如确认修复，请追加 --apply")
            return

        if not updates:
            print("\n没有可写入的记录")
            return

        written = await db.execute_many(
            "UPDATE swe_skills SET cn_name = %s WHERE id = %s",
            [pair[:2] for pair in updates],
        )
        print(f"\n已写入：{written} 条")
    finally:
        await db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="补齐 RMASSIST swe_skills 中文名",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(backfill(apply=args.apply))


if __name__ == "__main__":
    main()
