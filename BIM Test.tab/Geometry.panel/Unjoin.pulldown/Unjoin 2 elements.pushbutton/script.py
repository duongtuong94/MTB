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
#Get UIDocument
uidoc = __revit__.ActiveUIDocument
#Get Document 
doc = uidoc.Document
Currentview = doc.ActiveView
def get_selected_elements():
    selection = uidoc.Selection
    selection_ids = selection.GetElementIds()
    elements = []
    for element_id in selection_ids:
        elements.append(doc.GetElement(element_id))
    return elements
Ele = get_selected_elements()
listele = []
t = Transaction (doc, "Unjoin 2 elements")
t.Start()
try:
    pick = Ele
    for i in pick:     
        listele.append(doc.GetElement(i.Id)) 
    if len(listele) !=2:
        Alert('You must select 2 elements',title="Warning",header= "Something wrong")
    else:
        if JoinGeometryUtils.AreElementsJoined(doc, listele[1], listele[0]):
            JoinGeometryUtils.UnjoinGeometry(doc, listele[1], listele[0])
        else:
            Alert('These elements have not joined yet',title="Warning",header= "Something wrong")
except:
    pass
t.Commit()