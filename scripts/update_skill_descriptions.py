# -*- coding: utf-8 -*-
"""批量更新技能描述字段"""

import asyncio
import json
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from swe.database.config import get_database_config
from swe.database.connection import DatabaseConnection


def parse_skill_description(skill_md_path: Path) -> str:
    """从 SKILL.md 文件解析 description 字段"""
    try:
        content = skill_md_path.read_text(encoding="utf-8")
        return _extract_description_from_frontmatter(content)
    except Exception as e:
        print(f"  解析 SKILL.md 失败: {e}")
    return ""


def _extract_description_from_frontmatter(content: str) -> str:
    """从 YAML frontmatter 提取 description 字段"""
    if not content.startswith("---"):
        return ""

    end_idx = content.find("---", 3)
    if end_idx == -1:
        return ""

    frontmatter = content[3:end_idx].strip()
    for line in frontmatter.split("\n"):
        if line.startswith("description:"):
            desc = line.split(":", 1)[1].strip()
            return _strip_quotes(desc)
    return ""


def _strip_quotes(text: str) -> str:
    """移除字符串两端可能的引号"""
    if text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    if text.startswith("'") and text.endswith("'"):
        return text[1:-1]
    return text


def _parse_index_json(index_path: Path) -> list[dict]:
    """解析 index.json 文件"""
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        return data.get("items", [])
    except Exception as e:
        print(f"  读取 {index_path} 失败: {e}")
        return []


def _extract_skill_descriptions_from_item(
    item: dict,
) -> dict[str, str]:
    """从单个 item 提取技能描述"""
    descriptions: dict[str, str] = {}

    if item.get("item_type") != "skill" or item.get("status") != "active":
        return descriptions

    name = item.get("name", "")
    chinese_name = item.get("chinese_name", "")
    description = item.get("description", "")

    if name and description:
        descriptions[name] = description
    if chinese_name and description:
        descriptions[chinese_name] = description

    return descriptions


def _parse_skill_json(skill_json_path: Path) -> str | None:
    """从 skill.json 解析 name 字段"""
    if not skill_json_path.exists():
        return None
    try:
        skill_data = json.loads(skill_json_path.read_text(encoding="utf-8"))
        return skill_data.get("name")
    except Exception:
        return None


def _parse_skill_md_name(skill_md_path: Path) -> str | None:
    """从 SKILL.md frontmatter 解析 name 字段"""
    if not skill_md_path.exists():
        return None
    try:
        md_content = skill_md_path.read_text(encoding="utf-8")
        return _extract_name_from_frontmatter(md_content)
    except Exception:
        return None


def _extract_name_from_frontmatter(content: str) -> str | None:
    """从 YAML frontmatter 提取 name 字段"""
    if not content.startswith("---"):
        return None

    end_idx = content.find("---", 3)
    if end_idx == -1:
        return None

    frontmatter = content[3:end_idx].strip()
    for line in frontmatter.split("\n"):
        if line.startswith("name:"):
            md_name = line.split(":", 1)[1].strip()
            return _strip_quotes(md_name)
    return None


def load_marketplace_skills(marketplace_root: Path) -> dict[str, str]:
    """从 marketplace 目录加载所有技能描述"""
    skill_descriptions: dict[str, str] = {}

    if not marketplace_root.exists():
        return skill_descriptions

    for source_dir in marketplace_root.iterdir():
        if not source_dir.is_dir():
            continue

        index_path = source_dir / "index.json"
        if not index_path.exists():
            continue

        items = _parse_index_json(index_path)
        for item in items:
            descriptions = _extract_skill_descriptions_from_item(item)
            skill_descriptions.update(descriptions)

            # 检查技能目录中的 skill.json 和 SKILL.md
            item_id = item.get("item_id", "")
            if not item_id:
                continue

            skill_dir = source_dir / "skills" / item_id
            description = item.get("description", "")

            skill_json_path = skill_dir / "skill.json"
            display_name = _parse_skill_json(skill_json_path)
            if display_name and description:
                skill_descriptions[display_name] = description

            skill_md_path = skill_dir / "SKILL.md"
            md_name = _parse_skill_md_name(skill_md_path)
            if md_name and description:
                skill_descriptions[md_name] = description

    return skill_descriptions


