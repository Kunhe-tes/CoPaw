from pathlib import Path
from types import SimpleNamespace

from swe.app.wplus_sop import entry


def test_explicit_selection_is_authoritative(monkeypatch):
    def unexpected_resolve(*_args, **_kwargs):
        raise AssertionError("explicit selection must not run inference")

    monkeypatch.setattr(entry, "resolve_effective_skills", unexpected_resolve)

    result = entry.classify_wplus_entry(
        user_message="ordinary visible text",
        selected_skill_names=["wplus-sop-miner"],
        workspace_dir=Path("."),
    )

    assert result.should_offer is True
    assert result.mode == "explicit"
    assert result.confidence == 1.0


def test_visible_skill_label_is_not_explicit_authority(monkeypatch):
    monkeypatch.setattr(
        entry,
        "resolve_effective_skills",
        lambda *_args, **_kwargs: [],
    )

    result = entry.classify_wplus_entry(
        user_message="@wplus-sop-miner please run",
        selected_skill_names=[],
        workspace_dir=Path("."),
    )

    assert result.should_offer is False


def test_implicit_candidate_uses_pre_agent_detector(monkeypatch):
    class FakeDetector:
        def __init__(self, **_kwargs):
            self.enabled = []

        def set_enabled_skills(self, skills):
            self.enabled = skills

        def detect_from_user_message(self, message):
            assert self.enabled == ["wplus-sop-miner"]
            assert message == "帮我梳理客户筛选 SOP"
            return "wplus-sop-miner", 0.7

    monkeypatch.setattr(
        entry,
        "resolve_effective_skills",
        lambda *_args, **_kwargs: ["wplus-sop-miner"],
    )
    monkeypatch.setattr(entry, "SkillInvocationDetector", FakeDetector)

    result = entry.classify_wplus_entry(
        user_message="帮我梳理客户筛选 SOP",
        selected_skill_names=None,
        workspace_dir=Path("."),
    )

    assert result.should_offer is True
    assert result.mode == "implicit"


def test_suppression_skips_implicit_detection(monkeypatch):
    def unexpected_resolve(*_args, **_kwargs):
        raise AssertionError("suppressed request must not run inference")

    monkeypatch.setattr(entry, "resolve_effective_skills", unexpected_resolve)

    result = entry.classify_wplus_entry(
        user_message="帮我梳理客户筛选 SOP",
        selected_skill_names=None,
        workspace_dir=Path("."),
        suppress_implicit=True,
    )

    assert result.should_offer is False


def test_extract_entry_text_ignores_non_text_parts():
    parts = [
        {"type": "text", "text": "第一段"},
        {"type": "image", "url": "ignored"},
        SimpleNamespace(text="第二段"),
    ]

    assert entry.extract_entry_text(parts) == "第一段\n第二段"
