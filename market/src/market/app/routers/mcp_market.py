# -*- coding: utf-8 -*-
"""市场 MCP 管理路由（管理员）。"""

import json
import re
from typing import Annotated, Optional
from urllib.parse import unquote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)

from ...marketplace.schemas import (
    MCPDistributionRequest,
    MCPDistributionResponse,
    MarketMCPDetail,
    MarketMCPItem,
    PublishMCPRequest,
    UpdateMarketMCPMetadataRequest,
    UploadMCPResponse,
)
from ...marketplace.fs import (
    load_mcp_config,
    load_index,
    normalize_mcp_config_data,
)
from ...runtime.config_store import MCPClientConfig
from ...runtime.context import tenant_context
from ..deps import require_source_id
from .my_mcp import _test_mcp_connection

router = APIRouter()
MCP_NOT_FOUND_DETAIL = "MCP not found or already deleted"


def _require_manager(x_manager: Optional[str]) -> None:
    """校验管理员权限。"""
    if x_manager != "true":
        raise HTTPException(status_code=403, detail="Manager access required")


class UploadMCPFormData:
    """上传 MCP 的表单字段。"""

    def __init__(
        self,
        name: Optional[str] = Form(default=None),
        chinese_name: Optional[str] = Form(default=""),
        description: Optional[str] = Form(default=""),
        guidance: Optional[str] = Form(default=""),
        bbk_ids: Optional[str] = Form(default=None),
    ) -> None:
        self.name = name
        self.chinese_name = chinese_name
        self.description = description
        self.guidance = guidance
        self.bbk_ids = bbk_ids


def _normalize_client_key(value: str) -> str:
    """规范化 client_key，保持与前端自动生成逻辑一致。"""
    normalized = re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-_")
    return normalized or "mcp"


def _infer_transport(config: dict) -> Optional[str]:
    """从兼容格式中推断 transport。"""
    raw_transport = (
        config.get("transport")
        or config.get("type")
        or (config.get("advanced") or {}).get("transport")
    )
    if isinstance(raw_transport, str):
        normalized = raw_transport.lower()
        if normalized == "stdio":
            return "stdio"
        if normalized == "sse":
            return "sse"
        if normalized in {"streamable_http", "streamable-http"}:
            return "streamable_http"
    if (
        isinstance(config.get("command"), str)
        and config.get("command", "").strip()
    ):
        return "stdio"
    if isinstance(config.get("url"), str) and config.get("url", "").strip():
        return "streamable_http"
    return None


def _build_upload_fallback_name(filename: str) -> str:
    """根据文件名生成上传名称兜底值。"""
    return re.sub(
        r"\.(json|mcp\.json)$",
        "",
        filename,
        flags=re.IGNORECASE,
    )


def _extract_mcp_servers_payload(
    file_data: dict,
) -> tuple[str, str, dict]:
    """从 mcpServers 结构中提取 client_key、name 和 config。"""
    mcp_servers = file_data.get("mcpServers")
    if not isinstance(mcp_servers, dict) or not mcp_servers:
        return "", "", {}

    first_key, first_value = next(iter(mcp_servers.items()))
    if not isinstance(first_value, dict):
        return "", "", {}

    config = dict(first_value)
    return str(first_key), str(config.get("name") or ""), config


def _extract_direct_payload(
    file_data: dict,
    current_client_key: str,
    current_name: str,
) -> tuple[str, str, dict]:
    """从扁平 config 或 config 包裹结构中提取数据。"""
    raw_config = file_data.get("config", file_data)
    if not isinstance(raw_config, dict):
        return current_client_key, current_name, {}

    config = dict(raw_config)
    client_key = str(file_data.get("client_key") or current_client_key or "")
    name = str(
        config.get("name") or file_data.get("name") or current_name or "",
    )
    return client_key, name, config


def _finalize_upload_payload(
    fallback_name: str,
    client_key: str,
    name: str,
    config: dict,
) -> tuple[str, str, dict]:
    """补全 transport/name/client_key，并校验最终结果。"""
    if not config:
        raise ValueError("文件格式不正确")

    transport = _infer_transport(config)
    if not transport:
        raise ValueError("文件格式不正确：无法识别连接方式")

    config["transport"] = transport
    final_name = name.strip() or fallback_name
    final_client_key = _normalize_client_key(
        client_key or final_name or fallback_name,
    )
    return final_client_key, final_name, config


