from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class PartRole(StrEnum):
    PRINTABLE = "printable"
    REFERENCE = "reference"
    INSPECTION = "inspection"
    LEGACY = "legacy"


PartFactory = Callable[[Any], object]


@dataclass(frozen=True)
class PartDefinition:
    id: str
    module_id: str
    filename: str
    factory: PartFactory
    role: PartRole = PartRole.PRINTABLE
    material: str = "PETG"
    shell_count: int = 4
    infill_density: float = 0.4
    version: str = ""
    family: str = ""
    assembly_ids: tuple[str, ...] = ()
    compatible_versions: tuple[str, ...] = ()
    mass_kg: float | None = None
    center_of_mass_mm: tuple[float, float, float] | None = None
    inertia_kg_m2: tuple[float, float, float, float, float, float] | None = None
    mass_source: str = "unset"

    @property
    def is_printable(self) -> bool:
        return self.role == PartRole.PRINTABLE

    @property
    def export_family(self) -> str:
        return self.family or self.module_id

    @property
    def export_subdir(self) -> Path:
        if self.version:
            return Path(self.version) / self.export_family
        return Path(self.export_family)


def definition_export_subdir(definition: Any) -> Path:
    subdir = getattr(definition, "export_subdir", None)
    if subdir is not None:
        return Path(subdir)
    return Path(getattr(definition, "module_id", ""))
