# -*- coding: utf-8 -*-
import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Structure import StructuralFramingUtils
from Autodesk.Revit.UI import *
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
import Autodesk.Revit.Exceptions as Exceptions

doc = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument

class BeamSelectionFilter(ISelectionFilter):
    def AllowElement(self, element):
        return element.Category and element.Category.Id.IntegerValue == int(BuiltInCategory.OST_StructuralFraming)
    def AllowReference(self, ref, point):
        return False

def get_2d_intersection(p1, p2, p3, p4):
    x1, y1 = p1.X, p1.Y
    x2, y2 = p2.X, p2.Y
    x3, y3 = p3.X, p3.Y
    x4, y4 = p4.X, p4.Y

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-6:
        return None 

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    
    if 0.001 < t < 0.999: 
        inter_x = x1 + t * (x2 - x1)
        inter_y = y1 + t * (y2 - y1)
        inter_z = p1.Z + t * (p2.Z - p1.Z) 
        return XYZ(inter_x, inter_y, inter_z)
    return None

def split_beam_and_force_cutback():
    try:
        main_ref = uidoc.Selection.PickObject(ObjectType.Element, BeamSelectionFilter(), "Bước 1: Chọn DẦM CHÍNH cần split")
        main_beam = doc.GetElement(main_ref)
        
        cutter_refs = uidoc.Selection.PickObjects(ObjectType.Element, BeamSelectionFilter(), "Bước 2: Quét chọn CÁC DẦM GIAO để cắt, sau đó bấm FINISH")
        cutters = [doc.GetElement(r) for r in cutter_refs]
        
    except Exceptions.OperationCanceledException:
        return

    main_curve = main_beam.Location.Curve
    if not isinstance(main_curve, Line):
        TaskDialog.Show("Lỗi", "Tool hiện tại chỉ hỗ trợ dầm thẳng.")
        return
        
    p_start = main_curve.GetEndPoint(0)
    p_end = main_curve.GetEndPoint(1)
    
    intersection_pts = []
    
    for cutter in cutters:
        c_curve = cutter.Location.Curve
        if not isinstance(c_curve, Line): continue
        
        cp_start = c_curve.GetEndPoint(0)
        cp_end = c_curve.GetEndPoint(1)
        
        intersect_pt = get_2d_intersection(p_start, p_end, cp_start, cp_end)
        if intersect_pt:
            intersection_pts.append(intersect_pt)
            
    if not intersection_pts:
        TaskDialog.Show("Thông báo", "Không tìm thấy điểm giao cắt nào nằm trên dầm chính.")
        return
        
    intersection_pts.sort(key=lambda pt: pt.DistanceTo(p_start))
    
    unique_pts = []
    for pt in intersection_pts:
        if not unique_pts or unique_pts[-1].DistanceTo(pt) > 0.01:
            unique_pts.append(pt)
            
    points_sequence = [p_start] + unique_pts + [p_end]
    segments = [main_beam]
    
    # --- GIAI ĐOẠN 1: CẮT DẦM VÀ ÉP CHO PHÉP JOIN ---
    t1 = Transaction(doc, "Split Element")
    t1.Start()
    try:
        for i in range(1, len(points_sequence) - 1):
            cloned_ids = ElementTransformUtils.CopyElement(doc, main_beam.Id, XYZ.Zero)
            segments.append(doc.GetElement(cloned_ids[0]))
            
        for i in range(len(segments)):
            beam = segments[i]
            beam.Location.Curve = Line.CreateBound(points_sequence[i], points_sequence[i+1])
            
            if not StructuralFramingUtils.IsJoinAllowedAtEnd(beam, 0):
                StructuralFramingUtils.AllowJoinAtEnd(beam, 0)
            if not StructuralFramingUtils.IsJoinAllowedAtEnd(beam, 1):
                StructuralFramingUtils.AllowJoinAtEnd(beam, 1)
                
        # CHỐNG VĂNG FILE: Kiểm tra xem người dùng có bấm Cancel ở bảng cảnh báo không
        status1 = t1.Commit()
        if status1 != TransactionStatus.Committed:
            return # Nếu bấm Cancel (RolledBack), thoát tool lập tức một cách êm ái
            
    except Exception as e:
        if t1.HasStarted(): t1.RollBack()
        TaskDialog.Show("Lỗi", "Giai đoạn 1 thất bại: " + str(e))
        return

    # --- GIAI ĐOẠN 2: THIẾT LẬP KHOẢNG HỞ 1'-0" VĨNH VIỄN ---
    t2 = Transaction(doc, "Modify elements attributes")
    t2.Start()
    try:
        for beam in segments:
            param_start_cutback = beam.LookupParameter("Start Join Cutback")
            param_end_cutback = beam.LookupParameter("End Join Cutback")
            
            if param_start_cutback and not param_start_cutback.IsReadOnly:
                param_start_cutback.Set(1.0)
                
            if param_end_cutback and not param_end_cutback.IsReadOnly:
                param_end_cutback.Set(1.0)
                
        status2 = t2.Commit()
        if status2 != TransactionStatus.Committed:
            return
            
    except Exception as e:
        if t2.HasStarted(): t2.RollBack()
        TaskDialog.Show("Lỗi", "Giai đoạn 2 thất bại: " + str(e))

split_beam_and_force_cutback()