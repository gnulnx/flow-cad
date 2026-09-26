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
    from build123d import Location, Compound, import_step

    root = import_step(step_path)
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

    def visit(node, parent_location, path, inherited_color=None):
        color = node.color if node.color is not None else inherited_color
        location = parent_location * (node.location or Location())
        if node.children:
            for index, child in enumerate(node.children):
                visit(child, location, f"{path}/{index}", color)
            return
        # Re-wrap this leaf only: copying children can copy the entire parent
        # assembly and consume many GB on large models.
        shape = Compound.cast(node.wrapped)
        shape.location = location
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
        name = node.label or f"Component {len(nodes)+1}"
        meshes.append({"name": name, "primitives": [{"attributes": {"POSITION": pos},
                       "indices": indices, "material": palette[rgba], "mode": 4}]})
        nodes.append({"name": name, "mesh": len(meshes)-1,
                      "extras": {"componentId": path, "label": name}})

    visit(root, Location(), "0")
    if not nodes:
        raise ValueError("STEP contains no tessellatable components")
    document = {"asset": {"version": "2.0", "generator": "Flow CAD STEP display v1"},
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
