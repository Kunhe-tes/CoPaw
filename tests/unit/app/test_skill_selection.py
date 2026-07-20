# -*- coding: utf-8 -*-
from pathlib import Path


def _write_skill(workspace: Path, name: str, description: str) -> None:
    skill_dir = workspace / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\nbody\n",
        encoding="utf-8",
    )


def test_build_skill_use_directives_keeps_first_effective_readable_name(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from swe.app.runner import skill_selection

    _write_skill(tmp_path, "first", "First guidance")
    _write_skill(tmp_path, "second", "Second guidance")
    monkeypatch.setattr(
        skill_selection,
        "resolve_effective_skills",
        lambda _workspace, _channel: ["first", "second"],
    )

    directives = skill_selection.build_skill_use_directives(
        workspace_dir=tmp_path,
        channel="console",
        selected_skill_names=["second", "first", "second", "missing"],
    )

    assert [directive.name for directive in directives] == ["second", "first"]
    assert directives[0].path == tmp_path / "skills" / "second" / "SKILL.md"
    assert "<SKILL-USE-V1>" in directives[0].render()
    assert (
        "<description>Second guidance</description>" in directives[0].render()
    )
    assert str(directives[0].path) in directives[0].render()


def test_build_skill_use_directives_limits_to_five_and_skips_unreadable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from swe.app.runner import skill_selection

    names = [f"skill-{index}" for index in range(6)]
    for name in names[:-1]:
        _write_skill(tmp_path, name, name)
    monkeypatch.setattr(
        skill_selection,
        "resolve_effective_skills",
        lambda _workspace, _channel: names,
    )

    directives = skill_selection.build_skill_use_directives(
        workspace_dir=tmp_path,
        channel="console",
        selected_skill_names=names,
    )

    assert [directive.name for directive in directives] == names[:5]
