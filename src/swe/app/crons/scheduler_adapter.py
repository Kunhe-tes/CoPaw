# -*- coding: utf-8 -*-
"""定时任务调度平台适配器。

定义外部调度平台的抽象接口，以及两个实现：
- NoopSchedulerAdapter：空操作，单机/开发环境使用
- RealSchedulerAdapter：通过 HTTP 对接外部调度平台（新增/更新/启停任务）
"""

from __future__ import annotations

import base64
import json
import logging
from abc import ABC, abstractmethod
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 外部调度平台 API 字段长度限制
# ---------------------------------------------------------------------------
_MAX_JOBDESC_CHARS = 200
_MAX_GLUEREMARK_CHARS = 60
_MAX_CRON_CHARS = 20


def _truncate(value: str, max_chars: int) -> str:
    """按字符数截断字符串，超出部分用省略号标记。"""
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1] + "…"


class SchedulerAdapter(ABC):
    """外部调度平台适配器抽象基类。"""

    @abstractmethod
    async def register_job(
        self,
        tenant_id: str,
        agent_id: str,
        task_type: str,
        job_id: str,
        job_name: str,
        cron: str,
        callback_url: str,
        source_id: str = "",
    ) -> str:
        """向外部调度平台注册一个定时任务。

        Args:
            tenant_id: 租户 ID
            agent_id: Agent ID
            task_type: 任务类型（"job" | "heartbeat" | "dream"）
            job_id: SWE 内部 job ID
            job_name: 任务名称
            cron: cron 表达式
            callback_url: 完整的回调 URL（含 server_domain 前缀）

        Returns:
            外部平台分配的任务 ID（external_job_id）
        """
        raise NotImplementedError

    @abstractmethod
    async def update_job(
        self,
        external_id: str,
        tenant_id: str,
        agent_id: str,
        task_type: str,
        job_id: str,
        job_name: str,
        cron: str,
        callback_url: str,
        source_id: str = "",
    ) -> None:
        """更新外部平台上已注册的任务。

        Args:
            external_id: 外部平台分配的任务 ID
            tenant_id: 租户 ID
            agent_id: Agent ID
            task_type: 任务类型（"job" | "heartbeat" | "dream"）
            job_id: SWE 内部 job ID
            job_name: 任务名称
            cron: cron 表达式
            callback_url: 完整的回调 URL（含 server_domain 前缀）
        """
        raise NotImplementedError

    @abstractmethod
    async def delete_job(
        self,
        external_id: str,
        *,
        tenant_id: str = "",
        agent_id: str = "",
        task_type: str = "",
        job_id: str = "",
        job_name: str = "",
        cron: str = "",
        callback_url: str = "",
    ) -> None:
        """从外部调度平台删除任务。

        若提供 job_name，先更名为 [已删除] {job_name} 再停止，
        以区分于普通暂停。其余参数用于构建完整的 update 请求体。
        """
        raise NotImplementedError

    @abstractmethod
    async def pause_job(self, external_id: str) -> None:
        """暂停外部平台上的任务调度。"""
        raise NotImplementedError

    @abstractmethod
    async def resume_job(self, external_id: str) -> None:
        """恢复外部平台上的任务调度。"""
        raise NotImplementedError


class NoopSchedulerAdapter(SchedulerAdapter):
    """空操作适配器，所有方法仅打日志，不产生外部效果。"""

    async def register_job(
        self,
        tenant_id: str,
        agent_id: str,
        task_type: str,
        job_id: str,
        job_name: str,
        cron: str,
        callback_url: str,
        source_id: str = "",
    ) -> str:
        logger.debug(
            "NoopAdapter.register_job: tenant=%s agent=%s type=%s name=%s job=%s cron=%s url=%s",
            tenant_id,
            agent_id,
            task_type,
            job_name,
            job_id,
            cron,
            callback_url,
        )
        return ""

    async def update_job(
        self,
        external_id: str,
        tenant_id: str,
        agent_id: str,
        task_type: str,
        job_id: str,
        job_name: str,
        cron: str,
        callback_url: str,
        source_id: str = "",
    ) -> None:
        logger.debug(
            "NoopAdapter.update_job: ext_id=%s tenant=%s agent=%s type=%s name=%s job=%s cron=%s",
            external_id,
            tenant_id,
            agent_id,
            task_type,
            job_name,
            job_id,
            cron,
        )

    async def delete_job(
        self,
        external_id: str,
        *,
        tenant_id: str = "",
        agent_id: str = "",
        task_type: str = "",
        job_id: str = "",
        job_name: str = "",
        cron: str = "",
        callback_url: str = "",
    ) -> None:
        logger.debug(
            "NoopAdapter.delete_job: ext_id=%s name=%s",
            external_id,
            job_name,
        )

    async def pause_job(self, external_id: str) -> None:
        logger.debug("NoopAdapter.pause_job: ext_id=%s", external_id)

    async def resume_job(self, external_id: str) -> None:
        logger.debug("NoopAdapter.resume_job: ext_id=%s", external_id)


