from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flow_cad.editing.models import EditDocument


DEFAULT_DOCUMENT_RELATIVE_PATH = Path("flow") / "document.json"


class EditDocumentError(ValueError):
    pass


class EditDocumentStore:
    def __init__(self, project_root: Path, document_path: Path | None = None):
        self.project_root = project_root.resolve()
        self.path = document_path or self.project_root / DEFAULT_DOCUMENT_RELATIVE_PATH

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> EditDocument:
        if not self.path.exists():
            return EditDocument.empty()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise EditDocumentError(f"Could not parse edit document: {self.relative_path}") from exc
        if not isinstance(payload, dict):
            raise EditDocumentError(f"Edit document must be a JSON object: {self.relative_path}")
        try:
            return EditDocument.from_payload(payload)
        except ValueError as exc:
            raise EditDocumentError(f"Invalid edit document {self.relative_path}: {exc}") from exc

    def load_or_create(self) -> EditDocument:
        document = self.load()
        if not self.path.exists():
            self.save(document)
        return document

    def save(self, document: EditDocument) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(document.to_payload(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @property
    def relative_path(self) -> str:
        try:
            return str(self.path.relative_to(self.project_root))
        except ValueError:
            return str(self.path)


def normalized_document_payload(store: EditDocumentStore, document: EditDocument) -> dict[str, Any]:
    return {
        **document.to_payload(),
        "document_path": store.relative_path,
    }