def _extract_upload_payload(
    filename: str,
    file_data: dict,
) -> tuple[str, str, dict]:
    """从上传文件中提取 client_key、name 和规范化后的 config。"""
    fallback_name = _build_upload_fallback_name(filename)
    client_key, name, config = _extract_mcp_servers_payload(file_data)
    if not config:
        client_key, name, config = _extract_direct_payload(
            file_data,
            client_key,
            name,
        )
    return _finalize_upload_payload(
        fallback_name,
        client_key,
        name,
        config,
    )


@router.post(
    "/market/mcp",
    response_model=MarketMCPItem,
    status_code=status.HTTP_201_CREATED,
)
async def publish_mcp(
    req: PublishMCPRequest,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
):
    """发布 MCP 到市场（管理员）。"""
    source_id = require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = request.app.state.marketplace
    item = await svc.publish_mcp(source_id, req)
    return MarketMCPItem(
        item_id=item.item_id,
        client_key=item.client_key,
        name=item.name,
        chinese_name=item.chinese_name,
        description=item.description,
        guidance=item.guidance,
        version=item.version,
        creator_id=item.creator_id,
        creator_name=item.creator_name,
        category_id=item.category_id,
        bbk_ids=item.bbk_ids,
        created_at=item.created_at,
        updated_at=item.updated_at,
        call_count=0,
        user_count=0,
    )


