# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals

try:
    unicode
except NameError:
    unicode = str

import random
import re

from pyrevit import DB, forms, script
import System
from System.Collections.Generic import List


PALETTE_1 = [
    (228, 26, 28), (55, 126, 184), (77, 175, 74), (152, 78, 163),
    (255, 127, 0), (255, 255, 51), (166, 86, 40), (247, 129, 191),
    (153, 153, 153), (102, 194, 165), (252, 141, 98), (141, 160, 203),
    (231, 138, 195), (166, 216, 84), (255, 217, 47), (229, 196, 148),
]

PALETTE_2 = [
    (31, 119, 180), (255, 127, 14), (44, 160, 44), (214, 39, 40),
    (148, 103, 189), (140, 86, 75), (227, 119, 194), (127, 127, 127),
    (188, 189, 34), (23, 190, 207), (57, 59, 121), (82, 84, 163),
    (107, 110, 207), (156, 158, 222), (99, 121, 57), (140, 162, 82),
]


def stop():
    script.exit()


def alert(message, title=u"Company Tools", warn_icon=False):
    forms.alert(message, title=title, warn_icon=warn_icon)


def choose_one(options, title, button_name=u"Chọn"):
    if not options:
        return None
    return forms.SelectFromList.show(
        sorted(options),
        title=title,
        multiselect=False,
        button_name=button_name,
        width=620,
        height=650,
    )


def choose_many(options, title, button_name=u"Chọn", checked_only=False):
    if not options:
        return []
    result = forms.SelectFromList.show(
        sorted(options),
        title=title,
        multiselect=True,
        button_name=button_name,
        width=720,
        height=720,
    )
    return result or []


def eid_value(element_id):
    if element_id is None:
        return -1
    try:
        return int(element_id.Value)
    except Exception:
        try:
            return int(element_id.IntegerValue)
        except Exception:
            return -1


def to_eid_list(ids):
    result = List[DB.ElementId]()
    for element_id in ids:
        result.Add(element_id)
    return result


def unique_elements(elements):
    found = {}
    for element in elements:
        if element is not None:
            found[eid_value(element.Id)] = element
    return list(found.values())


def element_type(doc, element):
    try:
        type_id = element.GetTypeId()
        if eid_value(type_id) < 0:
            return None
        return doc.GetElement(type_id)
    except Exception:
        return None


def element_name(element, fallback=u"<Không có tên>"):
    """Read Element.Name reliably on IronPython/pythonnet and Revit 2025."""
    if element is None:
        return fallback
    try:
        value = element.Name
        if value:
            return unicode(value)
    except Exception:
        pass
    try:
        value = DB.Element.Name.GetValue(element)
        if value:
            return unicode(value)
    except Exception:
        pass
    for bip_name in (
        'SYMBOL_NAME_PARAM', 'ALL_MODEL_TYPE_NAME', 'ELEM_FAMILY_AND_TYPE_PARAM',
    ):
        try:
            bip = getattr(DB.BuiltInParameter, bip_name)
            param = element.get_Parameter(bip)
            if param is not None and param.HasValue:
                value = param.AsString() or param.AsValueString()
                if value:
                    return unicode(value)
        except Exception:
            pass
    return fallback


def category_name(element):
    try:
        return unicode(element.Category.Name)
    except Exception:
        return u"<Không có Category>"


def type_family_name(doc, element):
    etype = element_type(doc, element)
    if etype is None:
        return u"<Không có Family>"
    try:
        value = etype.FamilyName
        if value:
            return unicode(value)
    except Exception:
        pass
    try:
        family = etype.Family
        if family is not None:
            value = element_name(family, None)
            if value:
                return value
    except Exception:
        pass
    for bip_name in ('SYMBOL_FAMILY_NAME_PARAM', 'ALL_MODEL_FAMILY_NAME'):
        try:
            bip = getattr(DB.BuiltInParameter, bip_name)
            param = etype.get_Parameter(bip)
            if param is not None and param.HasValue:
                value = param.AsString() or param.AsValueString()
                if value:
                    return unicode(value)
        except Exception:
            pass
    return element_name(etype, u"<Không có Family>")


def type_name(doc, element):
    etype = element_type(doc, element)
    if etype is None:
        return element_name(element, u"<Không có Type>")
    return element_name(etype, u"<Không có Type>")


