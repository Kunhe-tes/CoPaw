# -*- coding: utf-8 -*-
"""Response for unpublished conversation sources."""

from .errors import StorageUnavailable


class TenantNotPublished(StorageUnavailable):
    code = "conversation_tenant_not_published"

    def __init__(self):
        super().__init__("Conversation tenant is under maintenance")


async def tenant_maintenance_response(_request, _error):
    """One safe response for failures from endpoints and outer middleware."""
    from starlette.responses import JSONResponse

    return JSONResponse(
        status_code=503,
        content={
            "detail": "Conversation tenant is under maintenance",
            "code": TenantNotPublished.code,
        },
        headers={"Retry-After": "30"},
    )
