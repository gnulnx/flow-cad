"""Isolated STEP -> GLB display conversion, preserving colored components.

GLB uses metres/Y-up; CAD consumers restore millimetres/Z-up. Each STEP leaf
is a selectable component. No product generators are imported.
"""
from __future__ import annotations

import json
import struct
import sys
from array import array
from pathlib import Path


def export_scene(step_path: Path, output: Path) -> dict:
    from .step_components import step_components
    return export_components(step_components(step_path), output)


def export_shape_scene(shape, output: Path) -> dict:
    """Mesh the generated shape directly, using STEP's occurrence transform convention."""
    from build123d import Compound, Location
    def visit(item, parent_location, key, inherited_color=None):
        location = parent_location * item.location
        color = item.color if item.color is not None else inherited_color
        if item.children:
            for index, child in enumerate(item.children, 1):
                yield from visit(child, location, f'{key}/{index}', color)
        else:
            yield key, item.label, color, Compound.cast(item.wrapped.Located(location.wrapped))
    return export_components(visit(shape, Location(), '1'), output)


def export_components(components, output: Path) -> dict:
    binary = bytearray()
    views, accessors, meshes, materials, nodes = [], [], [], [], []
    palette = {}

    def buffer(values, code, component_type, kind, count, **extra):
        data = array(code, values)
        if sys.byteorder != "little":
            data.byteswap()
        offset = len(binary)
        binary.extend(data.tobytes())
        binary.extend(b"\0" * (-len(binary) % 4))
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data) * data.itemsize})
        accessors.append({"bufferView": len(views)-1, "componentType": component_type,
                          "count": count, "type": kind, **extra})
        return len(accessors)-1

    def add_component(path, name, color, shape):
        vertices, triangles = shape.tessellate(0.2, angular_tolerance=0.2)
        if not triangles:
            return
        points = [(v.X * .001, v.Z * .001, -v.Y * .001) for v in vertices]
        rgba = tuple(color) if color is not None else (.30, .40, .48, 1.)
        if rgba not in palette:
            palette[rgba] = len(materials)
            materials.append({"pbrMetallicRoughness": {"baseColorFactor": list(rgba),
                              "metallicFactor": .08, "roughnessFactor": .58},
                              "doubleSided": True,
                              **({"alphaMode": "BLEND"} if rgba[3] < 1 else {})})
        pos = buffer((v for p in points for v in p), "f", 5126, "VEC3", len(points),
                     min=[min(p[i] for p in points) for i in range(3)],
                     max=[max(p[i] for p in points) for i in range(3)])
        indices = buffer((v for t in triangles for v in t), "I", 5125, "SCALAR", len(triangles)*3)
        name = name or f"Component {len(nodes)+1}"
        meshes.append({"name": name, "primitives": [{"attributes": {"POSITION": pos},
                       "indices": indices, "material": palette[rgba], "mode": 4}]})
        nodes.append({"name": name, "mesh": len(meshes)-1,
                      "extras": {"componentId": path, "label": name}})

    for component in components:
        add_component(*component)
    if not nodes:
        raise ValueError("STEP contains no tessellatable components")
    document = {"asset": {"version": "2.0", "generator": "Flow CAD STEP display v2"},
                "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}],
                "nodes": nodes, "meshes": meshes, "materials": materials,
                "buffers": [{"byteLength": len(binary)}], "bufferViews": views, "accessors": accessors}
    encoded = json.dumps(document, separators=(",", ":")).encode()
    encoded += b" " * (-len(encoded) % 4)
    output.write_bytes(struct.pack("<III", 0x46546C67, 2, 28+len(encoded)+len(binary))
                       + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
                       + struct.pack("<II", len(binary), 0x004E4942) + binary)
    return {"component_count": len(nodes), "color_count": len(materials)}


if __name__ == "__main__":
    print(json.dumps(export_scene(Path(sys.argv[1]), Path(sys.argv[2]))))