class RealSchedulerAdapter(SchedulerAdapter):
    """对接外部调度平台（POST /job-admin/v2/*）的适配器。

    配置项来自环境变量或直接传入，与平台 API 一一对应：
    - jobGroup, author, alarmEmail, clientNo, clientKey, clientRemark
    - glueType 固定为 "GLUE_GROOVY"
    """

    def __init__(
        self,
        *,
        base_url: str,
        job_group: int,
        author: str,
        alarm_email: str,
        client_no: str,
        client_key: str,
        client_remark: str,
        glue_type: str = "GLUE_GROOVY",
        mis_fire_strategy: Optional[int] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._job_group = job_group
        self._author = author
        self._alarm_email = alarm_email
        self._client_no = client_no
        self._client_key = client_key
        self._client_remark = client_remark
        self._glue_type = glue_type
        self._mis_fire_strategy = mis_fire_strategy

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------

    async def register_job(
        self,
        tenant_id: str,
        agent_id: str,
        task_type: str,
        job_id: str,
        job_name: str,
        cron: str,
        callback_url: str,
        source_id: str = "",
    ) -> str:
        payload = self._build_add_payload(
            tenant_id,
            agent_id,
            task_type,
            job_id,
            job_name,
            cron,
            callback_url,
            source_id=source_id,
        )
        resp_data = await self._post("/job-admin/v2/add-job", payload)
        ext_id = str(resp_data.get("content", ""))
        logger.info(
            "RealAdapter registered job: ext_id=%s tenant=%s source=%s agent=%s type=%s job=%s",
            ext_id,
            tenant_id,
            source_id,
            agent_id,
            task_type,
            job_id,
        )
        await self._set_run_state(ext_id, run_flag=1)
        return ext_id

    async def update_job(
        self,
        external_id: str,
        tenant_id: str,
        agent_id: str,
        task_type: str,
        job_id: str,
        job_name: str,
        cron: str,
        callback_url: str,
        source_id: str = "",
    ) -> None:
        payload = self._build_add_payload(
            tenant_id,
            agent_id,
            task_type,
            job_id,
            job_name,
            cron,
            callback_url,
            source_id=source_id,
        )
        payload["id"] = int(external_id)
        await self._post("/job-admin/v2/update-job", payload)
        logger.info(
            "RealAdapter updated job: ext_id=%s tenant=%s source=%s agent=%s type=%s job=%s",
            external_id,
            tenant_id,
            source_id,
            agent_id,
            task_type,
            job_id,
        )

    async def delete_job(
        self,
        external_id: str,
        *,
        tenant_id: str = "",
        agent_id: str = "",
        task_type: str = "",
        job_id: str = "",
        job_name: str = "",
        cron: str = "",
        callback_url: str = "",
    ) -> None:
        """停止任务；若提供 job_name 则先更名为 [已删除] 前缀以区分暂停。"""
        if job_name:
            try:
                payload = self._build_add_payload(
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    task_type=task_type,
                    job_id=job_id,
                    job_name=job_name,
                    cron=cron,
                    callback_url=callback_url,
                )
                payload["id"] = int(external_id)
                payload["jobDesc"] = _truncate(
                    f"[已删除] [SWE] {tenant_id}/{agent_id}/{task_type} - {job_name}",
                    _MAX_JOBDESC_CHARS,
                )
                await self._post("/job-admin/v2/update-job", payload)
            except Exception:
                logger.warning(
                    "Failed to rename job %s before delete",
                    external_id,
                    exc_info=True,
                )
        await self._set_run_state(external_id, run_flag=0)
        logger.info(
            "RealAdapter stopped (delete) job: ext_id=%s",
            external_id,
        )

    async def pause_job(self, external_id: str) -> None:
        await self._set_run_state(external_id, run_flag=0)
        logger.info("RealAdapter paused job: ext_id=%s", external_id)

    async def resume_job(self, external_id: str) -> None:
        await self._set_run_state(external_id, run_flag=1)
        logger.info("RealAdapter resumed job: ext_id=%s", external_id)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_cron(cron: str) -> str:
        """将5位cron表达式转换为外部平台的6位格式。

        外部平台格式：秒 分 时 日 月 周
        - 最前面补0表示第0秒运行
        - 最后一位（星期）固定为?
        """
        parts = cron.strip().split()
        if len(parts) != 5:
            return cron
        normalized = f"0 {' '.join(parts[:4])} ?"
        logger.debug("Normalized cron: %s -> %s", cron, normalized)
        return normalized

    @staticmethod
    def _build_job_param(
        tenant_id: str,
        source_id: str,
        agent_id: str,
        task_type: str,
        job_id: str,
    ) -> str:
        """将回调上下文参数编码为 base64 JSON，放入 jobParam。

        外部平台回调时会将 jobParam 原样传回，用于在统一的
        /api/internal/cron/callback 端点中确定租户、Agent、任务类型。
        """
        payload = json.dumps(
            {
                "tenant_id": tenant_id,
                "source_id": source_id,
                "scopeId": f"{tenant_id}-{source_id}",
                "agent_id": agent_id,
                "task_type": task_type,
                "job_id": job_id,
                "fromId": tenant_id,
            },
        )
        return base64.urlsafe_b64encode(payload.encode()).decode()

    def _build_add_payload(
        self,
        tenant_id: str,
        agent_id: str,
        task_type: str,
        job_id: str,
        job_name: str,
        cron: str,
        callback_url: str,
        source_id: str = "",
    ) -> dict:
        """构建 add-job / update-job 的请求体。"""
        identity = tenant_id
        if source_id:
            identity = f"{tenant_id}/{source_id}"
        job_desc = _truncate(
            f"[SWE] {identity}/{agent_id}/{task_type} - {job_name}",
            _MAX_JOBDESC_CHARS,
        )
        glue_remark = _truncate(job_id, _MAX_GLUEREMARK_CHARS)
        payload: dict = {
            "jobDesc": job_desc,
            "jobGroup": self._job_group,
            "glueRemark": glue_remark,
            "jobCron": _truncate(self._normalize_cron(cron), _MAX_CRON_CHARS),
            "author": self._author,
            "alarmEmail": self._alarm_email,
            "glueType": self._glue_type,
            "jobAddress": callback_url,
            "clientNo": self._client_no,
            "clientKey": self._client_key,
            "clientRemark": self._client_remark,
            "jobParam": self._build_job_param(
                tenant_id,
                source_id,
                agent_id,
                task_type,
                job_id,
            ),
        }
        if self._mis_fire_strategy is not None:
            payload["misFireStrategy"] = self._mis_fire_strategy
        return payload

    async def _set_run_state(self, external_id: str, run_flag: int) -> None:
        """调用 /v2/update-job-run-states 启停任务。"""
        payload = {
            "id": int(external_id),
            "runFlag": run_flag,
            "clientNo": self._client_no,
            "clientKey": self._client_key,
            "clientRemark": self._client_remark,
        }
        await self._post("/job-admin/v2/update-job-run-states", payload)

    async def _post(self, path: str, payload: dict) -> dict:
        """发送 POST 请求到外部调度平台，处理通用错误。"""
        url = f"{self._base_url}{path}"
        logger.info("RealAdapter POST %s: %s", url, payload)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        code = data.get("code")
        if code != 200:
            msg = data.get("msg") or "unknown error"
            return_info = data.get("returnInfo", {})
            err_code = return_info.get("returnCode", "")
            raise RuntimeError(
                f"外部调度平台返回错误: code={code}, "
                f"returnCode={err_code}, msg={msg}",
            )
        return data
