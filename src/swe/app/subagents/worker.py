# -*- coding: utf-8 -*-
"""Internal Background SubAgent worker entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Sequence

from ...config.config import AgentProfileConfig
from .models import SubAgentRunRecord, WorkerLaunchSpec
from .run_store import PerRunSubAgentRunStore
from .runtime import SubAgentRuntime


def load_launch_spec(path: Path) -> WorkerLaunchSpec:
    """Load and validate a worker launch spec from disk."""
    return WorkerLaunchSpec.model_validate_json(
        Path(path).read_text(encoding="utf-8"),
    )


async def run_worker(launch_spec_path: Path) -> int:
    """Run one Background SubAgent and persist its terminal record."""
    launch_spec = load_launch_spec(launch_spec_path)
    store = PerRunSubAgentRunStore(Path(launch_spec.run_store_dir))
    record = await store.get(launch_spec.run_id)
    if record is None:
        return 1
    await store.mark_running(
        launch_spec.run_id,
        worker_pid=os.getpid(),
        stderr_log_path=launch_spec.stderr_log_path,
    )
    runtime_record = SubAgentRunRecord(
        run_id=record.run_id,
        status="queued",
        spec=launch_spec.delegation_spec,
        definition_name=launch_spec.definition.name,
        definition_version=launch_spec.definition.version,
        definition_source=launch_spec.definition.source,
        owner_scope=launch_spec.definition.owner_scope,
        effective_policy=launch_spec.effective_policy,
        created_at=record.created_at,
        started_at=record.started_at,
    )
    try:
        runtime = SubAgentRuntime(store=store)
        result = await runtime.run(
            run=runtime_record,
            definition=launch_spec.definition,
            spec=launch_spec.delegation_spec,
            parent_agent_config=AgentProfileConfig.model_validate(
                launch_spec.parent_agent_config,
            ),
            workspace_dir=Path(launch_spec.workspace_dir),
            effective_policy=launch_spec.effective_policy,
            request_context=launch_spec.request_context,
        )
        await store.finish(launch_spec.run_id, result)
        return 0
    except Exception as exc:
        await store.fail(
            launch_spec.run_id,
            str(exc),
            error_code="worker_runtime_error",
        )
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for `python -m swe.app.subagents.worker`."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch-spec", required=True)
    args = parser.parse_args(argv)
    return asyncio.run(run_worker(Path(args.launch_spec)))


if __name__ == "__main__":
    raise SystemExit(main())
