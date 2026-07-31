#!/usr/bin/env python3
"""Validate a W+ SOP specification using standard-library checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from privacy import sensitive_key_findings, sensitive_value_findings


SUPPORTED_SCHEMA_VERSION = "1.1"
SENSITIVE_PARAMETERS = {"custuid", "cardnbr", "crdnbr", "account", "accountnumber"}
EXECUTION_MODES = {"opencli", "analysis", "human_action", "unsupported"}


def _required_object_fields(data: dict[str, Any], fields: list[str], prefix: str) -> list[str]:
    return [f"{prefix}: missing required field '{field}'" for field in fields if field not in data]


def validate_sop(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["$: SOP must be a JSON object"]

    errors.extend(
        _required_object_fields(
            data,
            [
                "schema_version",
                "title",
                "request_summary",
                "queue_confirmed",
                "status",
                "trigger",
                "actor",
                "stages",
                "capability_snapshot",
                "open_questions",
                "memory_candidates",
            ],
            "$",
        )
    )
    if errors:
        return errors

    if data["schema_version"] != SUPPORTED_SCHEMA_VERSION:
        errors.append("$.schema_version: unsupported schema version")
    if data["queue_confirmed"] is not True:
        errors.append("$.queue_confirmed: stage queue must be confirmed")
    if data["status"] not in {"complete", "blocked"}:
        errors.append("$.status: must be 'complete' or 'blocked'")
    if data["status"] == "complete" and data["open_questions"]:
        errors.append("$.open_questions: must be empty when status is complete")

    snapshots = data.get("capability_snapshot")
    if not isinstance(snapshots, list):
        errors.append("$.capability_snapshot: must be an array")
        snapshots = []
    snapshot_index: dict[str, dict[str, Any]] = {}
    for index, capability in enumerate(snapshots):
        path = f"$.capability_snapshot[{index}]"
        if not isinstance(capability, dict) or not capability.get("id"):
            errors.append(f"{path}: capability must have an id")
            continue
        if capability["id"] in snapshot_index:
            errors.append(f"{path}: duplicate capability id '{capability['id']}'")
        snapshot_index[capability["id"]] = capability

    stages = data.get("stages")
    if not isinstance(stages, list) or not 2 <= len(stages) <= 4:
        errors.append("$.stages: must contain between 2 and 4 stages")
        stages = []
    seen_stage_ids: set[str] = set()
    for index, stage in enumerate(stages):
        path = f"$.stages[{index}]"
        if not isinstance(stage, dict):
            errors.append(f"{path}: stage must be an object")
            continue
        errors.extend(
            _required_object_fields(
                stage,
                [
                    "id",
                    "name",
                    "status",
                    "verification_mode",
                    "entry_point",
                    "data_scope",
                    "decision_logic",
                    "output",
                    "next_action",
                    "trial_notes",
                    "execution",
                ],
                path,
            )
        )
        stage_id = stage.get("id")
        if stage_id in seen_stage_ids:
            errors.append(f"{path}.id: duplicate stage id '{stage_id}'")
        if stage_id:
            seen_stage_ids.add(stage_id)
        if data["status"] == "complete" and stage.get("status") != "complete":
            errors.append(f"{path}.status: all stages must be complete")
        if data["status"] == "complete" and stage.get("verification_mode") != "user_confirmed":
            errors.append(
                f"{path}.verification_mode: complete stages must be user_confirmed"
            )
        if not isinstance(stage.get("trial_notes"), list):
            errors.append(f"{path}.trial_notes: must be an array")
        elif data["status"] == "complete" and not stage["trial_notes"]:
            errors.append(
                f"{path}.trial_notes: complete stages require a trial confirmation record"
            )

        execution = stage.get("execution")
        if not isinstance(execution, dict):
            errors.append(f"{path}.execution: must be an object")
            continue
        mode = execution.get("mode")
        capability_ids = execution.get("capability_ids", [])
        bindings = execution.get("parameter_bindings", {})
        if mode not in EXECUTION_MODES:
            errors.append(f"{path}.execution.mode: invalid execution mode")
            continue
        if not isinstance(capability_ids, list):
            errors.append(f"{path}.execution.capability_ids: must be an array")
            capability_ids = []
        if not isinstance(bindings, dict):
            errors.append(f"{path}.execution.parameter_bindings: must be an object")
            bindings = {}

        if mode == "opencli" and not capability_ids:
            errors.append(f"{path}.execution: opencli mode requires at least one capability")
        if mode != "opencli" and capability_ids:
            errors.append(f"{path}.execution: only opencli mode may reference capabilities")

        for capability_id in capability_ids:
            capability = snapshot_index.get(capability_id)
            if capability is None:
                errors.append(f"{path}.execution: capability '{capability_id}' is missing from capability_snapshot")
                continue
            for input_contract in capability.get("inputs", []):
                if input_contract.get("required") and input_contract.get("name") not in bindings:
                    errors.append(
                        f"{path}.execution.parameter_bindings: missing required input '{input_contract.get('name')}'"
                    )

        for parameter, binding in bindings.items():
            binding_path = f"{path}.execution.parameter_bindings.{parameter}"
            if not isinstance(binding, dict) or binding.get("source") not in {"constant", "user_input", "stage_output"}:
                errors.append(f"{binding_path}: invalid binding source")
                continue
            if binding["source"] == "constant" and "value" not in binding:
                errors.append(f"{binding_path}: constant binding requires value")
            if binding["source"] == "stage_output" and not all(key in binding for key in ("stage_id", "field")):
                errors.append(f"{binding_path}: stage_output binding requires stage_id and field")
            if parameter.casefold() in SENSITIVE_PARAMETERS and binding["source"] == "constant":
                errors.append(f"{binding_path}: sensitive parameter cannot use a constant value")

    memory_candidates = data.get("memory_candidates")
    if not isinstance(memory_candidates, list):
        errors.append("$.memory_candidates: must be an array")
    else:
        for index, candidate in enumerate(memory_candidates):
            path = f"$.memory_candidates[{index}]"
            if not isinstance(candidate, dict):
                errors.append(f"{path}: candidate must be an object")
                continue
            errors.extend(_required_object_fields(candidate, ["type", "content", "evidence"], path))
            if candidate.get("type") not in {"common_wplus_knowledge", "user_wplus_usage", "sop_case"}:
                errors.append(f"{path}.type: invalid memory type")
            errors.extend(sensitive_key_findings(candidate.get("content"), f"{path}.content"))
            errors.extend(sensitive_value_findings(candidate, path))

    errors.extend(sensitive_value_findings(data))
    return list(dict.fromkeys(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sop", type=Path)
    args = parser.parse_args()
    with args.sop.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    errors = validate_sop(data)
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
