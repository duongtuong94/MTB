# -*- coding: utf-8 -*-
__doc__ = 'python for revit api'

import Autodesk
from Autodesk.Revit.DB import *

# Khởi tạo uidoc và doc (Cách viết này áp dụng cho RevitPythonShell hoặc pyRevit bản cũ)
uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

# Sử dụng API chuẩn để lấy các đối tượng đang được chọn trên màn hình thay vì dùng thư viện ngoài
selected_ids = uidoc.Selection.GetElementIds()
Ele = [doc.GetElement(e_id) for e_id in selected_ids]

if Ele:
    t = Transaction(doc, "Disallow Join")
    t.Start()
    
    def disallow_join_at_end(element):
        # 0 là đầu start, 1 là đầu end của dầm
        Autodesk.Revit.DB.Structure.StructuralFramingUtils.DisallowJoinAtEnd(element, 0)
        Autodesk.Revit.DB.Structure.StructuralFramingUtils.DisallowJoinAtEnd(element, 1)
        
    for i in Ele:
        try:
            disallow_join_at_end(i)
        except:
            pass
            
    t.Commit()