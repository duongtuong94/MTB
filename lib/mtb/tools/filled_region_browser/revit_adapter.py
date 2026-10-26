# -*- coding: utf-8 -*-
"""Revit reads, explicit type duplication and native command dispatch."""
from __future__ import unicode_literals

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit import DB, UI
from System.Collections.Generic import List
from .service import validate_name, draw_view_reason


def id_value(identifier):
    try:
        return int(identifier.Value)
    except AttributeError:
        return int(identifier.IntegerValue)


def element_name(element):
    return DB.Element.Name.GetValue(element)


class NativeEditUnavailable(ValueError):
    pass


class RegionLibrary(object):
    def __init__(self, uiapp):
        self.uiapp = uiapp
        self.uidoc = uiapp.ActiveUIDocument
        self.doc = self.uidoc.Document

    def _active(self):
        if self.uiapp.ActiveUIDocument is None or self.uiapp.ActiveUIDocument.Document != self.doc:
            raise ValueError('The active project changed. Reopen Filled Region Browser.')

    def _write_ready(self):
        self._active()
        if self.doc.IsFamilyDocument or self.doc.IsReadOnly or self.doc.IsModifiable:
            raise ValueError('Use an editable project and finish any active Revit edit first.')

    def _type(self, identifier):
        self._active()
        result = self.doc.GetElement(DB.ElementId(identifier))
        if result is None or not isinstance(result, DB.FilledRegionType):
            raise ValueError('This filled region type is no longer available. Refresh the browser.')
        return result

    def _change(self, title, callback):
        transaction = DB.Transaction(self.doc, title)
        try:
            transaction.Start()
            value = callback()
            if transaction.Commit() != DB.TransactionStatus.Committed:
                raise ValueError('Revit did not commit this change.')
            return value
        except Exception:
            if transaction.GetStatus() == DB.TransactionStatus.Started:
                transaction.RollBack()
            raise
        finally:
            transaction.Dispose()

    def _pattern(self, identifier, color, cache):
        key = id_value(identifier)
        if key not in cache:
            result = dict(name='<None>', none=True, solid=False, target='Drafting', grids=[])
            element = self.doc.GetElement(identifier) if key >= 0 else None
            if element is not None:
                pattern = element.GetFillPattern()
                try:
                    grids = []
                    for grid in pattern.GetFillGrids():
                        try:
                            grids.append(dict(angle=float(grid.Angle), offset=float(grid.Offset),
                                              shift=float(grid.Shift), origin=(float(grid.Origin.U), float(grid.Origin.V)),
                                              segments=[float(s) for s in grid.GetSegments()],
                                              segment_encoding='revit'))
                        finally:
                            grid.Dispose()
                    result.update(name=element_name(element), none=False, solid=bool(pattern.IsSolidFill),
                                  target=str(pattern.Target), grids=grids)
                finally:
                    pattern.Dispose()
            cache[key] = result
        layer = dict(cache[key])
        layer['color'] = ((0, 0, 0) if layer['none'] else
                          (int(color.Red), int(color.Green), int(color.Blue)))
        return layer

    def snapshot(self):
        self._active()
        rows, patterns = [], {}
        for region_type in DB.FilteredElementCollector(self.doc).OfClass(DB.FilledRegionType):
            row = dict(id=id_value(region_type.Id), name=element_name(region_type),
                       masking=bool(region_type.IsMasking), line_weight=int(region_type.LineWeight),
                       can_duplicate=bool(region_type.CanBeCopied), error='')
            try:
                row['foreground'] = self._pattern(region_type.ForegroundPatternId, region_type.ForegroundPatternColor, patterns)
                row['background'] = self._pattern(region_type.BackgroundPatternId, region_type.BackgroundPatternColor, patterns)
            except Exception as error:
                row['error'] = str(error)
                row['foreground'] = row['background'] = dict(name='Unavailable', none=True, solid=False,
                                                            target='Drafting', color=(0, 0, 0), grids=[])
            rows.append(row)
        view = self.uidoc.ActiveView
        reason = draw_view_reason(str(view.ViewType), bool(view.IsTemplate))
        if self.doc.IsReadOnly or self.doc.IsModifiable:
            reason = 'Finish the current edit or open an editable project to draw.'
        return rows, reason, max(1, int(view.Scale))

    def duplicate(self, identifier, name):
        self._write_ready()
        source = self._type(identifier)
        names = [element_name(t) for t in DB.FilteredElementCollector(self.doc).OfClass(DB.FilledRegionType)]
        name = validate_name(name, names)
        if not source.CanBeCopied:
            raise ValueError('Revit does not allow this type to be duplicated.')
        # Native Duplicate copies all parameters, not just the visible swatch.
        result = self._change('Library: Duplicate Filled Region Type', lambda: source.Duplicate(name))
        return id_value(result.Id)

    def draw(self, identifier):
        self._write_ready()
        region_type = self._type(identifier)
        view = self.uidoc.ActiveView
        reason = draw_view_reason(str(view.ViewType), bool(view.IsTemplate))
        if reason:
            raise ValueError(reason)
        command = UI.RevitCommandId.LookupPostableCommandId(UI.PostableCommand.FilledRegion)
        if not self.uiapp.CanPostCommand(command):
            raise ValueError('Revit cannot start Filled Region sketching in the current context.')
        # Prefer the API that queues the exact type without changing defaults.
        if self.uidoc.CanPlaceElementType(region_type):
            self.uidoc.PostRequestForElementTypePlacement(region_type)
            return
        # Some element types have no generic placement handler. Use the native
        # Filled Region command with its default type set explicitly instead.
        group = DB.ElementTypeGroup.FilledRegionType
        if not self.doc.IsDefaultElementTypeIdValid(group, region_type.Id):
            raise ValueError('Revit rejected this default filled region type.')
        previous = self.doc.GetDefaultElementTypeId(group)
        old_selection = list(self.uidoc.Selection.GetElementIds())
        changed = previous != region_type.Id
        if changed:
            self._change('Library: Choose Filled Region Type',
                         lambda: self.doc.SetDefaultElementTypeId(group, region_type.Id))
        try:
            self.uidoc.Selection.SetElementIds(List[DB.ElementId]())
            self.uiapp.PostCommand(command)
        except Exception:
            try:
                if changed:
                    self._change('Library: Restore Filled Region Type',
                                 lambda: self.doc.SetDefaultElementTypeId(group, previous))
            finally:
                self.uidoc.Selection.SetElementIds(List[DB.ElementId](old_selection))
            raise

    def edit_type(self, identifier):
        self._write_ready()
        region_type = self._type(identifier)
        command = UI.RevitCommandId.LookupPostableCommandId(UI.PostableCommand.TypeProperties)
        old_selection = list(self.uidoc.Selection.GetElementIds())
        candidates = [element.Id for element in DB.FilteredElementCollector(self.doc).OfClass(DB.FilledRegion)
                      if element.GetTypeId() == region_type.Id and element.OwnerViewId == self.uidoc.ActiveView.Id]
        # Revit may allow selecting the type directly (e.g. browser context).
        # If it doesn't, never create a dummy region merely to open properties.
        candidates.append(region_type.Id)
        posted = False
        try:
            for candidate in candidates:
                try:
                    self.uidoc.Selection.SetElementIds(List[DB.ElementId]([candidate]))
                    actual = [id_value(i) for i in self.uidoc.Selection.GetElementIds()]
                    if actual != [id_value(candidate)] or not self.uiapp.CanPostCommand(command):
                        continue
                except Exception:
                    continue
                self.uiapp.PostCommand(command)
                posted = True
                return
            raise NativeEditUnavailable(
                'Revit cannot open native Type Properties for this type in the current context.\n\n'
                'Open a view containing a region of this type, or use Draw Region and then '
                'Edit Type in Revit\'s Properties palette. No temporary region was created.')
        finally:
            if not posted:
                self.uidoc.Selection.SetElementIds(List[DB.ElementId](old_selection))