@router.post(
    "/market/mcp/upload",
    response_model=UploadMCPResponse,
)
async def upload_mcp(
    request: Request,
    file: UploadFile = File(...),
    form: UploadMCPFormData = Depends(),
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
):
    """上传 MCP 连接器文件到市场（管理员）。"""
    source_id = require_source_id(x_source_id)
    _require_manager(x_manager)

    # 校验文件格式
    if not file.filename or not file.filename.endswith(".json"):
        return UploadMCPResponse(
            success=False,
            error="Only .json files are accepted",
        )

    try:
        content = await file.read()
        file_data = json.loads(content.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return UploadMCPResponse(success=False, error=f"Invalid JSON: {e}")

    try:
        client_key, inferred_name, config = _extract_upload_payload(
            file.filename,
            file_data,
        )
    except ValueError as e:
        return UploadMCPResponse(success=False, error=str(e))

    final_name = form.name or inferred_name

    # 构建发布请求
    req = PublishMCPRequest(
        client_key=client_key,
        name=final_name,
        chinese_name=form.chinese_name or "",
        description=form.description or config.get("description", ""),
        guidance=form.guidance or "",
        creator_id=x_user_id or "unknown",
        creator_name=unquote(x_user_name or ""),
        category_id=None,
        bbk_ids=json.loads(form.bbk_ids) if form.bbk_ids else [],
        config=config,
    )

    svc = request.app.state.marketplace
    try:
        await svc.publish_mcp(source_id, req)
        return UploadMCPResponse(success=True)
    except Exception as e:
        return UploadMCPResponse(success=False, error=str(e))


@router.post(
    "/market/mcp/{item_id}/distribute",
    response_model=MCPDistributionResponse,
)
async def distribute_mcp(
    item_id: str,
    req: MCPDistributionRequest,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
):
    """分发 MCP（管理员）。"""
    source_id = require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = request.app.state.marketplace

    # 检查条目是否存在
    items = load_index(svc.marketplace_root, source_id)
    item = next(
        (i for i in items if i.item_id == item_id and i.item_type == "mcp"),
        None,
    )
    if item is None:
        raise HTTPException(
            status_code=404,
            detail=MCP_NOT_FOUND_DETAIL,
        )

    try:
        result = await svc.distribute_mcp(
            source_id,
            item_id,
            operator_id=x_user_id or "",
            operator_name=unquote(x_user_name or ""),
            req=req,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result


@router.delete(
    "/market/mcp/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_mcp(
    item_id: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
):
    """删除市场 MCP（管理员）。"""
    source_id = require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = request.app.state.marketplace

    # 检查条目是否存在
    items = load_index(svc.marketplace_root, source_id)
    item = next(
        (i for i in items if i.item_id == item_id and i.item_type == "mcp"),
        None,
    )
    if item is None:
        raise HTTPException(
            status_code=404,
            detail=MCP_NOT_FOUND_DETAIL,
        )

    ok = await svc.delete_mcp(
        source_id,
        item_id,
        operator_id=x_user_id or "",
        operator_name=unquote(x_user_name or ""),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="MCP not found")


@router.put("/market/mcp/{item_id}/metadata", response_model=MarketMCPDetail)
async def update_market_mcp_metadata(
    item_id: str,
    payload: UpdateMarketMCPMetadataRequest,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_bbk_id: Optional[str] = Header(default=None, alias="X-Bbk-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
):
    """更新 MCP 市场条目的展示元数据。"""
    source_id = require_source_id(x_source_id)
    _require_manager(x_manager)
    user_bbk_id = x_bbk_id or "100"
    svc = request.app.state.marketplace
    try:
        svc.update_mcp_metadata(
            source_id=source_id,
            item_id=item_id,
            chinese_name=payload.chinese_name,
            description=payload.description,
            guidance=payload.guidance,
            bbk_ids=payload.bbk_ids,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    detail = await svc.get_mcp_detail(source_id, item_id, user_bbk_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="MCP not found")
    return detail


@router.post("/market/mcp/{item_id}/test")
async def test_market_mcp(
    item_id: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """测试市场 MCP 连接。"""
    source_id = require_source_id(x_source_id)
    svc = request.app.state.marketplace

    # 获取 MCP 配置
    items = load_index(svc.marketplace_root, source_id)
    item = next(
        (i for i in items if i.item_id == item_id and i.item_type == "mcp"),
        None,
    )
    if item is None:
        raise HTTPException(
            status_code=404,
            detail=MCP_NOT_FOUND_DETAIL,
        )

    mcp_config = load_mcp_config(svc.marketplace_root, source_id, item_id)
    if mcp_config is None:
        raise HTTPException(status_code=404, detail="MCP config not found")

    config_data = normalize_mcp_config_data(
        mcp_config.get("config", {}),
    )
    if not config_data.get("name"):
        config_data["name"] = item.name or item.client_key or "market-mcp"
    config_data.setdefault("description", item.description or "")
    config_data.setdefault("enabled", True)
    client_config = MCPClientConfig(**config_data)

    # 与 MyMCP 测试连接保持同一实现，避免两处逻辑继续漂移。
    tenant_id = x_user_id or "default"
    with tenant_context(
        tenant_id=tenant_id,
        user_id=tenant_id,
        source_id=source_id,
    ):
        return await _test_mcp_connection(client_config)


@router.get(
    "/market/mcp/{item_id}/distributions",
)
async def get_mcp_distributions(
    item_id: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
):
    """查询 MCP 分发记录（管理员）."""
    source_id = require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = request.app.state.marketplace
    distributions = await svc.get_distributions(source_id, item_id, "mcp")
    return distributions


@router.post(
    "/market/mcp/recall",
)
async def recall_mcp_by_name(
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
) -> dict:
    """按 MCP 名称撤回（管理员）."""
    from ...marketplace.schemas import RecallRequest

    source_id = require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = request.app.state.marketplace

    # 解析请求体
    body = await request.json()
    target_user_ids = body.get("target_user_ids")
    mcp_name = body.get("mcp_name")
    req = RecallRequest(
        target_user_ids=target_user_ids,
        mcp_name=mcp_name,
    )

    try:
        result = await svc.recall_mcp(
            source_id,
            None,
            operator_id=x_user_id or "",
            operator_name=unquote(x_user_name or ""),
            req=req,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result.model_dump()


@router.post(
    "/market/mcp/{item_id}/recall",
)
async def recall_mcp(
    item_id: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
) -> dict:
    """撤回已分发的 MCP（管理员）."""
    from ...marketplace.schemas import RecallRequest

    source_id = require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = request.app.state.marketplace

    # 解析请求体
    body = await request.json()
    target_user_ids = body.get("target_user_ids")
    force = body.get("force", False)
    req = RecallRequest(
        target_user_ids=target_user_ids,
        force=force,
    )

    try:
        result = await svc.recall_mcp(
            source_id,
            item_id,
            operator_id=x_user_id or "",
            operator_name=unquote(x_user_name or ""),
            req=req,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result.model_dump()
