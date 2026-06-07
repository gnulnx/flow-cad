from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flow_cad.editing.document import EditDocumentError, EditDocumentStore, normalized_document_payload
from flow_cad.editing.kernel import EditKernelError, bounding_box_payload
from flow_cad.editing.models import EditDocument, EditEntity, EditPoint
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
        if operation_type == "create_point":
            return self._append_create_point(document, payload)
        if operation_type in {"set_transform", "resize_box"}:
            entity_id = str(payload.get("entity_id") or "")
            if not entity_id:
                raise EditServiceError(f"`entity_id` is required for {operation_type}")
            return self._append_update_entity(document, entity_id, payload, operation_type=operation_type)
        raise EditServiceError(f"Unsupported edit operation type: {operation_type or '<missing>'}")

    def patch_entity(self, entity_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise EditServiceError("Edit entity patch payload must be an object")
        document = self._load_document(create=True)
        normalized_entity_id = entity_id_from_component_id(entity_id) if is_edit_component_id(entity_id) else entity_id
        has_size = "size_mm" in payload
        has_transform = any(key in payload for key in ("transform", "translation_mm", "rotation_deg"))
        if has_size and has_transform:
            raise EditServiceError("Patch either size or transform in one operation, not both")
        if has_size:
            return self._append_update_entity(document, normalized_entity_id, payload, operation_type="resize_box")
        if has_transform:
            return self._append_update_entity(document, normalized_entity_id, payload, operation_type="set_transform")
        raise EditServiceError("Edit entity patch requires `size_mm`, `transform`, `translation_mm`, or `rotation_deg`")

    def create_point(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise EditServiceError("Edit point payload must be an object")
        document = self._load_document(create=True)
        return self._append_create_point(document, payload)

    def patch_point(self, point_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise EditServiceError("Edit point patch payload must be an object")
        document = self._load_document(create=True)
        try:
            current = document.points[point_id]
        except KeyError as exc:
            raise EditServiceError(f"Edit point is not registered: {point_id}") from exc

        point_payload = {
            **current.to_payload(),
            **payload,
        }
        try:
            point = EditPoint.from_payload(point_id, point_payload)
        except ValueError as exc:
            raise EditServiceError(str(exc)) from exc

        operation_id = str(payload.get("id") or self._next_operation_id(document))
        self._ensure_operation_id_available(document, operation_id)
        operation = {
            "id": operation_id,
            "type": "update_point",
            "point_id": point.id,
            "timestamp": datetime.now(UTC).isoformat(),
            "previous_point": current.to_payload(),
            "point": point.to_payload(),
        }
        next_document = document.with_point_and_operation(point, operation)
        self.store.save(next_document)
        return self._point_result(next_document, point, operation)

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

    def _append_create_point(self, document: EditDocument, payload: dict[str, Any]) -> dict[str, Any]:
        point_id = str(payload.get("point_id") or payload.get("id") or self._next_point_id(document))
        if point_id in document.points:
            raise EditServiceError(f"Edit point already exists: {point_id}")
        if "position_mm" not in payload:
            raise EditServiceError("`position_mm` is required for create_point")

        try:
            point = EditPoint.from_payload(
                point_id,
                {
                    "position_mm": payload.get("position_mm"),
                    "coordinate_space": payload.get("coordinate_space", "world"),
                    "quality": payload.get("quality", "exact"),
                    "source": payload.get("source", {}),
                },
            )
        except ValueError as exc:
            raise EditServiceError(str(exc)) from exc

        operation_id = str(payload.get("operation_id") or self._next_operation_id(document))
        self._ensure_operation_id_available(document, operation_id)
        operation = {
            "id": operation_id,
            "type": "create_point",
            "point_id": point.id,
            "timestamp": datetime.now(UTC).isoformat(),
            "point": point.to_payload(),
        }
        next_document = document.with_point_and_operation(point, operation)
        self.store.save(next_document)
        return self._point_result(next_document, point, operation)

    def _point_result(self, document: EditDocument, point: EditPoint, operation: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "document_revision": document.revision,
            "operation": operation,
            "point": {
                "id": point.id,
                **point.to_payload(),
            },
            "changed_point_ids": [point.id],
            "document": normalized_document_payload(self.store, document),
        }

    def _append_update_entity(
        self,
        document: EditDocument,
        entity_id: str,
        payload: dict[str, Any],
        *,
        operation_type: str,
    ) -> dict[str, Any]:
        entity_id = entity_id_from_component_id(entity_id) if is_edit_component_id(entity_id) else entity_id
        try:
            current = document.entities[entity_id]
        except KeyError as exc:
            raise EditServiceError(f"Edit entity is not registered: {entity_id}") from exc

        entity_payload = current.to_payload()
        if operation_type == "resize_box":
            if "size_mm" not in payload:
                raise EditServiceError("`size_mm` is required for resize_box")
            entity_payload["size_mm"] = payload["size_mm"]
        elif operation_type == "set_transform":
            entity_payload["transform"] = self._merged_transform_payload(current, payload)
        else:
            raise EditServiceError(f"Unsupported edit operation type: {operation_type}")

        try:
            updated = EditEntity.from_payload(entity_id, entity_payload)
            bounds = bounding_box_payload(updated)
        except ValueError as exc:
            raise EditServiceError(str(exc)) from exc
        except EditKernelError as exc:
            raise EditServiceUnavailableError(str(exc)) from exc

        operation_id = str(payload.get("id") or self._next_operation_id(document))
        if any(operation.get("id") == operation_id for operation in document.operations):
            raise EditServiceError(f"Edit operation already exists: {operation_id}")

        operation = {
            "id": operation_id,
            "type": operation_type,
            "entity_id": updated.id,
            "timestamp": datetime.now(UTC).isoformat(),
            "previous_entity": current.to_payload(),
            "entity": updated.to_payload(),
        }
        next_document = document.with_entity_and_operation(updated, operation)
        self.store.save(next_document)
        return {
            "ok": True,
            "document_revision": next_document.revision,
            "operation": operation,
            "entity": {
                "id": updated.id,
                **updated.to_payload(),
                "bounds": bounds,
            },
            "changed_entity_ids": [updated.id],
            "document": normalized_document_payload(self.store, next_document),
        }

    def _load_document(self, *, create: bool) -> EditDocument:
        try:
            return self.store.load_or_create() if create else self.store.load()
        except EditDocumentError as exc:
            raise EditServiceError(str(exc)) from exc

    @staticmethod
    def _merged_transform_payload(entity: EditEntity, payload: dict[str, Any]) -> dict[str, Any]:
        raw_transform = payload.get("transform", {})
        if raw_transform is not None and not isinstance(raw_transform, dict):
            raise EditServiceError("`transform` must be an object")
        transform_payload = {
            **entity.transform.to_payload(),
            **(raw_transform or {}),
        }
        if "translation_mm" in payload:
            transform_payload["translation_mm"] = payload["translation_mm"]
        if "rotation_deg" in payload:
            transform_payload["rotation_deg"] = payload["rotation_deg"]
        return transform_payload

    @staticmethod
    def _next_entity_id(document: EditDocument, prefix: str) -> str:
        return _next_numbered_id(document.entities.keys(), prefix)

    @staticmethod
    def _next_operation_id(document: EditDocument) -> str:
        return _next_numbered_id((str(operation.get("id", "")) for operation in document.operations), "op")

    @staticmethod
    def _next_point_id(document: EditDocument) -> str:
        return _next_numbered_id(document.points.keys(), "point")

    @staticmethod
    def _ensure_operation_id_available(document: EditDocument, operation_id: str) -> None:
        if any(operation.get("id") == operation_id for operation in document.operations):
            raise EditServiceError(f"Edit operation already exists: {operation_id}")


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
