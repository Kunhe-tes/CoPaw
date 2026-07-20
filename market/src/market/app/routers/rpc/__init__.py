# -*- coding: utf-8 -*-
"""RPC 路由模块."""

from fastapi import APIRouter
from .skills import router as skills_router

router = APIRouter()
router.include_router(skills_router)
