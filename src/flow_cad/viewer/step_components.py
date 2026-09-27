"""Read STEP occurrence appearances without collapsing them into prototypes."""
from pathlib import Path


def step_components(path: Path):
    from build123d import Compound
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Quantity import Quantity_ColorRGBA
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_Label
    try:
        # OCCT 8 moved sequence bindings out of the old typedef modules.
        from OCP.collections import Sequence_TDF_Label
    except ImportError:
        from OCP.TDF import TDF_LabelSequence as Sequence_TDF_Label
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_ColorSurf, XCAFDoc_ColorGen, XCAFDoc_ColorCurv, XCAFDoc_ColorTool, XCAFDoc_DocumentTool

    document = TDocStd_Document(TCollection_ExtendedString('XCAF'))
    reader = STEPCAFControl_Reader()
    reader.SetColorMode(True)
    reader.SetNameMode(True)
    reader.SetLayerMode(True)
    reader.SetSHUOMode(True)
    if reader.ReadFile(str(path)) != IFSelect_RetDone or not reader.Transfer(document):
        raise ValueError(f'Cannot read STEP display geometry: {path.name}')
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    colors = XCAFDoc_DocumentTool.ColorTool_s(document.Main())

    def label_color(label):
        value = Quantity_ColorRGBA()
        for kind in (XCAFDoc_ColorSurf, XCAFDoc_ColorGen, XCAFDoc_ColorCurv):
            if XCAFDoc_ColorTool.GetColor_s(label, kind, value):
                rgb = value.GetRGB()
                return rgb.Red(), rgb.Green(), rgb.Blue(), value.Alpha()
        return None

    def shape_color(shape):
        value = Quantity_ColorRGBA()
        for kind in (XCAFDoc_ColorSurf, XCAFDoc_ColorGen, XCAFDoc_ColorCurv):
            if colors.GetInstanceColor(shape, kind, value) or colors.GetColor(shape, kind, value):
                rgb = value.GetRGB()
                return rgb.Red(), rgb.Green(), rgb.Blue(), value.Alpha()
        return None

    def label_name(label):
        value = TDataStd_Name()
        if label.FindAttribute(TDataStd_Name.GetID_s(), value):
            name = value.Get().ToExtString().strip()
            if name and not name.isdigit() and name.lower() not in {'solid', 'compound', 'assembly', 'shell'} and not name.startswith(('Open CASCADE STEP translator', '=>')):
                return name
        return None

    def visit(label, parent_location, key, inherited_color=None, inherited_name=None):
        referred = label
        if shapes.IsReference_s(label):
            referred = TDF_Label()
            shapes.GetReferredShape_s(label, referred)
        instance = shapes.GetShape_s(label)
        prototype = shapes.GetShape_s(referred)
        location = parent_location * instance.Location()
        color = label_color(label) or shape_color(instance) or label_color(referred) or shape_color(prototype) or inherited_color
        name = label_name(label) or label_name(referred) or inherited_name
        children = Sequence_TDF_Label()
        shapes.GetComponents_s(referred, children, False)
        if children.Length():
            for index in range(1, children.Length()+1):
                yield from visit(children.Value(index), location, f'{key}/{index}', color, name)
        elif not prototype.IsNull():
            # A new wrapper prevents parent/sibling deep copies during meshing.
            shape = Compound.cast(prototype.Located(location))
            yield key, name, color, shape

    roots = Sequence_TDF_Label()
    shapes.GetFreeShapes(roots)
    for index in range(1, roots.Length()+1):
        yield from visit(roots.Value(index), TopLoc_Location(), str(index))
