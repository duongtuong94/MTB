# -*- coding: utf-8 -*-
__doc__ = 'python for revit api - Allow join dầm'

import Autodesk
from Autodesk.Revit.DB import Transaction
from pyrevit import revit

# Khởi tạo uidoc và doc chuẩn của pyRevit
uidoc = revit.uidoc
doc = revit.doc

# Lấy các đối tượng đang được chọn trên màn hình
selected_ids = uidoc.Selection.GetElementIds()
Ele = [doc.GetElement(e_id) for e_id in selected_ids]

if Ele:
    t = Transaction(doc, "Allow Join")
    t.Start()
    
    def allow_join_at_end(element):
        # 0 là đầu start, 1 là đầu end của dầm
        Autodesk.Revit.DB.Structure.StructuralFramingUtils.AllowJoinAtEnd(element, 0)
        Autodesk.Revit.DB.Structure.StructuralFramingUtils.AllowJoinAtEnd(element, 1)
        
    for i in Ele:
        try:
            allow_join_at_end(i)
        except Exception:
            pass
            
    t.Commit()