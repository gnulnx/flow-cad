from pathlib import Path

from flow_cad.step_io import STABLE_STEP_TIMESTAMP, normalize_step_file, normalize_generated_occurrence_ids


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
                "FILE_NAME('flow_example_assembly','2026-05-20T06:24:54',('Author'),(",
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
    assert "FILE_NAME('flow_example_assembly','2000-01-01T00:00:00'" in text
    assert "2026-05-20T06:24:54" not in text


def test_normalize_step_file_replaces_wrapped_filename_timestamp(tmp_path: Path) -> None:
    step_file = tmp_path / "part.step"
    step_file.write_text(
        "\n".join(
            [
                "ISO-10303-21;",
                "HEADER;",
                "FILE_NAME('flow_example_wrapped_part',",
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


def test_generated_occurrence_ids_remove_only_counter_offset(tmp_path: Path) -> None:
    path = tmp_path / "assembly.step"
    original = (
        "#7 = NEXT_ASSEMBLY_USAGE_OCCURRENCE('104','left 104','',#2,#3,$);\n"
        "#8 = NEXT_ASSEMBLY_USAGE_OCCURRENCE(\n  '103','right','',#2,#4,$);\n"
        "#9 = CARTESIAN_POINT('',(103.,104.,0.));\n"
    )
    path.write_text(original)
    assert normalize_generated_occurrence_ids(path) is True
    expected = original.replace("('104',", "('2',").replace("'103','right'", "'1','right'")
    assert path.read_text() == expected
    assert normalize_generated_occurrence_ids(path) is False
    assert path.read_text() == expected


def test_no_generated_occurrences_preserves_step_bytes(tmp_path: Path) -> None:
    path = tmp_path / "solid.step"
    original = "#1 = CARTESIAN_POINT('',(1.,2.,3.));\n"
    path.write_text(original)
    assert normalize_generated_occurrence_ids(path) is False
    assert path.read_text() == original
