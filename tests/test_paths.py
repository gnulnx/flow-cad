from pathlib import Path

from erb_cad.paths import (
    discover_freecad_cmd,
    parse_env_file,
    read_local_config,
    resolve_tool_config,
)


def test_parse_env_file_supports_comments_export_and_quotes(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
        # comment
        export TEXT_TO_CAD_ROOT="~/cad viewer"
        TEXT_TO_CAD_PYTHON='~/cad viewer/.venv/bin/python'
        IGNORED_LINE
        """,
        encoding="utf-8",
    )

    values = parse_env_file(env_file)

    assert values["TEXT_TO_CAD_ROOT"] == "~/cad viewer"
    assert values["TEXT_TO_CAD_PYTHON"] == "~/cad viewer/.venv/bin/python"
    assert "IGNORED_LINE" not in values


def test_env_values_override_local_config(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "TEXT_TO_CAD_ROOT=~/from-local\nTEXT_TO_CAD_PYTHON=~/from-local/python\n",
        encoding="utf-8",
    )

    config = resolve_tool_config(
        tmp_path,
        env={
            "TEXT_TO_CAD_ROOT": "~/from-env",
            "TEXT_TO_CAD_PYTHON": "~/from-env/python",
        },
    )

    assert str(config.text_to_cad_root).endswith("from-env")
    assert str(config.text_to_cad_python).endswith("from-env/python")


def test_local_toml_can_define_tool_paths(tmp_path: Path) -> None:
    (tmp_path / ".erb-cad.local.toml").write_text(
        """
        [tools]
        TEXT_TO_CAD_ROOT = "~/toml-root"
        TEXT_TO_CAD_PYTHON = "~/toml-python"
        FREECAD_CMD = "~/toml-freecad"
        """,
        encoding="utf-8",
    )

    values = read_local_config(tmp_path)

    assert values["TEXT_TO_CAD_ROOT"] == "~/toml-root"
    assert values["TEXT_TO_CAD_PYTHON"] == "~/toml-python"
    assert values["FREECAD_CMD"] == "~/toml-freecad"


def test_freecad_discovery_prefers_env_over_system_candidates(tmp_path: Path) -> None:
    candidate = tmp_path / "freecadcmd"
    candidate.touch()

    result = discover_freecad_cmd(
        {"FREECAD_CMD": "~/configured/freecadcmd"},
        {},
        which=lambda _name: str(candidate),
    )

    assert result is not None
    assert str(result).endswith("configured/freecadcmd")


def test_freecad_discovery_uses_path_lookup_before_platform_candidates(tmp_path: Path) -> None:
    candidate = tmp_path / "freecadcmd"
    candidate.touch()
    platform_candidate = tmp_path / "mac" / "freecadcmd"
    platform_candidate.parent.mkdir()
    platform_candidate.touch()

    result = discover_freecad_cmd(
        {},
        {},
        which=lambda name: str(candidate) if name == "freecadcmd" else None,
        candidates=(platform_candidate,),
    )

    assert result == candidate
