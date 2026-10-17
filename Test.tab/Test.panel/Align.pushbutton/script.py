# -*- coding: utf-8 -*-
import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter

uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

# Bộ lọc để pick chọn đường Detail Line
class LineFilter(ISelectionFilter):
    def AllowElement(self, elem):
        return isinstance(elem, CurveElement)
    def AllowReference(self, ref, pos):
        return True

# Hàm tìm hướng của cấu kiện dầm/cột mà Tag đang bám vào
def get_tag_host_direction(tag, doc):
    try:
        refs = tag.GetTaggedReferences()
        for ref in refs:
            # Nếu dầm nằm trong file Revit Link
            if ref.LinkedElementId != ElementId.InvalidElementId:
                link_inst = doc.GetElement(ref.ElementId)
                if isinstance(link_inst, RevitLinkInstance):
                    link_doc = link_inst.GetLinkDocument()
                    host = link_doc.GetElement(ref.LinkedElementId)
                    if host and host.Location and isinstance(host.Location, LocationCurve):
                        curve = host.Location.Curve
                        if isinstance(curve, Line):
                            tf = link_inst.GetTransform()
                            return tf.OfVector(curve.Direction).Normalize()
            else:
                # Nếu dầm ở file hiện tại
                host = doc.GetElement(ref.ElementId)
                if host and host.Location and isinstance(host.Location, LocationCurve):
                    curve = host.Location.Curve
                    if isinstance(curve, Line):
                        return curve.Direction
    except:
        pass
    return None

# Hàm tính toán vector trượt dọc theo dầm đến khi đụng Line dóng
def get_sliding_vector(p1, v1, p2, v2):
    dx1, dy1 = v1.X, v1.Y
    dx2, dy2 = v2.X, v2.Y
    
    # Định thức giao cắt 2 đường thẳng 2D
    det = dy1 * dx2 - dx1 * dy2
    if abs(det) < 1e-9:
        return None # Trùng hoặc song song, không cắt nhau
        
    t = ((p2.Y - p1.Y) * dx2 - (p2.X - p1.X) * dy2) / det
    
    # Chỉ dịch chuyển trên mặt bằng XY (giữ nguyên Z)
    return XYZ(t * dx1, t * dy1, 0)

def align_tags_along_beams():
    selected_ids = uidoc.Selection.GetElementIds()
    
    tags = []
    reference_line_elem = None
    
    for el_id in selected_ids:
        el = doc.GetElement(el_id)
        if isinstance(el, IndependentTag):
            tags.append(el)
        elif isinstance(el, CurveElement):
            reference_line_elem = el
            
    if not tags:
        from Autodesk.Revit.UI import TaskDialog
        TaskDialog.Show("Thông báo", "Vui lòng quét chọn các Tag cần align (và đường Line dóng) trước!")
        return
        
    if not reference_line_elem:
        try:
            ref = uidoc.Selection.PickObject(ObjectType.Element, LineFilter(), "Click chọn Detail Line làm đường dóng")
            reference_line_elem = doc.GetElement(ref)
        except:
            return # Bỏ qua nếu user bấm ESC
            
    if not reference_line_elem:
        return
        
    curve = reference_line_elem.GeometryCurve
    if not isinstance(curve, Line):
        from Autodesk.Revit.UI import TaskDialog
        TaskDialog.Show("Lỗi", "Vui lòng chọn đường thẳng, không chọn đường cong/arc!")
        return
        
    # Điểm và vector của đường Line dóng
    p2 = curve.GetEndPoint(0)
    v2 = curve.Direction

    t = Transaction(doc, "Move")
    t.Start()

    count = 0
    for tag in tags:
        try:
            if tag.Pinned:
                continue
                
            # Lấy khung bao (Bounding Box) của Tag trong mặt bằng hiện tại
            bbox = tag.get_BoundingBox(doc.ActiveView)
            
            if bbox:
                # Lấy điểm đầu (mép trái) và giữ cao độ Z tâm để làm mốc tịnh tiến
                # Nếu muốn lấy mép phải, bạn đổi bbox.Min.X thành bbox.Max.X
                current_pos = XYZ(bbox.Min.X, tag.TagHeadPosition.Y, tag.TagHeadPosition.Z)
            else:
                current_pos = tag.TagHeadPosition
            
            # Lấy vector hướng của dầm
            beam_direction = get_tag_host_direction(tag, doc)
            
            translation_vector = None
            
            if beam_direction:
                # Trượt Tag dọc theo dầm để giao với đường Line
                translation_vector = get_sliding_vector(current_pos, beam_direction, p2, v2)
            else:
                # Fallback: Dóng vuông góc nếu host không phải là dầm (ví dụ: sàn)
                align_line = Line.CreateUnbound(p2, v2)
                projected_result = align_line.Project(current_pos)
                if projected_result:
                    translation_vector = projected_result.XYZPoint - current_pos
                    translation_vector = XYZ(translation_vector.X, translation_vector.Y, 0)
                    
            if translation_vector and not translation_vector.IsAlmostEqualTo(XYZ.Zero):
                # Tịnh tiến Tag (Move)
                ElementTransformUtils.MoveElement(doc, tag.Id, translation_vector)
                
                # Sửa lỗi đuôi Leader chạy lộn xộn
                if tag.HasLeader:
                    tag.LeaderEndCondition = LeaderEndCondition.Free
                    
            count += 1
        except Exception as e:
            pass
            
    # Tự động dọn dẹp (xóa) Detail Line sau khi canh lề xong
    try:
        doc.Delete(reference_line_elem.Id)
    except:
        pass

    t.Commit()

# Khởi chạy tool
align_tags_along_beams()