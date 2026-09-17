"""Cross-check the bundled W+ Miner contract against the platform protocol."""

from __future__ import annotations

import json
from pathlib import Path
import re

from swe.app.wplus_sop.models import MemoryWriteBatchResultPayload, TrialPlanPayload


REPO_ROOT = Path(__file__).resolve().parents[4]
MINER_ROOT = REPO_ROOT / "skills" / "wplus-sop-miner"


def test_example_result_templates_include_a_local_generic_fallback() -> None:
    templates = sorted(
        (MINER_ROOT / "assets" / "example-result-templates").glob("*.html"),
    )

    assert templates, "the output contract requires at least one HTML template"
    generic = next(path for path in templates if path.name == "generic-summary.html")
    source = generic.read_text(encoding="utf-8")
    assert "{{SOP_TITLE}}" in source
    assert "{{RESULT_SECTIONS}}" in source
    assert "{{WARNINGS}}" in source
    assert re.search(r"(?:src|href)=[\"']https?://", source) is None


def test_stage_workflow_trial_plan_example_matches_platform_payload() -> None:
    source = (MINER_ROOT / "references" / "stage-workflow.md").read_text(
        encoding="utf-8",
    )
    section = source.split("## 结构化预跑计划", maxsplit=1)[1]
    example = json.loads(
        section.split("```json", maxsplit=1)[1].split("```", maxsplit=1)[0],
    )

    assert example["kind"] == "trial_plan"
    payload = TrialPlanPayload.model_validate(example["payload"])
    registry = json.loads(
        (MINER_ROOT / "references" / "capability-registry.json").read_text(
            encoding="utf-8",
        ),
    )
    capability_ids = {item["id"] for item in registry["capabilities"]}
    assert payload.run_id == "run_..."
    assert payload.steps[0].capability_id in capability_ids
    assert payload.steps[0].capability_version == registry["catalog_version"]


def test_memory_policy_has_a_complete_batch_event_envelope() -> None:
    source = (MINER_ROOT / "references" / "memory-policy.md").read_text(
        encoding="utf-8",
    )
    section = source.split("## 批量写入结果事件", maxsplit=1)[1]
    example = json.loads(
        section.split("```json", maxsplit=1)[1].split("```", maxsplit=1)[0],
    )

    assert example["kind"] == "memory_write_batch_result"
    assert example["event_key"] == "memory-write-batch-result-{run_id}"
    payload = MemoryWriteBatchResultPayload.model_validate(example["payload"])
    assert [item.status for item in payload.results] == ["succeeded", "failed"]