def get_skill_description(
    skill_name: str,
    builtin_dir: Path,
    pool_dir: Path,
    marketplace_skills: dict[str, str],
) -> str:
    """获取技能描述"""
    # 优先从 marketplace 获取
    if skill_name in marketplace_skills:
        return marketplace_skills[skill_name]

    # 尝试从内置技能目录读取
    skill_md_path = builtin_dir / skill_name / "SKILL.md"
    if skill_md_path.exists():
        desc = parse_skill_description(skill_md_path)
        if desc:
            return desc

    # 尝试从技能池目录读取
    skill_md_path = pool_dir / skill_name / "SKILL.md"
    if skill_md_path.exists():
        desc = parse_skill_description(skill_md_path)
        if desc:
            return desc

    # 为常见技能名称生成默认描述
    default_descriptions = {
        "数据分析": "对数据进行统计分析、可视化和洞察提取",
        "客户分析": "分析客户数据，识别客户特征和行为模式",
        "数据查询": "从数据库或数据源中查询和提取数据",
        "营销推荐": "基于客户数据生成个性化营销推荐",
        "风险评估": "对业务或客户进行风险分析和评估",
        "文档生成": "自动生成各类文档和报告",
        "智能客服": "基于知识库的智能问答和客服服务",
        "智能监控": "实时监控业务数据和系统状态",
        "对话问答": "智能对话问答，支持多轮交互",
        "数据报表": "生成数据报表和可视化图表",
        "数据导入": "导入外部数据到系统数据库",
        "数据导出": "导出系统数据到外部文件",
        "图表生成": "生成各类统计图表和可视化图形",
        "图表分析": "对图表数据进行分析和解读",
        "股票分析": "分析股票市场数据和投资建议",
        "理财服务": "提供理财产品和投资咨询服务",
        "邮件生成": "自动生成邮件内容和模板",
        "文档处理": "处理各类文档格式转换和编辑",
        "预警通知": "发送业务预警和通知消息",
        "贷款预审": "对贷款申请进行预审和风险评估",
        "客户画像": "构建客户画像，分析客户特征",
        "客户服务": "提供客户咨询和服务支持",
        "客户管理": "管理客户信息和关系",
        "数据治理": "数据质量管理和数据标准化",
        "智能助手": "智能助手功能，提供辅助决策",
        "智能问答": "基于知识库的智能问答系统",
        "财务分析": "财务数据分析和报表生成",
        "风险分析": "业务风险分析和预警",
        "合规检查": "业务合规性检查和审核",
        "报表生成": "自动生成各类业务报表",
        "画像分析": "客户画像分析和洞察",
        "产品推荐": "基于客户需求的产品推荐",
        "业务分析": "业务数据分析和决策支持",
        "流程自动化": "自动化业务流程处理",
    }

    if skill_name in default_descriptions:
        return default_descriptions[skill_name]

    # 根据名称关键词推断描述
    if "分析" in skill_name:
        return f"{skill_name}相关的数据分析和洞察提取"
    elif "查询" in skill_name:
        return f"{skill_name}相关的数据查询和提取"
    elif "生成" in skill_name:
        return f"{skill_name}相关的自动生成功能"
    elif "推荐" in skill_name:
        return f"{skill_name}相关的智能推荐服务"
    elif "监控" in skill_name:
        return f"{skill_name}相关的实时监控功能"
    elif "问答" in skill_name:
        return f"{skill_name}相关的智能问答系统"
    elif "客服" in skill_name:
        return f"{skill_name}相关的客户服务功能"
    elif "报表" in skill_name:
        return f"{skill_name}相关的报表生成功能"
    elif "文档" in skill_name:
        return f"{skill_name}相关的文档处理功能"
    elif "预警" in skill_name or "通知" in skill_name:
        return f"{skill_name}相关的预警通知功能"
    elif "风险" in skill_name:
        return f"{skill_name}相关的风险分析功能"
    elif "客户" in skill_name:
        return f"{skill_name}相关的客户分析和管理"
    elif "数据" in skill_name:
        return f"{skill_name}相关的数据处理功能"
    elif "智能" in skill_name:
        return f"{skill_name}相关的智能化服务"
    elif "画像" in skill_name:
        return f"{skill_name}相关的画像分析功能"

    return ""


async def update_skill_descriptions():
    """批量更新技能描述"""
    config = get_database_config()
    db = DatabaseConnection(config)
    await db.connect()

    # 获取内置技能目录和技能池目录
    builtin_dir = project_root / "src" / "swe" / "agents" / "skills"
    pool_dir = Path.home() / ".swe" / "skill_pool"
    marketplace_root = Path.home() / ".swe.marketplace"

    print(f"内置技能目录: {builtin_dir}")
    print(f"技能池目录: {pool_dir}")
    print(f"Marketplace 目录: {marketplace_root}")

    # 加载 marketplace 技能描述
    marketplace_skills = load_marketplace_skills(marketplace_root)
    print(f"从 Marketplace 加载了 {len(marketplace_skills)} 个技能描述")

    # 获取所有需要更新描述的技能
    query = """
        SELECT DISTINCT skill_name
        FROM swe_tracing_spans
        WHERE event_type = 'skill_invocation'
          AND skill_name IS NOT NULL
          AND skill_description IS NULL
        ORDER BY skill_name
    """
    rows = await db.fetch_all(query)
    skills = [row["skill_name"] for row in rows]
    print(f"\n找到 {len(skills)} 个需要更新描述的技能")

    updated_count = 0
    for skill_name in skills:
        desc = get_skill_description(
            skill_name,
            builtin_dir,
            pool_dir,
            marketplace_skills,
        )
        if desc:
            print(f"  {skill_name}: 找到描述 ({len(desc)} 字符)")
            # 更新数据库
            update_query = """
                UPDATE swe_tracing_spans
                SET skill_description = %s
                WHERE event_type = 'skill_invocation'
                  AND skill_name = %s
                  AND skill_description IS NULL
            """
            result = await db.execute(update_query, (desc, skill_name))
            updated_count += result
            print(f"    更新了 {result} 条记录")
        else:
            print(f"  {skill_name}: 未找到描述")

    print(f"\n总计更新 {updated_count} 条记录")


if __name__ == "__main__":
    asyncio.run(update_skill_descriptions())
