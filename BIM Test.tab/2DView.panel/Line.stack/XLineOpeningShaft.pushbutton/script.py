# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import (
    BuiltInCategory, XYZ, Line, ViewType, Transaction, SubTransaction, TransactionStatus,
)
from Autodesk.Revit.UI import TaskDialog
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
import Autodesk.Revit.Exceptions as Exceptions
from opening_marks import opening_marks

doc = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument
view = doc.ActiveView


def element_id_value(element_id):
    try:
        return int(element_id.Value)
    except AttributeError:
        return int(element_id.IntegerValue)


class OpeningSelectionFilter(ISelectionFilter):
    def AllowElement(self, element):
        if element is None or element.Category is None:
            return False
        return element_id_value(element.Category.Id) in (
            int(BuiltInCategory.OST_ShaftOpening), int(BuiltInCategory.OST_FloorOpening))

    def AllowReference(self, ref, point):
        return False


def view_frame():
    origin = view.Origin
    if view.ViewType in (ViewType.FloorPlan, ViewType.EngineeringPlan, ViewType.CeilingPlan):
        if view.GenLevel is not None:
            origin = XYZ(origin.X, origin.Y, view.GenLevel.Elevation)
    try:
        if view.SketchPlane is not None:
            origin = view.SketchPlane.GetPlane().Origin
    except Exception:
        pass
    return origin, view.RightDirection.Normalize(), view.UpDirection.Normalize()


def project(point, frame):
    delta = point.Subtract(frame[0])
    return (delta.DotProduct(frame[1]), delta.DotProduct(frame[2]))


def unproject(point, frame):
    return frame[0].Add(frame[1].Multiply(point[0])).Add(frame[2].Multiply(point[1]))


def boundary_edges(opening, frame):
    # BoundaryCurves is not defined for rectangular-boundary Openings.
    if opening.IsRectBoundary:
        rectangle = list(opening.BoundaryRect)
        if len(rectangle) != 2:
            raise ValueError('Invalid BoundaryRect')
        low, high = rectangle
        vertices = [XYZ(low.X, low.Y, low.Z), XYZ(high.X, low.Y, low.Z),
                    XYZ(high.X, high.Y, high.Z), XYZ(low.X, high.Y, high.Z)]
        points = [project(p, frame) for p in vertices]
        return [{'points': [points[i], points[(i + 1) % 4]], 'linear': True}
                for i in range(4)]
    curves = opening.BoundaryCurves
    if curves is None or curves.Size == 0:
        raise ValueError('No boundary curves')
    result = []
    for curve in curves:
        points = [project(p, frame) for p in curve.Tessellate()]
        closed = bool(curve.IsCyclic and not curve.IsBound)
        result.append({'points': points, 'linear': isinstance(curve, Line), 'closed': closed})
    return result


def draw_x(mark, frame):
    # Both diagonals belong to one subtransaction: failure leaves no half-X.
    sub = SubTransaction(doc)
    sub.Start()
    try:
        for a, b in mark:
            doc.Create.NewDetailCurve(view, Line.CreateBound(unproject(a, frame), unproject(b, frame)))
        if sub.Commit() != TransactionStatus.Committed:
            raise ValueError('Revit rejected detail curves')
    except Exception:
        if sub.GetStatus() == TransactionStatus.Started:
            sub.RollBack()
        raise
    finally:
        sub.Dispose()


ERROR_LABELS = {
    'invalid_edge': u'Cạnh không có hình học hợp lệ',
    'open_or_branched': u'Đường bao hở, trùng cạnh hoặc nhiều nhánh',
    'degenerate': u'Đường bao suy biến trên mặt phẳng view',
    'self_intersection_or_zero_area': u'Đường bao tự giao hoặc diện tích bằng 0',
    'touching_or_crossing_loops': u'Các đường bao chạm nhau hoặc giao nhau',
    'ambiguous_nesting': u'Không xác định được quan hệ vùng đặc/lỗ mở',
    'opening_contains_solid_island': u'Lỗ có vùng đặc bên trong: bỏ qua để không vẽ X xuyên vùng đặc',
    'too_small': u'Lỗ quá nhỏ để tạo đủ hai đường chéo',
}


def auto_draw_all_openings():
    valid_views = (ViewType.FloorPlan, ViewType.EngineeringPlan, ViewType.CeilingPlan,
                   ViewType.Detail, ViewType.Section, ViewType.DraftingView)
    if view.ViewType not in valid_views:
        TaskDialog.Show(u'BIM Test | X Opening', u'Vui lòng chạy tool trong mặt bằng hoặc chi tiết.')
        return
    selection_filter = OpeningSelectionFilter()
    openings = [doc.GetElement(eid) for eid in uidoc.Selection.GetElementIds()]
    openings = [op for op in openings if selection_filter.AllowElement(op)]
    if not openings:
        try:
            refs = uidoc.Selection.PickObjects(
                ObjectType.Element, selection_filter,
                u'Chọn Opening (Shaft/Floor), sau đó bấm FINISH. Mỗi vòng kín sẽ được xử lý riêng.')
            openings = [doc.GetElement(ref) for ref in refs]
        except Exceptions.OperationCanceledException:
            return
    unique = {}
    for op in openings:
        unique[element_id_value(op.Id)] = op
    openings = list(unique.values())
    if not openings:
        return

    frame = view_frame()
    minimum_length = doc.Application.ShortCurveTolerance
    prepared, warnings = [], []
    skipped = 0
    islands = 0
    for op in openings:
        op_id = element_id_value(op.Id)
        try:
            result = opening_marks(boundary_edges(op, frame),
                                   tolerance=max(1e-6, minimum_length * 0.001),
                                   minimum_length=minimum_length)
            prepared.extend((op_id, mark) for mark in result['marks'])
            islands += result['islands']
            skipped += len(result['errors'])
            warnings.extend(u'Opening {0}: {1}'.format(op_id, ERROR_LABELS[reason])
                            for reason in result['errors'])
        except Exception as error:
            skipped += 1
            warnings.append(u'Opening {0}: không đọc được đường bao ({1})'.format(op_id, error))

    drawn_count = 0
    if prepared:
        transaction = Transaction(doc, 'X lines for Opening contours')
        transaction.Start()
        try:
            for op_id, mark in prepared:
                try:
                    draw_x(mark, frame)
                    drawn_count += 1
                except Exception as error:
                    skipped += 1
                    warnings.append(u'Opening {0}: không tạo được X ({1})'.format(op_id, error))
            if transaction.Commit() != TransactionStatus.Committed:
                raise ValueError('Revit rejected transaction')
        except Exception as error:
            if transaction.GetStatus() == TransactionStatus.Started:
                transaction.RollBack()
            TaskDialog.Show(u'BIM Test | X Opening',
                            u'Không lưu được các đường X.\n\n{0}'.format(error))
            return
        finally:
            transaction.Dispose()

    message = u'Đã xử lý {0} Opening, vẽ X cho {1} lỗ.\nBỏ qua {2} nhóm/cạnh đường bao lỗi.'.format(
        len(openings), drawn_count, skipped)
    if islands:
        message += u'\nKhông đánh X cho {0} vùng đặc lồng bên trong.'.format(islands)
    if warnings:
        message += u'\n\n' + u'\n'.join(warnings[:10])
        if len(warnings) > 10:
            message += u'\n... và {0} cảnh báo khác.'.format(len(warnings) - 10)
    TaskDialog.Show(u'BIM Test | X Opening', message)


if __name__ == '__main__':
    auto_draw_all_openings()
