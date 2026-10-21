# -*- coding: utf-8 -*-
"""
Toggle Grid and Level Bubbles - pyRevit / Revit 2025

Workflow:
1. Run command.
2. Drag a rectangle to select Grids/Levels.
3. Release mouse - no Finish button.
4. Click one point near the side/end you want to toggle.
5. For EACH selected item independently:
   - Compare click point to End0 and End1 in the active view.
   - Toggle the bubble at the closer end only.
"""

from pyrevit import revit, DB, forms
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectSnapTypes
from Autodesk.Revit.Exceptions import OperationCanceledException
from System.Collections.Generic import List

uidoc = revit.uidoc
doc = revit.doc
view = doc.ActiveView


class DatumSelectionFilter(ISelectionFilter):
    def AllowElement(self, element):
        # Cho phép lọc cả đối tượng Grid và Level
        return isinstance(element, (DB.Grid, DB.Level))

    def AllowReference(self, reference, point):
        return False


def pick_datums_by_rectangle():
    with forms.WarningBar(title="Quét chuột để chọn Grid/Level"):
        return list(
            uidoc.Selection.PickElementsByRectangle(
                DatumSelectionFilter(),
                "Quét chuột để chọn Grid/Level"
            )
        )


def ensure_work_plane(active_view):
    try:
        if active_view.SketchPlane:
            return True
    except Exception:
        pass

    tx = DB.Transaction(doc, "Datum Toggle - Set Work Plane")
    try:
        tx.Start()
        plane = DB.Plane.CreateByNormalAndOrigin(
            active_view.ViewDirection,
            active_view.Origin
        )
        active_view.SketchPlane = DB.SketchPlane.Create(doc, plane)
        tx.Commit()
        return True
    except Exception:
        try:
            tx.RollBack()
        except Exception:
            pass
        return False


def get_view_curve(datum, active_view):
    try:
        curves = datum.GetCurvesInView(
            DB.DatumExtentType.ViewSpecific,
            active_view
        )
        if curves and curves.Count > 0:
            return curves[0]
    except Exception:
        pass

    try:
        curves = datum.GetCurvesInView(
            DB.DatumExtentType.Model,
            active_view
        )
        if curves and curves.Count > 0:
            return curves[0]
    except Exception:
        pass

    return None


def get_closest_datum_end(datum, click_point, active_view):
    curve = get_view_curve(datum, active_view)
    if curve is None:
        return None

    p0 = curve.GetEndPoint(0)
    p1 = curve.GetEndPoint(1)

    if click_point.DistanceTo(p0) <= click_point.DistanceTo(p1):
        return DB.DatumEnds.End0
    return DB.DatumEnds.End1


def toggle_datum_bubble(datum, click_point, active_view):
    end = get_closest_datum_end(datum, click_point, active_view)
    if end is None:
        return False

    try:
        if datum.IsBubbleVisibleInView(end, active_view):
            datum.HideBubbleInView(end, active_view)
        else:
            datum.ShowBubbleInView(end, active_view)
        return True
    except Exception:
        return False


# MAIN
try:
    datums = pick_datums_by_rectangle()
except OperationCanceledException:
    datums = []
except Exception:
    datums = []

if not datums:
    forms.alert("Không có Grid/Level nào được chọn.", title="Toggle Datum Bubbles")
    raise SystemExit

if not ensure_work_plane(view):
    forms.alert(
        "Không thể thiết lập Work Plane cho View hiện tại.",
        title="Toggle Datum Bubbles"
    )
    raise SystemExit

try:
    with forms.WarningBar(title="Click 1 điểm gần phía đầu Grid/Level cần bật/tắt"):
        click_pt = uidoc.Selection.PickPoint(
            ObjectSnapTypes.None,
            "Click 1 điểm gần phía đầu Grid/Level cần bật/tắt"
        )
except OperationCanceledException:
    raise SystemExit
except Exception:
    raise SystemExit

tx = DB.Transaction(doc, "Toggle Datum Bubbles")
changed = 0
skipped = 0

try:
    tx.Start()

    for datum in datums:
        if toggle_datum_bubble(datum, click_pt, view):
            changed += 1
        else:
            skipped += 1

    tx.Commit()

except Exception as ex:
    try:
        tx.RollBack()
    except Exception:
        pass

    forms.alert(
        "Không thể Toggle Grid/Level.\n\n{}".format(ex),
        title="Toggle Datum Bubbles"
    )
    raise SystemExit

try:
    uidoc.Selection.SetElementIds(List[DB.ElementId]())
except Exception:
    pass
