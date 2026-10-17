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

# Bộ lọc mở rộng: Cho phép chọn Tag thường, Tag phòng/diện tích và Ký hiệu Spot
class AllLeaderFilter(ISelectionFilter):
    def AllowElement(self, element):
        return isinstance(element, (IndependentTag, SpatialElementTag, SpotDimension))
    def AllowReference(self, ref, point):
        return False

def toggle_all_leaders():
    elements = []
    
    # 1. KIỂM TRA CHỌN TRƯỚC (PRE-SELECTION)
    selected_ids = uidoc.Selection.GetElementIds()
    for e_id in selected_ids:
        elem = doc.GetElement(e_id)
        if isinstance(elem, (IndependentTag, SpatialElementTag, SpotDimension)):
            elements.append(elem)
            
    # 2. NẾU CHƯA CHỌN, YÊU CẦU QUÉT
    if not elements:
        try:
            refs = uidoc.Selection.PickObjects(ObjectType.Element, AllLeaderFilter(), "Quét chọn Tags, Room Tags, Spot Elevations... rồi BẤM FINISH")
            for ref in refs:
                elements.append(doc.GetElement(ref))
        except Exceptions.OperationCanceledException:
            return 
            
    if not elements:
        return

    # 3. TIẾN HÀNH BẬT/TẮT LEADER
    t = Transaction(doc, "Modify element attributes")
    t.Start()
    
    count = 0
    for elem in elements:
        try:
            # Đảo ngược trạng thái HasLeader cho bất kỳ đối tượng nào lọt qua bộ lọc
            elem.HasLeader = not elem.HasLeader
            count += 1
        except Exception:
            pass
            
    t.Commit()

toggle_all_leaders()