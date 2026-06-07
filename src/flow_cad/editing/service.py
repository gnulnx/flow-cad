from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flow_cad.editing.document import EditDocumentError, EditDocumentStore, normalized_document_payload
from flow_cad.editing.kernel import EditKernelError, bounding_box_payload
from flow_cad.editing.models import EditBooleanOperation, EditDocument, EditEntity, EditHoleCut, EditPoint, Vector3
from flow_cad.editing.presets import hole_preset, hole_presets_payload
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
        self._redo_operations: list[dict[str, Any]] = []

    def status(self) -> dict[str, Any]:
        document = self._load_document(create=False)
        return {
            "editing_available": True,
            "document_path": self.store.relative_path,
            "document_exists": self.store.exists(),
            "document_revision": document.revision,
            "active_session_id": None,
            "can_undo": bool(document.operations),
            "can_redo": bool(self._redo_operations),
            "tool_presets": {
                "holes": hole_presets_payload(),
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
            return self._operation_result(self._append_create_box(document, payload))
        if operation_type == "create_point":
            return self._operation_result(self._append_create_point(document, payload))
        if operation_type in {"set_transform", "resize_box"}:
            entity_id = str(payload.get("entity_id") or "")
            if not entity_id:
                raise EditServiceError(f"`entity_id` is required for {operation_type}")
            return self._operation_result(self._append_update_entity(document, entity_id, payload, operation_type=operation_type))
        if operation_type == "cut_hole":
            return self._operation_result(self._append_cut_hole(document, payload))
        if operation_type in {"fuse", "cut"}:
            return self._operation_result(self._append_boolean(document, payload, operation_type=operation_type))
        if operation_type == "split":
            return self._operation_result(self._append_split(document, payload))
        if operation_type == "delete_entity":
            entity_id = str(payload.get("entity_id") or "")
            if not entity_id:
                raise EditServiceError("`entity_id` is required for delete_entity")
            return self.delete_entity(entity_id, payload)
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
            return self._operation_result(self._append_update_entity(document, normalized_entity_id, payload, operation_type="resize_box"))
        if has_transform:
            return self._operation_result(self._append_update_entity(document, normalized_entity_id, payload, operation_type="set_transform"))
        raise EditServiceError("Edit entity patch requires `size_mm`, `transform`, `translation_mm`, or `rotation_deg`")

    def create_point(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise EditServiceError("Edit point payload must be an object")
        document = self._load_document(create=True)
        return self._operation_result(self._append_create_point(document, payload))

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
        return self._operation_result(self._point_result(next_document, point, operation))

    def create_hole(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise EditServiceError("Edit hole payload must be an object")
        document = self._load_document(create=True)
        return self._operation_result(self._append_cut_hole(document, {**payload, "type": "cut_hole"}))

    def create_boolean(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise EditServiceError("Edit boolean payload must be an object")
        operation_type = str(payload.get("operation") or payload.get("type") or "")
        if operation_type not in {"fuse", "cut"}:
            raise EditServiceError("Edit boolean operation must be `fuse` or `cut`")
        document = self._load_document(create=True)
        return self._operation_result(self._append_boolean(document, {**payload, "type": operation_type}, operation_type=operation_type))

    def create_split(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise EditServiceError("Edit split payload must be an object")
        document = self._load_document(create=True)
        return self._operation_result(self._append_split(document, {**payload, "type": "split"}))

    def delete_entity(self, entity_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        document = self._load_document(create=True)
        normalized_entity_id = entity_id_from_component_id(entity_id) if is_edit_component_id(entity_id) else entity_id
        try:
            current = document.entities[normalized_entity_id]
        except KeyError as exc:
            raise EditServiceError(f"Edit entity is not registered: {normalized_entity_id}") from exc

        self._ensure_entity_can_be_deleted(document, normalized_entity_id)
        operation_id = str(payload.get("id") or payload.get("operation_id") or self._next_operation_id(document))
        self._ensure_operation_id_available(document, operation_id)
        operation = {
            "id": operation_id,
            "type": "delete_entity",
            "entity_id": current.id,
            "timestamp": datetime.now(UTC).isoformat(),
            "previous_entity": current.to_payload(),
        }
        entities = {**document.entities}
        entities.pop(current.id)
        next_document = EditDocument(
            schema_version=document.schema_version,
            document_id=document.document_id,
            units=document.units,
            revision=document.revision + 1,
            entities=entities,
            points=document.points,
            operations=[*document.operations, operation],
        )
        self.store.save(next_document)
        return self._operation_result({
            "ok": True,
            "document_revision": next_document.revision,
            "operation": operation,
            "deleted_entity_id": current.id,
            "changed_entity_ids": [current.id],
            "document": normalized_document_payload(self.store, next_document),
        })

    def undo(self) -> dict[str, Any]:
        document = self._load_document(create=True)
        if not document.operations:
            raise EditServiceError("No edit operation is available to undo")
        operation = document.operations[-1]
        next_document = self._document_after_undo(document, operation)
        self.store.save(next_document)
        self._redo_operations.append(operation)
        return {
            "ok": True,
            "document_revision": next_document.revision,
            "undone_operation": operation,
            "document": normalized_document_payload(self.store, next_document),
        }

    def redo(self) -> dict[str, Any]:
        document = self._load_document(create=True)
        if not self._redo_operations:
            raise EditServiceError("No edit operation is available to redo")
        operation = self._redo_operations.pop()
        next_document = self._document_after_redo(document, operation)
        self.store.save(next_document)
        return {
            "ok": True,
            "document_revision": next_document.revision,
            "redone_operation": operation,
            "document": normalized_document_payload(self.store, next_document),
        }

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

    def _append_cut_hole(self, document: EditDocument, payload: dict[str, Any]) -> dict[str, Any]:
        target_entity_id = str(payload.get("target_entity_id") or payload.get("entity_id") or "")
        if is_edit_component_id(target_entity_id):
            target_entity_id = entity_id_from_component_id(target_entity_id)
        if not target_entity_id:
            raise EditServiceError("`target_entity_id` is required for cut_hole")
        point_id = str(payload.get("point_id") or "")
        if not point_id:
            raise EditServiceError("`point_id` is required for cut_hole")

        try:
            current = document.entities[target_entity_id]
        except KeyError as exc:
            raise EditServiceError(f"Edit entity is not registered: {target_entity_id}") from exc
        try:
            point = document.points[point_id]
        except KeyError as exc:
            raise EditServiceError(f"Edit point is not registered: {point_id}") from exc

        if point.quality != "exact":
            raise EditServiceError("Approximate edit points cannot drive exact through-hole cuts")
        if point.coordinate_space != "world":
            raise EditServiceError("Only world-space edit points can drive through-hole cuts in V1")

        preset_id = str(payload.get("preset") or "m4_clearance")
        try:
            preset = hole_preset(preset_id)
            axis = _normalized_cardinal_axis(payload.get("axis", (0.0, 0.0, 1.0)))
        except ValueError as exc:
            raise EditServiceError(str(exc)) from exc

        hole_id = str(payload.get("hole_id") or self._next_hole_id(document))
        if any(hole.id == hole_id for entity in document.entities.values() for hole in entity.holes):
            raise EditServiceError(f"Edit hole already exists: {hole_id}")

        try:
            hole = EditHoleCut.from_payload(
                hole_id,
                {
                    "point_id": point.id,
                    "position_mm": point.position_mm,
                    "axis": axis,
                    "preset": preset.id,
                    "diameter_mm": preset.diameter_mm,
                    "through": True,
                },
            )
            updated = EditEntity.from_payload(
                current.id,
                {
                    **current.to_payload(),
                    "holes": [hole.to_payload() for hole in (*current.holes, hole)],
                },
            )
        except ValueError as exc:
            raise EditServiceError(str(exc)) from exc

        operation_id = str(payload.get("id") or payload.get("operation_id") or self._next_operation_id(document))
        self._ensure_operation_id_available(document, operation_id)
        operation = {
            "id": operation_id,
            "type": "cut_hole",
            "target_entity_id": updated.id,
            "point_id": point.id,
            "hole_id": hole.id,
            "timestamp": datetime.now(UTC).isoformat(),
            "preset": preset.id,
            "diameter_mm": preset.diameter_mm,
            "axis": list(axis),
            "through": True,
        }
        next_document = document.with_entity_and_operation(updated, operation)
        try:
            bounds = bounding_box_payload(updated, document=next_document)
        except EditKernelError as exc:
            raise EditServiceUnavailableError(str(exc)) from exc
        self.store.save(next_document)
        return {
            "ok": True,
            "document_revision": next_document.revision,
            "operation": operation,
            "hole": hole.to_payload(),
            "entity": {
                "id": updated.id,
                **updated.to_payload(),
                "bounds": bounds,
            },
            "changed_entity_ids": [updated.id],
            "document": normalized_document_payload(self.store, next_document),
        }

    def _append_boolean(self, document: EditDocument, payload: dict[str, Any], *, operation_type: str) -> dict[str, Any]:
        target_entity_id = str(payload.get("target_entity_id") or "")
        tool_entity_id = str(payload.get("tool_entity_id") or "")
        if is_edit_component_id(target_entity_id):
            target_entity_id = entity_id_from_component_id(target_entity_id)
        if is_edit_component_id(tool_entity_id):
            tool_entity_id = entity_id_from_component_id(tool_entity_id)
        if not target_entity_id:
            raise EditServiceError("`target_entity_id` is required for boolean operations")
        if not tool_entity_id:
            raise EditServiceError("`tool_entity_id` is required for boolean operations")
        if target_entity_id == tool_entity_id:
            raise EditServiceError("Boolean target and tool must be different edit entities")

        try:
            current_target = document.entities[target_entity_id]
        except KeyError as exc:
            raise EditServiceError(f"Edit entity is not registered: {target_entity_id}") from exc
        try:
            current_tool = document.entities[tool_entity_id]
        except KeyError as exc:
            raise EditServiceError(f"Edit entity is not registered: {tool_entity_id}") from exc

        boolean_id = str(payload.get("boolean_id") or self._next_boolean_id(document))
        if any(operation.id == boolean_id for entity in document.entities.values() for operation in entity.booleans):
            raise EditServiceError(f"Edit boolean already exists: {boolean_id}")

        try:
            boolean = EditBooleanOperation.from_payload(
                boolean_id,
                {
                    "type": operation_type,
                    "tool_entity_id": current_tool.id,
                    "keep_tool": True,
                },
            )
            updated_target = EditEntity.from_payload(
                current_target.id,
                {
                    **current_target.to_payload(),
                    "booleans": [operation.to_payload() for operation in (*current_target.booleans, boolean)],
                },
            )
            updated_tool = EditEntity.from_payload(
                current_tool.id,
                {
                    **current_tool.to_payload(),
                    "role": str(payload.get("tool_role") or "construction"),
                },
            )
        except ValueError as exc:
            raise EditServiceError(str(exc)) from exc

        operation_id = str(payload.get("id") or payload.get("operation_id") or self._next_operation_id(document))
        self._ensure_operation_id_available(document, operation_id)
        operation = {
            "id": operation_id,
            "type": operation_type,
            "target_entity_id": updated_target.id,
            "tool_entity_id": updated_tool.id,
            "boolean_id": boolean.id,
            "timestamp": datetime.now(UTC).isoformat(),
            "keep_tool": True,
            "tool_role": updated_tool.role,
            "previous_tool_entity": current_tool.to_payload(),
        }
        next_document = document.with_entities_and_operation((updated_target, updated_tool), operation)
        try:
            bounds = bounding_box_payload(updated_target, document=next_document)
        except EditKernelError as exc:
            raise EditServiceUnavailableError(str(exc)) from exc
        self.store.save(next_document)
        return {
            "ok": True,
            "document_revision": next_document.revision,
            "operation": operation,
            "boolean": boolean.to_payload(),
            "entity": {
                "id": updated_target.id,
                **updated_target.to_payload(),
                "bounds": bounds,
            },
            "tool_entity": {
                "id": updated_tool.id,
                **updated_tool.to_payload(),
            },
            "changed_entity_ids": [updated_target.id, updated_tool.id],
            "document": normalized_document_payload(self.store, next_document),
        }

    def _append_split(self, document: EditDocument, payload: dict[str, Any]) -> dict[str, Any]:
        target_entity_id = str(payload.get("target_entity_id") or payload.get("entity_id") or "")
        if is_edit_component_id(target_entity_id):
            target_entity_id = entity_id_from_component_id(target_entity_id)
        if not target_entity_id:
            raise EditServiceError("`target_entity_id` is required for split")
        try:
            current = document.entities[target_entity_id]
        except KeyError as exc:
            raise EditServiceError(f"Edit entity is not registered: {target_entity_id}") from exc

        try:
            current_bounds = bounding_box_payload(current, document=document)
            plane_origin = _vector3_payload(
                payload.get("plane_origin_mm") or payload.get("origin_mm") or current_bounds["center_mm"],
                field_name="plane_origin_mm",
            )
            plane_normal = _normalized_vector3_payload(
                payload.get("plane_normal") or payload.get("axis") or (0.0, 0.0, 1.0),
                field_name="plane_normal",
            )
        except ValueError as exc:
            raise EditServiceError(str(exc)) from exc
        except EditKernelError as exc:
            raise EditServiceUnavailableError(str(exc)) from exc

        raw_result_ids = payload.get("result_entity_ids", {})
        if raw_result_ids is not None and not isinstance(raw_result_ids, dict):
            raise EditServiceError("`result_entity_ids` must be an object")
        result_ids = raw_result_ids or {}
        top_id = str(result_ids.get("top") or f"{target_entity_id}_split_top")
        bottom_id = str(result_ids.get("bottom") or f"{target_entity_id}_split_bottom")
        if top_id == bottom_id:
            raise EditServiceError("Split result entity ids must be different")
        existing_ids = set(document.entities)
        conflicts = sorted(existing_ids.intersection({top_id, bottom_id}))
        if conflicts:
            raise EditServiceError(f"Split result entity already exists: {', '.join(conflicts)}")

        operation_id = str(payload.get("id") or payload.get("operation_id") or self._next_operation_id(document))
        self._ensure_operation_id_available(document, operation_id)
        operation = {
            "id": operation_id,
            "type": "split",
            "target_entity_id": current.id,
            "result_entity_ids": {
                "top": top_id,
                "bottom": bottom_id,
            },
            "timestamp": datetime.now(UTC).isoformat(),
            "plane_origin_mm": list(plane_origin),
            "plane_normal": list(plane_normal),
            "previous_source_entity": current.to_payload(),
        }
        try:
            source = EditEntity.from_payload(current.id, {**current.to_payload(), "role": "construction"})
            top = EditEntity.from_payload(
                top_id,
                {
                    "kind": "derived_split",
                    "name": top_id,
                    "source_entity_id": current.id,
                    "split_plane": {
                        "origin_mm": plane_origin,
                        "normal": plane_normal,
                    },
                    "split_keep": "top",
                    "size_mm": current_bounds["size_mm"],
                    "role": current.role,
                },
            )
            bottom = EditEntity.from_payload(
                bottom_id,
                {
                    "kind": "derived_split",
                    "name": bottom_id,
                    "source_entity_id": current.id,
                    "split_plane": {
                        "origin_mm": plane_origin,
                        "normal": plane_normal,
                    },
                    "split_keep": "bottom",
                    "size_mm": current_bounds["size_mm"],
                    "role": current.role,
                },
            )
        except ValueError as exc:
            raise EditServiceError(str(exc)) from exc

        next_document = document.with_entities_and_operation((source, top, bottom), operation)
        try:
            top_bounds = bounding_box_payload(top, document=next_document)
            bottom_bounds = bounding_box_payload(bottom, document=next_document)
        except EditKernelError as exc:
            raise EditServiceUnavailableError(str(exc)) from exc
        self.store.save(next_document)
        return {
            "ok": True,
            "document_revision": next_document.revision,
            "operation": operation,
            "entities": [
                {
                    "id": top.id,
                    **top.to_payload(),
                    "bounds": top_bounds,
                },
                {
                    "id": bottom.id,
                    **bottom.to_payload(),
                    "bounds": bottom_bounds,
                },
            ],
            "source_entity": {
                "id": source.id,
                **source.to_payload(),
            },
            "changed_entity_ids": [source.id, top.id, bottom.id],
            "document": normalized_document_payload(self.store, next_document),
        }

    def _document_after_undo(self, document: EditDocument, operation: dict[str, Any]) -> EditDocument:
        entities = {**document.entities}
        points = {**document.points}
        operation_type = str(operation.get("type") or "")

        if operation_type == "create_box":
            entities.pop(str(operation.get("entity_id") or ""), None)
        elif operation_type == "delete_entity":
            entity_id = str(operation.get("entity_id") or "")
            previous = operation.get("previous_entity")
            if not entity_id or not isinstance(previous, dict):
                raise EditServiceError("Cannot undo malformed delete_entity operation")
            entities[entity_id] = EditEntity.from_payload(entity_id, previous)
        elif operation_type in {"set_transform", "resize_box"}:
            entity_id = str(operation.get("entity_id") or "")
            previous = operation.get("previous_entity")
            if not entity_id or not isinstance(previous, dict):
                raise EditServiceError(f"Cannot undo malformed {operation_type} operation")
            entities[entity_id] = EditEntity.from_payload(entity_id, previous)
        elif operation_type == "create_point":
            points.pop(str(operation.get("point_id") or ""), None)
        elif operation_type == "update_point":
            point_id = str(operation.get("point_id") or "")
            previous = operation.get("previous_point")
            if not point_id or not isinstance(previous, dict):
                raise EditServiceError("Cannot undo malformed update_point operation")
            points[point_id] = EditPoint.from_payload(point_id, previous)
        elif operation_type == "cut_hole":
            entity_id = str(operation.get("target_entity_id") or "")
            hole_id = str(operation.get("hole_id") or "")
            current = entities.get(entity_id)
            if current is None or not hole_id:
                raise EditServiceError("Cannot undo malformed cut_hole operation")
            entities[entity_id] = EditEntity.from_payload(
                entity_id,
                {
                    **current.to_payload(),
                    "holes": [hole.to_payload() for hole in current.holes if hole.id != hole_id],
                },
            )
        elif operation_type in {"fuse", "cut"}:
            entity_id = str(operation.get("target_entity_id") or "")
            boolean_id = str(operation.get("boolean_id") or "")
            current = entities.get(entity_id)
            if current is None or not boolean_id:
                raise EditServiceError(f"Cannot undo malformed {operation_type} operation")
            entities[entity_id] = EditEntity.from_payload(
                entity_id,
                {
                    **current.to_payload(),
                    "booleans": [boolean.to_payload() for boolean in current.booleans if boolean.id != boolean_id],
                },
            )
            tool_entity_id = str(operation.get("tool_entity_id") or "")
            previous_tool = operation.get("previous_tool_entity")
            if tool_entity_id and isinstance(previous_tool, dict):
                entities[tool_entity_id] = EditEntity.from_payload(tool_entity_id, previous_tool)
        elif operation_type == "split":
            result_ids = operation.get("result_entity_ids")
            if not isinstance(result_ids, dict):
                raise EditServiceError("Cannot undo malformed split operation")
            for result_id in result_ids.values():
                entities.pop(str(result_id), None)
            source_id = str(operation.get("target_entity_id") or "")
            previous_source = operation.get("previous_source_entity")
            if source_id and isinstance(previous_source, dict):
                entities[source_id] = EditEntity.from_payload(source_id, previous_source)
        else:
            raise EditServiceError(f"Cannot undo unsupported edit operation type: {operation_type or '<missing>'}")

        return EditDocument(
            schema_version=document.schema_version,
            document_id=document.document_id,
            units=document.units,
            revision=document.revision + 1,
            entities=entities,
            points=points,
            operations=document.operations[:-1],
        )

    def _document_after_redo(self, document: EditDocument, operation: dict[str, Any]) -> EditDocument:
        entities = {**document.entities}
        points = {**document.points}
        operation_type = str(operation.get("type") or "")

        if operation_type == "create_box":
            entity_id = str(operation.get("entity_id") or "")
            if not entity_id:
                raise EditServiceError("Cannot redo malformed create_box operation")
            entities[entity_id] = EditEntity.from_payload(
                entity_id,
                {
                    "kind": "primitive_box",
                    "name": operation.get("name") or entity_id,
                    "size_mm": operation.get("size_mm", (20.0, 20.0, 20.0)),
                    "transform": operation.get("transform", {}),
                    "role": operation.get("role") or "inspection",
                },
            )
        elif operation_type == "delete_entity":
            entities.pop(str(operation.get("entity_id") or ""), None)
        elif operation_type in {"set_transform", "resize_box"}:
            entity_id = str(operation.get("entity_id") or "")
            entity = operation.get("entity")
            if not entity_id or not isinstance(entity, dict):
                raise EditServiceError(f"Cannot redo malformed {operation_type} operation")
            entities[entity_id] = EditEntity.from_payload(entity_id, entity)
        elif operation_type in {"create_point", "update_point"}:
            point_id = str(operation.get("point_id") or "")
            point = operation.get("point")
            if not point_id or not isinstance(point, dict):
                raise EditServiceError(f"Cannot redo malformed {operation_type} operation")
            points[point_id] = EditPoint.from_payload(point_id, point)
        elif operation_type == "cut_hole":
            entity_id = str(operation.get("target_entity_id") or "")
            point_id = str(operation.get("point_id") or "")
            hole_id = str(operation.get("hole_id") or "")
            current = entities.get(entity_id)
            point = points.get(point_id)
            if current is None or point is None or not hole_id:
                raise EditServiceError("Cannot redo malformed cut_hole operation")
            try:
                hole = EditHoleCut.from_payload(
                    hole_id,
                    {
                        "point_id": point.id,
                        "position_mm": point.position_mm,
                        "axis": operation.get("axis", (0.0, 0.0, 1.0)),
                        "preset": operation.get("preset") or "m4_clearance",
                        "diameter_mm": operation.get("diameter_mm", 4.5),
                        "through": operation.get("through", True),
                    },
                )
                entities[entity_id] = EditEntity.from_payload(
                    entity_id,
                    {
                        **current.to_payload(),
                        "holes": [existing.to_payload() for existing in (*current.holes, hole)],
                    },
                )
            except ValueError as exc:
                raise EditServiceError(str(exc)) from exc
        elif operation_type in {"fuse", "cut"}:
            entity_id = str(operation.get("target_entity_id") or "")
            tool_entity_id = str(operation.get("tool_entity_id") or "")
            boolean_id = str(operation.get("boolean_id") or "")
            current = entities.get(entity_id)
            current_tool = entities.get(tool_entity_id)
            if current is None or current_tool is None or not boolean_id:
                raise EditServiceError(f"Cannot redo malformed {operation_type} operation")
            try:
                boolean = EditBooleanOperation.from_payload(
                    boolean_id,
                    {
                        "type": operation_type,
                        "tool_entity_id": tool_entity_id,
                        "keep_tool": operation.get("keep_tool", True),
                    },
                )
                entities[entity_id] = EditEntity.from_payload(
                    entity_id,
                    {
                        **current.to_payload(),
                        "booleans": [existing.to_payload() for existing in (*current.booleans, boolean)],
                    },
                )
                entities[tool_entity_id] = EditEntity.from_payload(
                    tool_entity_id,
                    {
                        **current_tool.to_payload(),
                        "role": str(operation.get("tool_role") or "construction"),
                    },
                )
            except ValueError as exc:
                raise EditServiceError(str(exc)) from exc
        elif operation_type == "split":
            source_id = str(operation.get("target_entity_id") or "")
            result_ids = operation.get("result_entity_ids")
            current = entities.get(source_id)
            if current is None or not isinstance(result_ids, dict):
                raise EditServiceError("Cannot redo malformed split operation")
            try:
                current_bounds = bounding_box_payload(current, document=document)
                plane_origin = _vector3_payload(operation.get("plane_origin_mm"), field_name="plane_origin_mm")
                plane_normal = _normalized_vector3_payload(operation.get("plane_normal"), field_name="plane_normal")
                source = EditEntity.from_payload(source_id, {**current.to_payload(), "role": "construction"})
                top = EditEntity.from_payload(
                    str(result_ids.get("top") or f"{source_id}_split_top"),
                    {
                        "kind": "derived_split",
                        "name": str(result_ids.get("top") or f"{source_id}_split_top"),
                        "source_entity_id": source_id,
                        "split_plane": {
                            "origin_mm": plane_origin,
                            "normal": plane_normal,
                        },
                        "split_keep": "top",
                        "size_mm": current_bounds["size_mm"],
                        "role": current.role,
                    },
                )
                bottom = EditEntity.from_payload(
                    str(result_ids.get("bottom") or f"{source_id}_split_bottom"),
                    {
                        "kind": "derived_split",
                        "name": str(result_ids.get("bottom") or f"{source_id}_split_bottom"),
                        "source_entity_id": source_id,
                        "split_plane": {
                            "origin_mm": plane_origin,
                            "normal": plane_normal,
                        },
                        "split_keep": "bottom",
                        "size_mm": current_bounds["size_mm"],
                        "role": current.role,
                    },
                )
            except ValueError as exc:
                raise EditServiceError(str(exc)) from exc
            except EditKernelError as exc:
                raise EditServiceUnavailableError(str(exc)) from exc
            entities[source.id] = source
            entities[top.id] = top
            entities[bottom.id] = bottom
        else:
            raise EditServiceError(f"Cannot redo unsupported edit operation type: {operation_type or '<missing>'}")

        return EditDocument(
            schema_version=document.schema_version,
            document_id=document.document_id,
            units=document.units,
            revision=document.revision + 1,
            entities=entities,
            points=points,
            operations=[*document.operations, operation],
        )

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
        except ValueError as exc:
            raise EditServiceError(str(exc)) from exc

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
        try:
            bounds = bounding_box_payload(updated, document=next_document)
        except EditKernelError as exc:
            raise EditServiceUnavailableError(str(exc)) from exc
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

    def _operation_result(self, result: dict[str, Any]) -> dict[str, Any]:
        self._redo_operations.clear()
        return result

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
    def _next_hole_id(document: EditDocument) -> str:
        return _next_numbered_id(
            (hole.id for entity in document.entities.values() for hole in entity.holes),
            "hole",
        )

    @staticmethod
    def _next_boolean_id(document: EditDocument) -> str:
        return _next_numbered_id(
            (operation.id for entity in document.entities.values() for operation in entity.booleans),
            "boolean",
        )

    @staticmethod
    def _ensure_operation_id_available(document: EditDocument, operation_id: str) -> None:
        if any(operation.get("id") == operation_id for operation in document.operations):
            raise EditServiceError(f"Edit operation already exists: {operation_id}")

    @staticmethod
    def _ensure_entity_can_be_deleted(document: EditDocument, entity_id: str) -> None:
        referencing_entities = sorted(
            other_entity.id
            for other_entity in document.entities.values()
            if other_entity.id != entity_id
            and (
                any(operation.tool_entity_id == entity_id for operation in other_entity.booleans)
                or other_entity.source_entity_id == entity_id
            )
        )
        if referencing_entities:
            refs = ", ".join(referencing_entities)
            raise EditServiceError(f"Cannot delete edit entity {entity_id}: referenced by {refs}")


def _next_numbered_id(existing: Any, prefix: str) -> str:
    taken = {str(value) for value in existing}
    index = 1
    while True:
        candidate = f"{prefix}_{index:03d}"
        if candidate not in taken:
            return candidate
        index += 1


def _normalized_cardinal_axis(value: Any) -> Vector3:
    normalized = _normalized_vector3_payload(value, field_name="axis")
    non_zero = [index for index, item in enumerate(normalized) if abs(item) > 1e-6]
    if len(non_zero) != 1:
        raise ValueError("`axis` must be one of +/-X, +/-Y, +/-Z for V1 through-hole cuts")
    index = non_zero[0]
    sign = 1.0 if normalized[index] > 0 else -1.0
    result = [0.0, 0.0, 0.0]
    result[index] = sign
    return (result[0], result[1], result[2])


def _vector3_payload(value: Any, *, field_name: str) -> Vector3:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"`{field_name}` must be a three-number array")
    vector = tuple(float(item) for item in value)
    return (vector[0], vector[1], vector[2])


def _normalized_vector3_payload(value: Any, *, field_name: str) -> Vector3:
    vector = _vector3_payload(value, field_name=field_name)
    length = sum(item * item for item in vector) ** 0.5
    if length == 0:
        raise ValueError(f"`{field_name}` must not be the zero vector")
    return (vector[0] / length, vector[1] / length, vector[2] / length)


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
