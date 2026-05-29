__version__ = "0.1.0"


def __getattr__(name: str):
    if name == "ChassisParams":
        from .params import ChassisParams

        return ChassisParams
    if name in {"build_parts", "cli"}:
        from .main import build_parts, cli

        return {"build_parts": build_parts, "cli": cli}[name]
    raise AttributeError(name)
