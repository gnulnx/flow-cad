from __future__ import annotations

from pathlib import Path

from flow_cad.config import AgentConfig, AgentProfile, FlowCadConfig, load_flow_config, write_flow_config
from flow_cad.project import init_project, load_project


def test_flow_config_loads_user_and_project_agent_profiles(tmp_path: Path) -> None:
    user_config = tmp_path / "home" / ".flow" / "config.toml"
    project_root = tmp_path / "project"
    project_config = project_root / ".flow" / "config.toml"
    user_config.parent.mkdir(parents=True)
    project_config.parent.mkdir(parents=True)
    user_config.write_text(
        """
[agent]
default_profile = "codex-high"

[agent.profiles.codex-high]
provider = "codex"
label = "Codex High"
model = "gpt-test"
reasoning = "high"
command = "codex"
timeout_seconds = 45
""",
        encoding="utf-8",
    )
    project_config.write_text(
        """
[agent]
default_profile = "local-fast"

[agent.profiles.local-fast]
provider = "llama-cpp"
label = "Local Fast"
endpoint = "http://127.0.0.1:1234/v1"
model = "local-test"
reasoning = "none"
""",
        encoding="utf-8",
    )

    config = load_flow_config(project_root, user_path=user_config)

    profile = config.active_agent_profile()
    assert profile.id == "local-fast"
    assert profile.provider == "llama-cpp"
    assert profile.endpoint == "http://127.0.0.1:1234/v1"
    assert config.agent.profiles["codex-high"].model == "gpt-test"
    assert config.sources == (user_config.resolve(), project_config.resolve())


def test_flow_config_env_runtime_overrides_disk_config(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_config = project_root / ".flow" / "config.toml"
    project_config.parent.mkdir(parents=True)
    project_config.write_text(
        """
[agent]
default_profile = "local-fast"

[agent.profiles.local-fast]
provider = "llama-cpp"
endpoint = "http://127.0.0.1:1234/v1"
""",
        encoding="utf-8",
    )

    config = load_flow_config(
        project_root,
        user_path=tmp_path / "missing-user.toml",
        env={
            "FLOW_CAD_AGENT_RUNTIME": "codex",
            "FLOW_CAD_CODEX_MODEL": "gpt-test",
            "FLOW_CAD_CODEX_REASONING": "xhigh",
            "FLOW_CAD_CODEX_TIMEOUT": "77",
        },
    )

    profile = config.active_agent_profile()
    assert profile.id == "env-codex"
    assert profile.provider == "codex"
    assert profile.model == "gpt-test"
    assert profile.reasoning == "xhigh"
    assert profile.timeout_seconds == 77.0


def test_write_flow_config_round_trips(tmp_path: Path) -> None:
    target = tmp_path / "home" / ".flow" / "config.toml"
    agent = load_flow_config(tmp_path, user_path=tmp_path / "missing.toml").agent
    config = FlowCadConfig(
        user_config_path=target,
        project_config_path=None,
        agent=AgentConfig(
            default_profile="openai.codex-medium",
            profiles={
                **agent.profiles,
                "openai.codex-medium": AgentProfile(
                    id="openai.codex-medium",
                    provider="codex",
                    label="Codex Medium",
                    model="gpt-test",
                ),
            },
        ),
    )

    written = write_flow_config(config)
    reloaded = load_flow_config(tmp_path, user_path=written)

    assert written == target.resolve()
    assert reloaded.agent.default_profile == config.agent.default_profile
    assert "codex-medium" in reloaded.agent.profiles
    assert reloaded.agent.profiles["openai.codex-medium"].model == "gpt-test"


def test_loaded_project_exposes_local_config_path_and_object(tmp_path: Path) -> None:
    init_project(tmp_path)
    (tmp_path / ".flow" / "config.toml").write_text(
        """
[agent]
default_profile = "codex-medium"
""",
        encoding="utf-8",
    )

    project = load_project(tmp_path, fallback_to_bundled=False)

    assert project.paths.config == tmp_path / ".flow" / "config.toml"
    assert project.config.project_config_path == (tmp_path / ".flow" / "config.toml").resolve()
    assert project.config.active_agent_profile().id == "codex-medium"
