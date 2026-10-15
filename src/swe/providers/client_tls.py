# -*- coding: utf-8 -*-
"""Request-owned TLS preparation for SDK clients constructed on the loop."""

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from ssl import SSLContext

_prepared_tls: ContextVar[SSLContext | None] = ContextVar(
    "prepared_client_tls",
    default=None,
)


class _ClientCleanup:
    """Preserve the SDK default client's best-effort asyncio cleanup."""

    def __del__(self):
        if self.is_closed:
            return
        try:
            asyncio.get_running_loop().create_task(self.aclose())
        except RuntimeError:
            pass


@contextmanager
def bind_prepared_client_tls(context: SSLContext | None):
    token = _prepared_tls.set(context)
    try:
        yield
    finally:
        _prepared_tls.reset(token)


def prepared_http_client_kwargs(sdk: str) -> dict:
    """Retain SDK timeout/pool defaults and HTTPX trust-env behavior."""
    context = _prepared_tls.get()
    if context is None:
        return {}
    if sdk == "anthropic":
        from anthropic import DefaultAsyncHttpxClient as AnthropicHttpxClient

        class AnthropicClient(_ClientCleanup, AnthropicHttpxClient):
            pass

        return {"http_client": AnthropicClient(verify=context)}
    else:
        from openai import DefaultAsyncHttpxClient as OpenAIHttpxClient

        class OpenAIClient(_ClientCleanup, OpenAIHttpxClient):
            pass

        return {"http_client": OpenAIClient(verify=context)}