def collect_scope_elements(doc, uidoc, scope, include_types=False):
    if scope == u"Đối tượng đang chọn":
        return unique_elements([doc.GetElement(x) for x in uidoc.Selection.GetElementIds()])

    if scope == u"Toàn bộ dự án":
        collector = DB.FilteredElementCollector(doc)
    else:
        collector = DB.FilteredElementCollector(doc, doc.ActiveView.Id)

    if not include_types:
        collector = collector.WhereElementIsNotElementType()
    return list(collector)


def get_parameter(element, parameter_id):
    if element is None:
        return None
    try:
        return element.get_Parameter(parameter_id)
    except Exception:
        try:
            for parameter in element.Parameters:
                if eid_value(parameter.Id) == eid_value(parameter_id):
                    return parameter
        except Exception:
            pass
    return None


def get_effective_parameter(doc, element, parameter_id, use_type):
    target = element_type(doc, element) if use_type else element
    return get_parameter(target, parameter_id)


def parameter_raw_value(parameter):
    if parameter is None or not parameter.HasValue:
        return None
    stype = parameter.StorageType
    if stype == DB.StorageType.String:
        return parameter.AsString() or u""
    if stype == DB.StorageType.Integer:
        return int(parameter.AsInteger())
    if stype == DB.StorageType.Double:
        return float(parameter.AsDouble())
    if stype == DB.StorageType.ElementId:
        return parameter.AsElementId()
    return None


def raw_value_key(raw):
    if isinstance(raw, DB.ElementId):
        return (u"eid", eid_value(raw))
    if isinstance(raw, float):
        return (u"double", round(raw, 10))
    return (type(raw).__name__, raw)


def parameter_display_value(doc, parameter):
    if parameter is None or not parameter.HasValue:
        return u"<Không có giá trị>"
    try:
        text = parameter.AsValueString()
        if text:
            return text
    except Exception:
        pass

    stype = parameter.StorageType
    try:
        if stype == DB.StorageType.String:
            return parameter.AsString() or u"<Trống>"
        if stype == DB.StorageType.Integer:
            return unicode(parameter.AsInteger())
        if stype == DB.StorageType.Double:
            return u"{0:.6g}".format(parameter.AsDouble())
        if stype == DB.StorageType.ElementId:
            ref_id = parameter.AsElementId()
            ref_elem = doc.GetElement(ref_id)
            if ref_elem is not None:
                return element_name(ref_elem, unicode(eid_value(ref_id)))
            return unicode(eid_value(ref_id))
    except Exception:
        pass
    return u"<Không đọc được>"


def values_equal(left, right, tolerance=1e-9):
    if left is None or right is None:
        return left is right
    if isinstance(left, DB.ElementId) and isinstance(right, DB.ElementId):
        return eid_value(left) == eid_value(right)
    if isinstance(left, float) or isinstance(right, float):
        try:
            return abs(float(left) - float(right)) <= tolerance
        except Exception:
            return False
    return left == right


def create_equals_rule(parameter_id, storage_type, raw_value):
    if raw_value is None:
        try:
            return DB.ParameterFilterRuleFactory.CreateHasNoValueParameterRule(parameter_id)
        except Exception:
            raise ValueError(u"Revit không hỗ trợ tạo filter cho giá trị trống của tham số này")
    if storage_type == DB.StorageType.String:
        return DB.ParameterFilterRuleFactory.CreateEqualsRule(parameter_id, System.String(raw_value or u""))
    if storage_type == DB.StorageType.Integer:
        return DB.ParameterFilterRuleFactory.CreateEqualsRule(parameter_id, System.Int32(int(raw_value)))
    if storage_type == DB.StorageType.Double:
        tolerance = max(abs(float(raw_value)) * 1e-9, 1e-9)
        return DB.ParameterFilterRuleFactory.CreateEqualsRule(parameter_id, System.Double(float(raw_value)), System.Double(tolerance))
    if storage_type == DB.StorageType.ElementId:
        return DB.ParameterFilterRuleFactory.CreateEqualsRule(parameter_id, raw_value)
    raise ValueError(u"StorageType không được hỗ trợ")


def solid_fill_pattern_id(doc):
    for fpe in DB.FilteredElementCollector(doc).OfClass(DB.FillPatternElement):
        try:
            if fpe.GetFillPattern().IsSolidFill:
                return fpe.Id
        except Exception:
            pass
    return DB.ElementId.InvalidElementId


def revit_color(rgb):
    return DB.Color(System.Byte(int(rgb[0])), System.Byte(int(rgb[1])), System.Byte(int(rgb[2])))


