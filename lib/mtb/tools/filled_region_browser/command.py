# -*- coding: utf-8 -*-
"""The command owns model writes; windows only collect explicit requests."""
from __future__ import unicode_literals

from pyrevit import forms
from .revit_adapter import RegionLibrary
from .window import RegionWindow


def run(uiapp):
    if uiapp.ActiveUIDocument is None or uiapp.ActiveUIDocument.Document.IsFamilyDocument:
        forms.alert('Open a Revit project before using Filled Region Browser.', title='Filled Region Browser')
        return
    library = RegionLibrary(uiapp)
    selected, state = None, None
    while True:
        try:
            rows, reason, view_scale = library.snapshot()
        except Exception as error:
            forms.alert(str(error), title='Filled Region Browser')
            return
        window = RegionWindow(rows, reason, view_scale,
                              lambda default: forms.ask_for_string(default=default,
                                  prompt='Name for the duplicated type:', title='Duplicate Filled Region Type'),
                              selected, state)
        try:
            window.ShowDialog()
            result, state = window.result, window.state
        finally:
            window.Dispose()
        if result is None:
            return
        action, selected, name = result
        try:
            if action == 'duplicate':
                selected = library.duplicate(selected, name)
                # The old search/scope may hide the newly created type.
                state.update(search='', scope=0, page=0)
            elif action == 'draw':
                library.draw(selected)
                return  # let Revit execute its queued Sketch command
            elif action == 'edit':
                library.edit_type(selected)
                return  # let Revit show native Type Properties
        except Exception as error:
            forms.alert(str(error), title='Filled Region Browser')
