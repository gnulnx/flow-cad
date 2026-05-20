from pathlib import Path

from flow_cad.core.bundler import should_include


def test_bundler_can_filter_stale_step_exports() -> None:
    active_steps = {Path("step/lower_chassis/active.step")}

    assert should_include(Path("exports/step/lower_chassis/active.step"), Path("exports"), active_steps)
    assert not should_include(Path("exports/step/lower_chassis/stale.step"), Path("exports"), active_steps)
    assert should_include(Path("exports/freecad/model.FCStd"), Path("exports"), active_steps)