def pick_single_rgb(default=(255, 0, 0)):
    try:
        import clr
        clr.AddReference("System.Windows.Forms")
        from System.Windows.Forms import ColorDialog, DialogResult
        dialog = ColorDialog()
        dialog.FullOpen = True
        if dialog.ShowDialog() == DialogResult.OK:
            return (dialog.Color.R, dialog.Color.G, dialog.Color.B)
    except Exception:
        pass
    return default


def palette_colors(mode, count):
    if mode == u"Một màu tự chọn":
        rgb = pick_single_rgb()
        return [rgb for _ in range(count)]
    if mode == u"Ngẫu nhiên":
        rng = random.Random(2025 + count)
        return [(rng.randint(20, 235), rng.randint(20, 235), rng.randint(20, 235)) for _ in range(count)]
    palette = PALETTE_2 if mode == u"Bảng màu 2" else PALETTE_1
    return [palette[index % len(palette)] for index in range(count)]


def make_overrides(doc, rgb, graphics_mode=u"Bề mặt + mặt cắt + đường nét", transparency=0):
    color = revit_color(rgb)
    ogs = DB.OverrideGraphicSettings()
    solid_id = solid_fill_pattern_id(doc)

    use_surface = graphics_mode in (u"Bề mặt + mặt cắt + đường nét", u"Bề mặt + mặt cắt", u"Chỉ bề mặt")
    use_cut = graphics_mode in (u"Bề mặt + mặt cắt + đường nét", u"Bề mặt + mặt cắt")
    use_lines = graphics_mode in (u"Bề mặt + mặt cắt + đường nét", u"Chỉ đường nét")

    if use_surface and eid_value(solid_id) >= 0:
        ogs.SetSurfaceForegroundPatternId(solid_id)
        ogs.SetSurfaceForegroundPatternColor(color)
        ogs.SetSurfaceTransparency(max(0, min(100, int(transparency))))
    if use_cut and eid_value(solid_id) >= 0:
        ogs.SetCutForegroundPatternId(solid_id)
        ogs.SetCutForegroundPatternColor(color)
    if use_lines:
        ogs.SetProjectionLineColor(color)
        ogs.SetCutLineColor(color)
    return ogs


def safe_filter_name(text, max_length=180):
    text = re.sub(r"[\\/:*?\"<>|\r\n\t]+", u"_", text or u"")
    text = re.sub(r"\s+", u" ", text).strip()
    return text[:max_length]


def get_filter_by_name(doc, name):
    for item in DB.FilteredElementCollector(doc).OfClass(DB.ParameterFilterElement):
        if item.Name == name:
            return item
    return None


def apply_filter_to_view(view, filter_id, overrides, visible=True):
    applied = [eid_value(x) for x in view.GetFilters()]
    if eid_value(filter_id) not in applied:
        view.AddFilter(filter_id)
    view.SetFilterOverrides(filter_id, overrides)
    view.SetFilterVisibility(filter_id, bool(visible))
    try:
        view.SetIsFilterEnabled(filter_id, True)
    except Exception:
        pass


def view_display_name(view):
    try:
        prefix = u"[Template] " if view.IsTemplate else u""
        return prefix + view.Name + u"  |  " + unicode(view.ViewType)
    except Exception:
        return unicode(view.Id)


def view_can_receive_filters(view):
    if view is None:
        return False
    try:
        unsupported = (
            u"DrawingSheet", u"Schedule", u"ColumnSchedule", u"Report",
            u"ProjectBrowser", u"SystemBrowser", u"Internal", u"Undefined",
        )
        if unicode(view.ViewType) in unsupported:
            return False
    except Exception:
        pass
    try:
        return bool(view.AreGraphicsOverridesAllowed())
    except Exception:
        return True


def bounding_boxes_intersect(element_a, element_b, view=None, tolerance=1e-9):
    try:
        box_a = element_a.get_BoundingBox(view)
        box_b = element_b.get_BoundingBox(view)
        if box_a is None or box_b is None:
            return False
        return not (
            box_a.Max.X < box_b.Min.X - tolerance or box_a.Min.X > box_b.Max.X + tolerance or
            box_a.Max.Y < box_b.Min.Y - tolerance or box_a.Min.Y > box_b.Max.Y + tolerance or
            box_a.Max.Z < box_b.Min.Z - tolerance or box_a.Min.Z > box_b.Max.Z + tolerance
        )
    except Exception:
        return False
