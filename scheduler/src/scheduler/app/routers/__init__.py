# -*- coding: utf-8 -*-
"""Scheduler routers."""

from fastapi import APIRouter

from .cron import router as cron_router

api_router = APIRouter()
api_router.include_router(cron_router)

__all__ = ["api_router"]
