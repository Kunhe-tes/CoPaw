# -*- coding: utf-8 -*-
from types import SimpleNamespace

from swe.app.runner.runner import _request_scenario_preset_snapshot


def test_runner_accepts_only_snapshot_restored_from_chat_metadata() -> None:
    snapshot = {"scenario_id": "scenario-a", "resources": []}

    assert (
        _request_scenario_preset_snapshot(
            SimpleNamespace(
                channel_meta={"scenario_preset_snapshot": snapshot},
            ),
        )
        is None
    )
    assert (
        _request_scenario_preset_snapshot(
            SimpleNamespace(
                channel_meta={
                    "scenario_preset_snapshot": snapshot,
                    "scenario_preset_snapshot_source": "chat_meta",
                },
            ),
        )
        == snapshot
    )
