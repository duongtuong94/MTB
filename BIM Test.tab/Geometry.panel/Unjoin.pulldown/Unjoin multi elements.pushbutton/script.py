# -*- coding: utf-8 -*-
from Autodesk.Revit.UI.Selection.Selection import PickObject
from Autodesk.Revit.UI.Selection  import ObjectType
from Autodesk.Revit.DB import*
import Autodesk
from Autodesk.Revit.DB import *
from Autodesk.Revit.DB import Element
from System.Collections.Generic import *
import math
from rpw import ui
from rpw.ui.forms import Alert

# Get UIDocument
uidoc = __revit__.ActiveUIDocument
# Get Document 
doc = uidoc.Document

def get_selected_elements():
    selection = uidoc.Selection
    selection_ids = selection.GetElementIds()
    elements = []
    for element_id in selection_ids:
        elements.append(doc.GetElement(element_id))
    return elements

selected_elements = get_selected_elements()

t = Transaction(doc, "Unjoin selected elements only")
t.Start()
try:
    # Lặp qua các cặp đối tượng trong danh sách đã chọn
    count = len(selected_elements)
    for i in range(count):
        for j in range(i + 1, count):
            ele1 = selected_elements[i]
            ele2 = selected_elements[j]
            
            # Chỉ thực hiện Unjoin nếu 2 đối tượng trong selection đang join với nhau
            if JoinGeometryUtils.AreElementsJoined(doc, ele1, ele2):
                JoinGeometryUtils.UnjoinGeometry(doc, ele1, ele2)
except Exception as ex:
    print("Error:", ex)
    
t.Commit()