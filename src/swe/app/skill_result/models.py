# -*- coding: utf-8 -*-
"""技能执行结果数据模型。"""

from typing import Any, Optional

from pydantic import BaseModel, Field


class SkillResultCreate(BaseModel):
    """保存技能执行结果的请求体。"""

    trace_id: Optional[str] = Field(default=None, max_length=128)
    skill_id: Optional[str] = Field(default=None, max_length=128)
    user_id: Optional[str] = Field(default=None, max_length=128)
    bbk: Optional[str] = Field(default=None, max_length=128)
    cust_list: list[str] = Field(default_factory=list)
    metadata: Optional[Any] = Field(default=None)
    result_id: Optional[str] = Field(default=None, max_length=128)


class SkillResultCreateResponse(BaseModel):
    """保存技能执行结果后的响应。"""

    success: bool = True
    id: Optional[int] = None
    trace_id: Optional[str] = None
