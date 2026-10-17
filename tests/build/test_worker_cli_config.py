from flow_cad.main import _build_runtime_config
from flow_cad.config import CadResources, FlowCadConfigError
import pytest


def test_worker_override_is_per_invocation(tmp_path):
    directory = tmp_path / '.flow'
    directory.mkdir()
    path = directory / 'config.toml'
    saved = '[cad]\nworkers = 2\nmemory_mb = 8192\n'
    path.write_text(saved)
    chosen = _build_runtime_config(tmp_path, 20)
    assert chosen.cad.workers == 20
    assert chosen.cad.native_threads == 1
    assert chosen.cad.memory_mb == 8192
    assert _build_runtime_config(tmp_path, None).cad.workers == 2
    assert path.read_text() == saved


def test_worker_count_remains_bounded():
    assert CadResources(workers=20).workers == 20
    with pytest.raises(FlowCadConfigError):
        CadResources(workers=65)
