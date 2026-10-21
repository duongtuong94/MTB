# -*- coding: utf-8 -*-

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI.Selection import PickBoxStyle
from Autodesk.Revit.Exceptions import OperationCanceledException

from pyrevit import revit, forms


uidoc = revit.uidoc
doc = revit.doc
view = doc.ActiveView


# 500mm khoảng thở đầu trục
OFFSET = 500 / 304.8


def supported_view(v):

    return v.ViewType in [
        ViewType.EngineeringPlan,
        ViewType.FloorPlan,
        ViewType.CeilingPlan,
        ViewType.Section,
        ViewType.Elevation,
        ViewType.DraftingView
    ]


try:

    if not supported_view(view):

        forms.alert(
            "View không hỗ trợ.\n"
            "Dùng Plan / Section / Elevation / Drafting View",
            "Quick Crop"
        )

        raise Exception()



    old_crop = view.CropBox



    # Chọn vùng

    box = uidoc.Selection.PickBox(
        PickBoxStyle.Directional,
        "Quét vùng Crop View"
    )


    p1 = box.Min
    p2 = box.Max



    tf = old_crop.Transform


    p1 = tf.OfPoint(
        XYZ(
            p1.X,
            p1.Y,
            old_crop.Min.Z
        )
    )


    p2 = tf.OfPoint(
        XYZ(
            p2.X,
            p2.Y,
            old_crop.Max.Z
        )
    )



    min_x = min(p1.X, p2.X) - OFFSET
    min_y = min(p1.Y, p2.Y) - OFFSET

    max_x = max(p1.X, p2.X) + OFFSET
    max_y = max(p1.Y, p2.Y) + OFFSET



    new_crop = BoundingBoxXYZ()

    new_crop.Transform = tf


    new_crop.Min = XYZ(
        min_x,
        min_y,
        old_crop.Min.Z
    )


    new_crop.Max = XYZ(
        max_x,
        max_y,
        old_crop.Max.Z
    )



    # Apply Crop

    with revit.Transaction("Quick Crop"):

        if not view.CropBoxActive:
            view.CropBoxActive = True

        view.CropBox = new_crop

        if not view.CropBoxVisible:
            view.CropBoxVisible = True



    # Auto Zoom Fit

    for uiview in uidoc.GetOpenUIViews():

        if uiview.ViewId == view.Id:

            uiview.ZoomToFit()

            break



except OperationCanceledException:

    pass



except Exception as e:

    forms.alert(
        str(e),
        "Quick Crop Error"
    )