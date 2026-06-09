from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping


FLOW_CAD_HOME_ENV = "FLOW_CAD_HOME"
FLOW_CAD_USER_DIR = ".flow"
FLOW_CAD_CONFIG = "config.toml"


class FlowCadConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class AgentProfile:
    id: str
    provider: str
    label: str | None = None
    model: str | None = None
    reasoning: str | None = None
    endpoint: str | None = None
    command: str | None = None
    sandbox: str | None = None
    timeout_seconds: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        return self.label or self.id

    @property
    def normalized_provider(self) -> str:
        return self.provider.strip().lower().replace("_", "-")


@dataclass(frozen=True)
class AgentConfig:
    default_profile: str = "fake"
    profiles: dict[str, AgentProfile] = field(default_factory=dict)

    def profile(self, profile_id: str | None = None) -> AgentProfile:
        selected = profile_id or self.default_profile
        try:
            return self.profiles[selected]
        except KeyError as exc:
            raise FlowCadConfigError(f"Unknown agent profile {selected!r}") from exc


@dataclass(frozen=True)
class FlowCadConfig:
    user_config_path: Path
    project_config_path: Path | None
    agent: AgentConfig = field(default_factory=AgentConfig)
    sources: tuple[Path, ...] = ()

    def active_agent_profile(self, profile_id: str | None = None) -> AgentProfile:
        return self.agent.profile(profile_id)


def user_flow_dir(env: Mapping[str, str] | None = None) -> Path:
    values = env or os.environ
    configured = values.get(FLOW_CAD_HOME_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / FLOW_CAD_USER_DIR).resolve()


def user_config_path(env: Mapping[str, str] | None = None) -> Path:
    return user_flow_dir(env) / FLOW_CAD_CONFIG


def project_config_path(project_root: Path) -> Path:
    return project_root.resolve() / ".flow" / FLOW_CAD_CONFIG


def default_flow_config(
    *,
    user_path: Path | None = None,
    project_path: Path | None = None,
) -> FlowCadConfig:
    profiles = {
        "fake": AgentProfile(
            id="fake",
            provider="fake",
            label="Local test runtime",
            reasoning="none",
        ),
        "codex-medium": AgentProfile(
            id="codex-medium",
            provider="codex",
            label="Codex Medium",
            command="codex",
            reasoning="medium",
            sandbox="read-only",
            timeout_seconds=120.0,
        ),
        "codex-high": AgentProfile(
            id="codex-high",
            provider="codex",
            label="Codex High",
            command="codex",
            reasoning="high",
            sandbox="read-only",
            timeout_seconds=180.0,
        ),
        "codex-xhigh": AgentProfile(
            id="codex-xhigh",
            provider="codex",
            label="Codex XHigh",
            command="codex",
            reasoning="xhigh",
            sandbox="read-only",
            timeout_seconds=240.0,
        ),
    }
    return FlowCadConfig(
        user_config_path=(user_path or user_config_path()).resolve(),
        project_config_path=project_path.resolve() if project_path is not None else None,
        agent=AgentConfig(default_profile="fake", profiles=profiles),
    )


def load_flow_config(
    project_root: Path,
    *,
    env: Mapping[str, str] | None = None,
    user_path: Path | None = None,
    project_path: Path | None = None,
) -> FlowCadConfig:
    values = env or os.environ
    resolved_user_path = (user_path or user_config_path(values)).resolve()
    resolved_project_path = (project_path or project_config_path(project_root)).resolve()
    config = default_flow_config(user_path=resolved_user_path, project_path=resolved_project_path)
    sources: list[Path] = []
    for path in (resolved_user_path, resolved_project_path):
        if not path.exists():
            continue
        config = _merge_config(config, _read_config_file(path), source=path)
        sources.append(path)
    config = _apply_env_overrides(config, values)
    return replace(config, sources=tuple(sources))


