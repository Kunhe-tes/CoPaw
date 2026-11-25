# -*- coding: utf-8 -*-
"""观测身份解析：写入端与查询端共用同一 service unit 来源。"""

from __future__ import annotations

import os

SERVICE_UNIT_ENV = "CMB_CAAS_SERVICEUNITID"
LEGACY_SERVICE_UNIT_ENV = "SWE_SERVICE_UNIT_ID"
DEFAULT_SERVICE_UNIT = "swe"


def service_unit_id() -> str:
    """返回观测写入与查询统一使用的 service unit 标识。

    优先使用部署侧业务标识 ``CMB_CAAS_SERVICEUNITID``，其次兼容旧的
    ``SWE_SERVICE_UNIT_ID``，两者都未配置时回退到 ``swe``。
    """
    for name in (SERVICE_UNIT_ENV, LEGACY_SERVICE_UNIT_ENV):
        value = os.environ.get(name)
        if value:
            return value
    return DEFAULT_SERVICE_UNIT
