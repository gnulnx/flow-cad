from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flow_cad.editing.document import EditDocumentError, EditDocumentStore, normalized_document_payload
from flow_cad.editing.kernel import EditKernelError, bounding_box_payload
from flow_cad.editing.models import EditDocument, EditEntity
from flow_cad.project import FlowCadProject


EDIT_COMPONENT_PREFIX = "edit:"


class EditServiceError(RuntimeError):
    status_code = 400


class EditServiceUnavailableError(EditServiceError):
    status_code = 503


class EditService:
    def __init__(self, project: FlowCadProject, document_path: Path | None = None):
        self.project = project
        self.store = EditDocumentStore(project.root, document_path=document_path)

    def status(self) -> dict[str, Any]:
        document = self._load_document(create=False)
        return {
            "editing_available": True,
            "document_path": self.store.relative_path,
            "document_exists": self.store.exists(),
            "document_revision": document.revision,
            "active_session_id": None,
            "can_undo": bool(document.operations),
            "can_redo": False,
            "tool_presets": {
                "holes": {},
            },
        }

    def document(self) -> dict[str, Any]:
        document = self._load_document(create=True)
        return normalized_document_payload(self.store, document)

    def document_model(self) -> EditDocument:
        return self._load_document(create=False)

    def iter_entities(self) -> list[EditEntity]:
        return list(self.document_model().entities.values())

    def entity_for_component_id(self, component_id: str) -> EditEntity:
        entity_id = entity_id_from_component_id(component_id)
        document = self.document_model()
        try:
            return document.entities[entity_id]
        except KeyError as exc:
            raise EditServiceError(f"Edit entity is not registered: {entity_id}") from exc

    def append_operation(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise EditServiceError("Edit operation payload must be an object")

        document = self._load_document(create=True)
        operation_type = str(payload.get("type") or "")
        if operation_type == "create_box":
            return self._append_create_box(document, payload)
        raise EditServiceError(f"Unsupported edit operation type: {operation_type or '<missing>'}")

    def _append_create_box(self, document: EditDocument, payload: dict[str, Any]) -> dict[str, Any]:
        entity_id = str(payload.get("entity_id") or self._next_entity_id(document, "box"))
        if entity_id in document.entities:
            raise EditServiceError(f"Edit entity already exists: {entity_id}")

        raw_transform = payload.get("transform", {})
        if raw_transform is not None and not isinstance(raw_transform, dict):
            raise EditServiceError("`transform` must be an object")
        transform_payload = raw_transform or {}
        if "translation_mm" in payload or "rotation_deg" in payload:
            transform_payload = {
                **transform_payload,
                "translation_mm": payload.get("translation_mm", transform_payload.get("translation_mm")),
                "rotation_deg": payload.get("rotation_deg", transform_payload.get("rotation_deg")),
            }

        try:
            entity = EditEntity.from_payload(
                entity_id,
                {
                    "kind": "primitive_box",
                    "name": payload.get("name") or entity_id,
                    "size_mm": payload.get("size_mm", (20.0, 20.0, 20.0)),
                    "transform": transform_payload,
                    "role": payload.get("role") or "inspection",
                },
            )
            bounds = bounding_box_payload(entity)
        except ValueError as exc:
            raise EditServiceError(str(exc)) from exc
        except EditKernelError as exc:
            raise EditServiceUnavailableError(str(exc)) from exc

        operation_id = str(payload.get("id") or self._next_operation_id(document))
        if any(operation.get("id") == operation_id for operation in document.operations):
            raise EditServiceError(f"Edit operation already exists: {operation_id}")

        operation = {
            "id": operation_id,
            "type": "create_box",
            "entity_id": entity.id,
            "timestamp": datetime.now(UTC).isoformat(),
            "size_mm": list(entity.size_mm),
            "transform": entity.transform.to_payload(),
            "role": entity.role,
        }
        next_document = document.with_entity_and_operation(entity, operation)
        self.store.save(next_document)
        return {
            "ok": True,
            "document_revision": next_document.revision,
            "operation": operation,
            "entity": {
                "id": entity.id,
                **entity.to_payload(),
                "bounds": bounds,
            },
            "changed_entity_ids": [entity.id],
            "document": normalized_document_payload(self.store, next_document),
        }

    def _load_document(self, *, create: bool) -> EditDocument:
        try:
            return self.store.load_or_create() if create else self.store.load()
        except EditDocumentError as exc:
            raise EditServiceError(str(exc)) from exc

    @staticmethod
    def _next_entity_id(document: EditDocument, prefix: str) -> str:
        return _next_numbered_id(document.entities.keys(), prefix)

    @staticmethod
    def _next_operation_id(document: EditDocument) -> str:
        return _next_numbered_id((str(operation.get("id", "")) for operation in document.operations), "op")


def _next_numbered_id(existing: Any, prefix: str) -> str:
    taken = {str(value) for value in existing}
    index = 1
    while True:
        candidate = f"{prefix}_{index:03d}"
        if candidate not in taken:
            return candidate
        index += 1


def component_id_for_entity(entity_id: str) -> str:
    return f"{EDIT_COMPONENT_PREFIX}{entity_id}"


def is_edit_component_id(component_id: str) -> bool:
    return component_id.startswith(EDIT_COMPONENT_PREFIX)


def entity_id_from_component_id(component_id: str) -> str:
    if not is_edit_component_id(component_id):
        raise EditServiceError(f"Not an edit entity component id: {component_id}")
    entity_id = component_id.removeprefix(EDIT_COMPONENT_PREFIX)
    if not entity_id:
        raise EditServiceError("Edit entity component id is missing an entity id")
    return entity_id
