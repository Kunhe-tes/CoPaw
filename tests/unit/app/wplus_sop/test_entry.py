from types import SimpleNamespace

from swe.app.wplus_sop import entry


def test_explicit_selection_is_authoritative():
    result = entry.classify_wplus_entry(
        selected_skill_names=["wplus-sop-miner"],
        message_text="ordinary request text",
    )

    assert result.should_offer is True
    assert result.mode == "explicit"
    assert result.confidence == 1.0


def test_missing_structured_selection_does_not_offer_entry():
    result = entry.classify_wplus_entry(
        selected_skill_names=[],
        message_text="Help me create an SOP",
    )

    assert result.should_offer is False


def test_none_structured_selection_does_not_offer_entry():
    result = entry.classify_wplus_entry(
        selected_skill_names=None,
        message_text=None,
    )

    assert result.should_offer is False


def test_exact_manual_skill_mention_is_explicit_entry():
    result = entry.classify_wplus_entry(
        selected_skill_names=[],
        message_text="请用@wplus-sop-miner帮我梳理客户筛选 SOP",
    )

    assert result.should_offer is True
    assert result.mode == "explicit"
    assert result.confidence == 1.0


def test_exact_manual_skill_mention_accepts_trailing_punctuation():
    result = entry.classify_wplus_entry(
        selected_skill_names=None,
        message_text="@wplus-sop-miner，请开始。",
    )

    assert result.should_offer is True


def test_non_exact_manual_skill_mentions_do_not_offer_entry():
    non_matches = [
        "wplus-sop-miner",
        "foo@wplus-sop-miner.com",
        "@wplus-sop-miner-old",
        "@wplus_sop_miner",
        "@WPLUS-SOP-MINER",
    ]

    for message_text in non_matches:
        result = entry.classify_wplus_entry(
            selected_skill_names=[],
            message_text=message_text,
        )
        assert result.should_offer is False, message_text


def test_suppression_prevents_reinterception_of_explicit_entry():
    result = entry.classify_wplus_entry(
        selected_skill_names=["wplus-sop-miner"],
        message_text="@wplus-sop-miner please run",
        suppress_entry=True,
    )

    assert result.should_offer is False


def test_extract_entry_text_ignores_non_text_parts():
    parts = [
        {"type": "text", "text": "第一段"},
        {"type": "image", "url": "ignored"},
        SimpleNamespace(text="第二段"),
    ]

    assert entry.extract_entry_text(parts) == "第一段\n第二段"
