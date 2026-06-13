# -*- coding: utf-8 -*-
from fastapi import APIRouter

from .categories import router as categories_router
from .health import router as health_router
from .mcp_browse import router as mcp_browse_router
from .mcp_market import router as mcp_market_router
from .my_mcp import router as my_mcp_router
from .skill_versions import router as skill_versions_router
from .skills_browse import router as skills_browse_router
from .skills_market import router as skills_market_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(categories_router, tags=["marketplace"])
api_router.include_router(my_mcp_router, tags=["my-mcp"])
api_router.include_router(skills_market_router, tags=["marketplace-admin"])
api_router.include_router(skill_versions_router, tags=["skill-versions"])
api_router.include_router(mcp_market_router, tags=["marketplace-admin"])
api_router.include_router(skills_browse_router, tags=["marketplace"])
api_router.include_router(mcp_browse_router, tags=["marketplace"])
