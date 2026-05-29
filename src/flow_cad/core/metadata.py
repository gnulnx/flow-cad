from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class PartRole(StrEnum):
    PRINTABLE = "printable"
    REFERENCE = "reference"
    INSPECTION = "inspection"


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

    @property
    def is_printable(self) -> bool:
        return self.role == PartRole.PRINTABLE
