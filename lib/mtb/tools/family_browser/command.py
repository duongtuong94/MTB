# -*- coding: utf-8 -*-
"""Command orchestration; interactive placement starts only after closing UI."""
from __future__ import unicode_literals

from pyrevit import forms, script
from .storage import UserStore
from .revit_adapter import RevitLibrary
from .window import BrowserWindow


def run(uiapp):
    if uiapp.ActiveUIDocument is None or uiapp.ActiveUIDocument.Document.IsFamilyDocument:
        forms.alert('Open a Revit project before using Family Browser.', title='Family Browser')
        return
    store = UserStore(script.get_universal_data_file('mtb_family_browser_v1', 'json'),
                      str(uiapp.Application.VersionNumber))
    library = RevitLibrary(uiapp, store)
    window = BrowserWindow(library, store)
    try:
        window.ShowDialog()
        result = window.result
    finally:
        window.Dispose()
    if result is None:
        return
    row, type_name = result
    try:
        completed, message = library.apply(row, type_name, lambda text: forms.alert(
            text, title='Family conflict', yes=True, no=True))
        if completed:
            store.touch(row['key'])
            store.save()
        if message:
            forms.alert(message, title='Family Browser')
    except Exception as error:
        forms.alert('Could not complete this operation.\n\n{0}'.format(error), title='Family Browser')
