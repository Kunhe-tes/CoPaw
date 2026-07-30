# -*- coding: utf-8 -*-
"""BBK branch mapping and primary-branch normalization."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Primary branch definitions from bbk_map.md.
BBK_MAP = [
    {"label": "总行", "value": "100"},
    {"label": "北京分行", "value": "110"},
    {"label": "广州分行", "value": "120"},
    {"label": "上海分行", "value": "121"},
    {"label": "天津分行", "value": "122"},
    {"label": "重庆分行", "value": "123"},
    {"label": "沈阳分行", "value": "124"},
    {"label": "南京分行", "value": "125"},
    {"label": "武汉分行", "value": "127"},
    {"label": "成都分行", "value": "128"},
    {"label": "西安分行", "value": "129"},
    {"label": "石家庄分行", "value": "311"},
    {"label": "唐山分行", "value": "315"},
    {"label": "太原分行", "value": "351"},
    {"label": "郑州分行", "value": "371"},
    {"label": "大连分行", "value": "411"},
    {"label": "长春分行", "value": "431"},
    {"label": "哈尔滨分行", "value": "451"},
    {"label": "呼和浩特分行", "value": "471"},
    {"label": "无锡分行", "value": "510"},
    {"label": "苏州分行", "value": "512"},
    {"label": "南通分行", "value": "513"},
    {"label": "济南分行", "value": "531"},
    {"label": "青岛分行", "value": "532"},
    {"label": "烟台分行", "value": "535"},
    {"label": "合肥分行", "value": "551"},
    {"label": "杭州分行", "value": "571"},
    {"label": "宁波分行", "value": "574"},
    {"label": "温州分行", "value": "577"},
    {"label": "福州分行", "value": "591"},
    {"label": "厦门分行", "value": "592"},
    {"label": "泉州分行", "value": "595"},
    {"label": "长沙分行", "value": "731"},
    {"label": "深圳分行", "value": "755"},
    {"label": "佛山分行", "value": "757"},
    {"label": "东莞分行", "value": "769"},
    {"label": "南宁分行", "value": "771"},
    {"label": "南昌分行", "value": "791"},
    {"label": "贵阳分行", "value": "851"},
    {"label": "昆明分行", "value": "871"},
    {"label": "海口分行", "value": "898"},
    {"label": "兰州分行", "value": "931"},
    {"label": "银川分行", "value": "951"},
    {"label": "西宁分行", "value": "972"},
    {"label": "乌鲁木齐分行", "value": "991"},
]

SECONDARY_BBK_TO_PRIMARY_MAP: dict[str, str] = {
    "772": "771",
    "587": "577",
    "610": "510",
    "416": "411",
    "850": "851",
    "763": "120",
    "537": "531",
    "793": "791",
    "576": "574",
    "981": "128",
    "594": "591",
    "377": "371",
    "372": "371",
    "596": "592",
    "918": "129",
    "572": "571",
    "379": "371",
    "597": "591",
    "554": "551",
    "760": "757",
    "556": "551",
    "417": "411",
    "717": "127",
    "561": "551",
    "638": "531",
    "738": "731",
    "374": "371",
    "598": "591",
    "472": "471",
    "579": "571",
    "733": "731",
    "412": "124",
    "993": "991",
    "511": "510",
    "536": "532",
    "515": "125",
    "830": "128",
    "432": "431",
    "612": "125",
    "358": "351",
    "599": "592",
    "459": "451",
    "349": "351",
    "719": "127",
    "716": "127",
    "316": "311",
    "130": "122",
    "657": "755",
    "518": "125",
    "516": "125",
    "912": "129",
    "356": "351",
    "613": "125",
    "435": "431",
    "528": "123",
    "797": "791",
    "514": "125",
    "603": "532",
    "103": "755",
    "888": "871",
    "555": "551",
    "102": "755",
    "593": "591",
    "798": "791",
    "714": "127",
    "589": "591",
    "750": "757",
    "910": "129",
    "575": "571",
    "330": "122",
    "573": "571",
    "874": "871",
    "710": "127",
    "519": "125",
    "712": "127",
    "983": "128",
    "631": "535",
    "734": "731",
    "899": "898",
    "470": "471",
    "322": "121",
    "581": "571",
    "111": "110",
    "553": "551",
    "427": "124",
    "477": "471",
    "415": "124",
    "873": "871",
    "413": "124",
    "752": "755",
    "546": "531",
    "570": "571",
    "543": "531",
    "713": "127",
    "539": "531",
    "656": "755",
    "759": "120",
    "732": "731",
    "792": "791",
    "112": "110",
    "564": "551",
    "533": "531",
    "523": "125",
    "858": "851",
}

_BBK_NAME_TO_ID: dict[str, str] = {
    item["label"]: item["value"] for item in BBK_MAP
}

_BBK_ID_TO_NAME: dict[str, str] = {
    item["value"]: item["label"] for item in BBK_MAP
}

BBK_ID_TO_NAME_MAP = _BBK_ID_TO_NAME


def _clean_bbk_id(bbk_id: str | None) -> str | None:
    text = str(bbk_id or "").strip()
    return text or None


def is_primary_bbk_id(bbk_id: str | None) -> bool:
    """Return whether the BBK ID is a known primary branch ID."""
    normalized = _clean_bbk_id(bbk_id)
    return normalized in _BBK_ID_TO_NAME


def get_primary_bbk_id(bbk_id: str | None) -> Optional[str]:
    """Return the known primary branch ID for a primary or secondary BBK ID."""
    normalized = _clean_bbk_id(bbk_id)
    if normalized is None:
        return None
    if normalized in _BBK_ID_TO_NAME:
        return normalized
    return SECONDARY_BBK_TO_PRIMARY_MAP.get(normalized)


def normalize_bbk_id_to_primary(bbk_id: str | None) -> Optional[str]:
    """Normalize known secondary BBK IDs to primary branch IDs.

    Unknown non-empty values are preserved and logged so ingestion can continue
    without silently losing branch data.
    """
    normalized = _clean_bbk_id(bbk_id)
    if normalized is None:
        return None

    primary_id = get_primary_bbk_id(normalized)
    if primary_id is not None:
        return primary_id

    logger.warning("Unknown BBK ID cannot be normalized: %s", normalized)
    return normalized


def get_bbk_id_by_name(name: str) -> Optional[str]:
    """Get the primary branch ID by branch name."""
    return _BBK_NAME_TO_ID.get(name)


def get_bbk_name_by_id(bbk_id: str) -> Optional[str]:
    """Get the primary branch name by a primary or secondary BBK ID."""
    primary_id = get_primary_bbk_id(bbk_id)
    if primary_id is None:
        return None
    return _BBK_ID_TO_NAME.get(primary_id)
