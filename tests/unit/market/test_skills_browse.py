# -*- coding: utf-8 -*-
"""Skills browse metadata tests."""

import json
from datetime import datetime, timezone

from market.app.routers.skills_browse import _build_skill_metadata


def test_update_skill_json_writes_created_at(tmp_path):
    """New skill metadata has a creation time without writing skill.json."""
    result = _build_skill_metadata(tmp_path, "test_skill", "Test Skill")

    parsed_time = datetime.fromisoformat(result["created_at"])
    assert parsed_time.year == datetime.now(timezone.utc).year
    assert not (tmp_path / "skill.json").exists()


def test_update_skill_json_preserves_existing_created_at(tmp_path):
    """Building metadata retains the creation time in an existing file."""
    existing = {
        "name": "Existing Skill",
        "description": "An existing skill",
        "created_at": "2024-01-15T10:30:00Z",
    }
    skill_json = tmp_path / "skill.json"
    skill_json.write_text(json.dumps(existing), encoding="utf-8")

    result = _build_skill_metadata(tmp_path, "existing_skill", "Updated Skill")

    assert result["created_at"] == existing["created_at"]
    assert json.loads(skill_json.read_text(encoding="utf-8")) == existing


def test_update_skill_json_updates_updated_at(tmp_path):
    """Existing skill metadata receives an update time in the result."""
    existing = {"name": "Original Skill", "created_at": "2024-01-15T10:30:00Z"}
    (tmp_path / "skill.json").write_text(json.dumps(existing), encoding="utf-8")

    result = _build_skill_metadata(tmp_path, "skill_to_update", "Updated Skill")

    assert (
        datetime.fromisoformat(result["updated_at"]).year
        == datetime.now(
            timezone.utc,
        ).year
    )
    assert result["created_at"] == existing["created_at"]