def write_flow_config(config: FlowCadConfig, path: Path | None = None) -> Path:
    target = (path or config.user_config_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(_format_config_toml(config), encoding="utf-8")
    tmp.replace(target)
    return target


def _read_config_file(path: Path) -> dict[str, Any]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise FlowCadConfigError(f"Invalid Flow CAD config {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise FlowCadConfigError(f"Flow CAD config must be a TOML table: {path}")
    return data


def _merge_config(config: FlowCadConfig, raw: dict[str, Any], *, source: Path) -> FlowCadConfig:
    agent_table = raw.get("agent", {})
    if not isinstance(agent_table, dict):
        raise FlowCadConfigError(f"`agent` must be a table in {source}")

    default_profile = _optional_str(agent_table.get("default_profile")) or config.agent.default_profile
    profiles = dict(config.agent.profiles)
    profile_tables = agent_table.get("profiles", {})
    if profile_tables is None:
        profile_tables = {}
    if not isinstance(profile_tables, dict):
        raise FlowCadConfigError(f"`agent.profiles` must be a table in {source}")
    for profile_id, profile_table in profile_tables.items():
        if not isinstance(profile_table, dict):
            raise FlowCadConfigError(f"`agent.profiles.{profile_id}` must be a table in {source}")
        existing = profiles.get(str(profile_id))
        profiles[str(profile_id)] = _profile_from_table(str(profile_id), profile_table, existing)

    return replace(config, agent=AgentConfig(default_profile=default_profile, profiles=profiles))


def _profile_from_table(profile_id: str, table: dict[str, Any], existing: AgentProfile | None = None) -> AgentProfile:
    base = existing or AgentProfile(id=profile_id, provider="fake")
    known_keys = {
        "provider",
        "label",
        "model",
        "reasoning",
        "endpoint",
        "command",
        "sandbox",
        "timeout_seconds",
        "timeout",
    }
    timeout = table.get("timeout_seconds", table.get("timeout", base.timeout_seconds))
    extra = dict(base.extra)
    for key, value in table.items():
        if key not in known_keys:
            extra[key] = value
    return AgentProfile(
        id=profile_id,
        provider=_optional_str(table.get("provider")) or base.provider,
        label=_optional_str(table.get("label")) or base.label,
        model=_optional_str(table.get("model")) or base.model,
        reasoning=_optional_str(table.get("reasoning")) or base.reasoning,
        endpoint=_optional_str(table.get("endpoint")) or base.endpoint,
        command=_optional_str(table.get("command")) or base.command,
        sandbox=_optional_str(table.get("sandbox")) or base.sandbox,
        timeout_seconds=_optional_float(timeout),
        extra=extra,
    )


def _apply_env_overrides(config: FlowCadConfig, env: Mapping[str, str]) -> FlowCadConfig:
    runtime = (env.get("FLOW_CAD_AGENT_RUNTIME") or "").strip().lower()
    endpoint = (env.get("FLOW_CAD_AGENT_RUNTIME_ENDPOINT") or "").strip()
    if runtime == "codex":
        profile = AgentProfile(
            id="env-codex",
            provider="codex",
            label="Codex",
            command=env.get("FLOW_CAD_CODEX_COMMAND", "codex"),
            model=_optional_str(env.get("FLOW_CAD_CODEX_MODEL")),
            reasoning=_optional_str(env.get("FLOW_CAD_CODEX_REASONING")),
            sandbox=env.get("FLOW_CAD_CODEX_SANDBOX", "read-only"),
            timeout_seconds=_optional_float(env.get("FLOW_CAD_CODEX_TIMEOUT")) or 120.0,
        )
        profiles = {**config.agent.profiles, profile.id: profile}
        return replace(config, agent=AgentConfig(default_profile=profile.id, profiles=profiles))
    if runtime == "fake":
        return replace(config, agent=replace(config.agent, default_profile="fake"))
    if endpoint:
        profile = AgentProfile(
            id="env-local-endpoint",
            provider=runtime or "llama-cpp",
            label="Local endpoint",
            endpoint=endpoint,
            model=env.get("FLOW_CAD_AGENT_RUNTIME_MODEL", "llama3"),
            reasoning=_optional_str(env.get("FLOW_CAD_AGENT_RUNTIME_REASONING")),
        )
        profiles = {**config.agent.profiles, profile.id: profile}
        return replace(config, agent=AgentConfig(default_profile=profile.id, profiles=profiles))
    profile_id = _optional_str(env.get("FLOW_CAD_AGENT_PROFILE") or env.get("FLOW_CAD_AGENT_RUNTIME_PROFILE"))
    if profile_id:
        return replace(config, agent=replace(config.agent, default_profile=profile_id))
    return config


def _format_config_toml(config: FlowCadConfig) -> str:
    lines = [
        "[agent]",
        f"default_profile = {_toml_string(config.agent.default_profile)}",
        "",
    ]
    for profile_id in sorted(config.agent.profiles):
        profile = config.agent.profiles[profile_id]
        lines.append(f"[agent.profiles.{_quote_table_key(profile_id)}]")
        lines.append(f"provider = {_toml_string(profile.provider)}")
        if profile.label is not None:
            lines.append(f"label = {_toml_string(profile.label)}")
        if profile.model is not None:
            lines.append(f"model = {_toml_string(profile.model)}")
        if profile.reasoning is not None:
            lines.append(f"reasoning = {_toml_string(profile.reasoning)}")
        if profile.endpoint is not None:
            lines.append(f"endpoint = {_toml_string(profile.endpoint)}")
        if profile.command is not None:
            lines.append(f"command = {_toml_string(profile.command)}")
        if profile.sandbox is not None:
            lines.append(f"sandbox = {_toml_string(profile.sandbox)}")
        if profile.timeout_seconds is not None:
            lines.append(f"timeout_seconds = {profile.timeout_seconds:g}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _quote_table_key(value: str) -> str:
    if value.replace("-", "_").isalnum():
        return value
    return _toml_string(value)


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise FlowCadConfigError(f"Expected numeric timeout value, got {value!r}") from exc
