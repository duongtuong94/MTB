# -*- coding: utf-8 -*-
"""Crop a picked screen rectangle in the existing view coordinate system."""
from pyrevit import revit, DB, forms
from Autodesk.Revit.UI.Selection import PickBoxStyle
from Autodesk.Revit.Exceptions import OperationCanceledException


OFFSET = 500.0 / 304.8
PICK_TOLERANCE = 1.0e-7


def crop_from_pick(old_crop, picked):
    # PickBox returns model points. CropBox.Min/Max are LOCAL to its transform.
    # Keep the complete picked XYZ (global Z is screen height in sections).
    inverse = old_crop.Transform.Inverse
    first = inverse.OfPoint(picked.Min)
    second = inverse.OfPoint(picked.Max)
    left, right = min(first.X, second.X), max(first.X, second.X)
    bottom, top = min(first.Y, second.Y), max(first.Y, second.Y)
    if right - left <= PICK_TOLERANCE or top - bottom <= PICK_TOLERANCE:
        raise ValueError(u"Vùng quét quá nhỏ. Hãy quét một hình chữ nhật có chiều rộng và cao.")
    result = DB.BoundingBoxXYZ()
    result.Transform = old_crop.Transform
    # The View.CropBox setter ignores the supplied Transform. The extents must
    # already use the EXISTING crop frame; do not transform them back to model.
    result.Min = DB.XYZ(left - OFFSET, bottom - OFFSET, old_crop.Min.Z)
    result.Max = DB.XYZ(right + OFFSET, top + OFFSET, old_crop.Max.Z)
    return result


def apply_crop(doc, view, crop, manager):
    transaction = DB.Transaction(doc, "Quick Crop")
    try:
        if transaction.Start() != DB.TransactionStatus.Started:
            raise RuntimeError(u"Không bắt đầu được transaction Quick Crop.")
        view.CropBoxActive = True
        # Assigning CropBox alone has no effect on a sketched crop boundary.
        if manager.ShapeSet:
            manager.RemoveCropRegionShape()
        view.CropBox = crop
        view.CropBoxVisible = True
        if transaction.Commit() != DB.TransactionStatus.Committed:
            raise RuntimeError(u"Không áp dụng được Crop Box; transaction chưa commit.")
    except Exception:
        if transaction.GetStatus() == DB.TransactionStatus.Started:
            transaction.RollBack()
        raise
    finally:
        transaction.Dispose()


def run(uidoc):
    doc = uidoc.Document
    view = doc.ActiveView
    if view.IsTemplate or view.ViewType not in (
            DB.ViewType.EngineeringPlan, DB.ViewType.FloorPlan,
            DB.ViewType.CeilingPlan, DB.ViewType.AreaPlan,
            DB.ViewType.Section, DB.ViewType.Elevation):
        forms.alert(u"Quick Crop dùng cho Plan / Section / Elevation hỗ trợ crop.",
                    title="Quick Crop")
        return False
    old_crop = view.CropBox
    if old_crop is None:
        forms.alert(u"View hiện tại không hỗ trợ Crop Box.", title="Quick Crop")
        return False
    scope = view.get_Parameter(DB.BuiltInParameter.VIEWER_VOLUME_OF_INTEREST_CROP)
    if scope is not None and scope.AsElementId() != DB.ElementId.InvalidElementId:
        forms.alert(u"Crop đang do Scope Box điều khiển. Đặt Scope Box = None trước khi dùng Quick Crop.",
                    title="Quick Crop")
        return False
    manager = view.GetCropRegionShapeManager()
    try:
        if manager.Split:
            forms.alert(u"Quick Crop chưa hỗ trợ view có Split Crop. Gộp các vùng crop trước khi quét.",
                        title="Quick Crop")
            return False
        picked = uidoc.Selection.PickBox(PickBoxStyle.Directional, u"Quét vùng Crop View")
        crop = crop_from_pick(old_crop, picked)
        apply_crop(doc, view, crop, manager)
    finally:
        manager.Dispose()
    # Zoom is optional presentation work, after a successful commit only.
    try:
        for ui_view in uidoc.GetOpenUIViews():
            if ui_view.ViewId == view.Id:
                ui_view.ZoomToFit()
                break
    except Exception as error:
        print("Quick Crop applied; Zoom to Fit failed: {0}".format(error))
    return True


def main():
    try:
        return run(revit.uidoc)
    except OperationCanceledException:
        return False
    except Exception as error:
        forms.alert(u"{0}".format(error), title="Quick Crop Error")
        return False


if __name__ == '__main__':
    main()
