from pathlib import Path

from flow_cad.step_io import STABLE_STEP_TIMESTAMP, normalize_step_file


def test_normalize_step_file_replaces_opencascade_timestamp(tmp_path: Path) -> None:
    step_file = tmp_path / "part.step"
    step_file.write_text(
        "\n".join(
            [
                "ISO-10303-21;",
                "HEADER;",
                "FILE_NAME('Open CASCADE Shape Model','2026-05-19T07:26:54',('Author'),(",
                "    'Open CASCADE'),'Open CASCADE STEP processor 7.8','build123d',",
                "  'Unknown');",
                "DATA;",
                "#1 = CARTESIAN_POINT('',(1.,2.,3.));",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    changed = normalize_step_file(step_file)

    text = step_file.read_text(encoding="utf-8")
    assert changed is True
    assert STABLE_STEP_TIMESTAMP in text
    assert "2026-05-19T07:26:54" not in text
    assert "#1 = CARTESIAN_POINT('',(1.,2.,3.));" in text


def test_normalize_step_file_replaces_labeled_model_timestamp(tmp_path: Path) -> None:
    step_file = tmp_path / "part.step"
    step_file.write_text(
        "\n".join(
            [
                "ISO-10303-21;",
                "HEADER;",
                "FILE_NAME('b3_lower_chassis_assembly','2026-05-20T06:24:54',('Author'),(",
                "    'Open CASCADE'),'Open CASCADE STEP processor 7.8','build123d',",
                "  'Unknown');",
                "DATA;",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    changed = normalize_step_file(step_file)

    text = step_file.read_text(encoding="utf-8")
    assert changed is True
    assert "FILE_NAME('b3_lower_chassis_assembly','2000-01-01T00:00:00'" in text
    assert "2026-05-20T06:24:54" not in text


def test_normalize_step_file_replaces_wrapped_filename_timestamp(tmp_path: Path) -> None:
    step_file = tmp_path / "part.step"
    step_file.write_text(
        "\n".join(
            [
                "ISO-10303-21;",
                "HEADER;",
                "FILE_NAME('erb_lower_chassis_rear_panel_detachable',",
                "  '2026-05-20T07:17:42',('Author'),('Open CASCADE'),",
                "  'Open CASCADE STEP processor 7.8','build123d','Unknown');",
                "DATA;",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    changed = normalize_step_file(step_file)

    text = step_file.read_text(encoding="utf-8")
    assert changed is True
    assert "2000-01-01T00:00:00" in text
    assert "2026-05-20T07:17:42" not in text


def test_normalize_step_file_is_noop_when_header_is_absent(tmp_path: Path) -> None:
    step_file = tmp_path / "part.step"
    original = "ISO-10303-21;\nDATA;\n#1 = CARTESIAN_POINT('',(1.,2.,3.));\n"
    step_file.write_text(original, encoding="utf-8")

    changed = normalize_step_file(step_file)

    assert changed is False
    assert step_file.read_text(encoding="utf-8") == original
