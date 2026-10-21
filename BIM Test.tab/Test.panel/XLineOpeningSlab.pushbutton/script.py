# -*- coding: utf-8 -*-
import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
import Autodesk.Revit.Exceptions as Exceptions

doc = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument
view = doc.ActiveView

class FloorSelectionFilter(ISelectionFilter):
    def AllowElement(self, element):
        return element.Category and element.Category.Id.IntegerValue == int(BuiltInCategory.OST_Floors)
    def AllowReference(self, ref, point):
        return False

def auto_draw_all_openings():
    valid_views = [
        ViewType.FloorPlan, ViewType.EngineeringPlan, 
        ViewType.CeilingPlan, ViewType.Detail, 
        ViewType.Section, ViewType.DraftingView
    ]
    
    if view.ViewType not in valid_views:
        TaskDialog.Show("Lỗi", "Vui lòng chạy tool trong mặt bằng hoặc chi tiết.")
        return

    floors = []
    
    # 1. ƯU TIÊN SÀN ĐÃ CHỌN TRƯỚC TỪ MÀN HÌNH
    selected_ids = uidoc.Selection.GetElementIds()
    for e_id in selected_ids:
        elem = doc.GetElement(e_id)
        if elem.Category and elem.Category.Id.IntegerValue == int(BuiltInCategory.OST_Floors):
            floors.append(elem)
            
    # 2. NẾU CHƯA CHỌN, YÊU CẦU QUÉT
    if not floors:
        try:
            refs = uidoc.Selection.PickObjects(ObjectType.Element, FloorSelectionFilter(), "Quét chọn sàn, SAU ĐÓ BẤM NÚT 'FINISH' (GÓC TRÊN TRÁI)")
            for ref in refs:
                floors.append(doc.GetElement(ref))
        except Exceptions.OperationCanceledException:
            return
            
    if not floors:
        return

    view_z = view.Origin.Z
    if view.GenLevel:
        view_z = view.GenLevel.Elevation

    t = Transaction(doc, "Tự động vẽ X lỗ mở")
    t.Start()
    
    drawn_count = 0
    error_count = 0

    for floor in floors:
        try:
            # SỬ DỤNG HÀM API ĐẶC QUYỀN: Bắt buộc Revit giao nộp mặt trên cùng của sàn
            top_face_refs = HostObjectUtils.GetTopFaces(floor)
        except:
            continue

        for ref in top_face_refs:
            face = floor.GetGeometryObjectFromReference(ref)
            
            # Đảm bảo đây là mặt phẳng (không phải mặt cong)
            if not isinstance(face, PlanarFace):
                continue
                
            loops = face.GetEdgesAsCurveLoops()
            
            # Nếu mảng loop <= 1 nghĩa là chỉ có đường viền bao ngoài, không có lỗ thủng
            if len(loops) <= 1:
                continue 

            normal = face.FaceNormal
            
            for loop in loops:
                # THUẬT TOÁN NHẬN DIỆN LỖ MỞ API CHUẨN:
                # - Mép bao ngoài sàn luôn quay ngược chiều kim đồng hồ (Counter-clockwise) so với Pháp tuyến
                # - Lỗ khoét bên trong luôn quay thuận chiều kim đồng hồ (Clockwise)
                if loop.IsCounterclockwise(normal):
                    continue # Bỏ qua mép bao ngoài của sàn
                    
                curves = [c for c in loop]
                pts = []
                is_all_lines = True
                
                for c in curves:
                    if not isinstance(c, Line):
                        is_all_lines = False
                    for p in c.Tessellate()[:-1]:
                        pts.append(p)
                        
                xs = [p.X for p in pts]
                ys = [p.Y for p in pts]
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)
                
                # Ưu tiên vẽ X nối 4 góc cho Lỗ tứ giác (Chữ nhật, vuông, hình thang)
                if len(curves) == 4 and is_all_lines:
                    p0 = curves[0].GetEndPoint(0)
                    p1 = curves[1].GetEndPoint(0)
                    p2 = curves[2].GetEndPoint(0)
                    p3 = curves[3].GetEndPoint(0)
                    
                    pt_a = XYZ(p0.X, p0.Y, view_z)
                    pt_b = XYZ(p2.X, p2.Y, view_z) # Đường chéo 1
                    pt_c = XYZ(p1.X, p1.Y, view_z)
                    pt_d = XYZ(p3.X, p3.Y, view_z) # Đường chéo 2
                
                # Dùng Bounding Box cho các lỗ hình tròn hoặc hình dạng phức tạp
                else:
                    pt_a = XYZ(min_x, min_y, view_z)
                    pt_b = XYZ(max_x, max_y, view_z)
                    pt_c = XYZ(min_x, max_y, view_z)
                    pt_d = XYZ(max_x, min_y, view_z)
                
                try:
                    if pt_a.DistanceTo(pt_b) > 0.01:
                        doc.Create.NewDetailCurve(view, Line.CreateBound(pt_a, pt_b))
                    if pt_c.DistanceTo(pt_d) > 0.01:
                        doc.Create.NewDetailCurve(view, Line.CreateBound(pt_c, pt_d))
                    drawn_count += 1
                except:
                    error_count += 1

    t.Commit()
    
    if drawn_count > 0:
        TaskDialog.Show("Thành công", "Đã tự động vẽ X cho {} lỗ mở!".format(drawn_count))
    elif error_count > 0:
        TaskDialog.Show("Lỗi", "Đã tìm thấy lỗ mở nhưng không thể vẽ (Lỗi do cao độ mặt phẳng View).")
    else:
        TaskDialog.Show("Thông báo", "Không tìm thấy lỗ mở nào bên trong tấm sàn được chọn.")

auto_draw_all_openings()