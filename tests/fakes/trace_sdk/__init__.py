# -*- coding: utf-8 -*-
"""Test fake for only the documented AgentTraceSDK surface used by Swe."""

from ._impl import SpanKind, TraceFields, decorator, global_tracer


def chat_traced(**config):
    return decorator("chat", **config)


def execute_tool_traced(**config):
    return decorator("execute_tool", **config)
