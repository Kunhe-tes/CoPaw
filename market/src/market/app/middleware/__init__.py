# -*- coding: utf-8 -*-
"""Market app middleware."""

from .request_logging import RequestLoggingMiddleware

__all__ = ["RequestLoggingMiddleware"]
