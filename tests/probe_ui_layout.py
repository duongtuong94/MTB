# -*- coding: utf-8 -*-
"""In-memory WinForms layout probe; never opens Revit or modifies a model.

Run with probe_ui_layout.ps1 in Windows PowerShell (IronPython/.NET Framework).
Synthetic typography/spacing at 100-300% exercises layout constraints, not the
host's real per-monitor DPI handling. Actual Revit/laptop QA is still required.
"""
import sys
import clr
clr.AddReference('System.Windows.Forms')
clr.AddReference('System.Drawing')
from System import Array
from System.IO import File, Path
from System.Drawing import *
from System.Windows.Forms import *
sys.path.insert(0, Path.Combine(workspace, 'lib'))
bim_ui = type(sys)('bim_ui')
sys.modules['bim_ui'] = bim_ui
ui_source = File.ReadAllText(Path.Combine(workspace, 'lib/bim_ui.py'))
ui_source = ui_source.replace('from __future__ import unicode_literals', '')
exec(compile(ui_source, 'bim_ui', 'exec'), bim_ui.__dict__)
from bim_ui import px, table, flow, section, button, viewport

original_configure = bim_ui.configure_form
original_scale = bim_ui.dpi_scale
probe_scale = 1.0
compact = False


def configure_form(form, title, width, height):
    original_configure(form, title, width, height)
    # Match physical font height to the synthetic layout scale on this machine.
    actual = original_scale(form)
    form.Font = Font('Segoe UI', 9.0 * probe_scale / actual)
    form.AutoScaleMode = getattr(AutoScaleMode, 'None')
    form.MinimumSize = Size(1, 1)
    form.Size = (Size(960, 640) if compact else
                 Size(min(int(960 * probe_scale), 1920), min(int(640 * probe_scale), 1080)))


def read(relative):
    return File.ReadAllText(Path.Combine(workspace, relative)).replace('\r\n', '\n')


copy_source = read('BIM Test.tab/Filters.panel/Copy Filters.pushbutton/script.py')
copy_block = copy_source[copy_source.index('class CopyFiltersForm'):copy_source.index('\nif doc.IsFamilyDocument:')]
exec(compile(copy_block, 'CopyFiltersForm', 'exec'))
CopyFiltersForm.load_data = lambda self: None
color_source = read('BIM Test.tab/Filters.panel/Color Filter.pushbutton/script.py')
color_block = color_source[color_source.index('class ColorFilterForm'):color_source.index('\ntry:\n    form = ColorFilterForm()')]
exec(compile(color_block, 'ColorFilterForm', 'exec'))
ColorFilterForm._wire = lambda self: None
ColorFilterForm._refresh_source = lambda self: None
join_source = read('BIM Test.tab/Geometry.panel/JoinGeometry.pushbutton/script.py')
join_block = join_source[join_source.index('class PairRow'):join_source.index('\nform = AutoJoinForm()')]
exec(compile(join_block, 'AutoJoinForm', 'exec'))


class Stub(object):
    Name = 'Sample source view with a long name ' * 3
    def GetElementIds(self):
        return []


source_view = Stub()
uidoc = Stub()
uidoc.Selection = Stub()
CATEGORY_LABELS = ['Walls', 'Structural Framing', 'Floors']
DEFAULT_PAIRS = [(0, 1)]
load_saved_scope = lambda count: False
load_saved_pairs = lambda: [(0, 1)] * 8


def walk(control):
    yield control
    for child in control.Controls:
        for item in walk(child):
            yield item


def layout(form):
    for iteration in range(6):
        for control in walk(form):
            control.PerformLayout()


failures = []
scenarios = [(scale, False) for scale in (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)]
scenarios += [(scale, True) for scale in (1.0, 1.5, 2.5, 3.0)]
for probe_scale, compact in scenarios:
    bim_ui.dpi_scale = lambda control: probe_scale
    for form_class in (CopyFiltersForm, ColorFilterForm, AutoJoinForm):
        form = form_class()
        layout(form)
        if isinstance(form, AutoJoinForm):
            form._layout_rows()
            layout(form)
        for control in walk(form):
            if not isinstance(control, ScrollableControl) or not control.AutoScroll:
                children = list(control.Controls)
                for index, left in enumerate(children):
                    for right in children[index + 1:]:
                        if left.Bounds.IntersectsWith(right.Bounds):
                            failures.append('%s %s%%: overlapping siblings %s / %s' %
                                (form_class.__name__, probe_scale * 100,
                                 left.GetType().Name, right.GetType().Name))
            if isinstance(control, (Button, RadioButton, CheckBox, Label)) and control.AutoSize:
                preferred = control.GetPreferredSize(Size(control.Width, 0))
                if control.Height + 2 < preferred.Height:
                    failures.append('%s %s%%: clipped height %s (%s < %s)' %
                        (form_class.__name__, probe_scale * 100, control.Text,
                         control.Height, preferred.Height))
        # Footer controls must be outside the scrollable content and on-screen.
        root = form.Controls[0]
        footer = root.GetControlFromPosition(0, root.RowCount - 1)
        if footer.Bottom > root.ClientSize.Height + 2 or footer.Top < 0:
            failures.append('%s %s%%: footer outside client area' %
                            (form_class.__name__, probe_scale * 100))
        for action in footer.Controls:
            if action.Right > footer.ClientSize.Width + 2 or action.Bottom > footer.ClientSize.Height + 2:
                failures.append('%s %s%%: footer button outside action strip: %s' %
                                (form_class.__name__, probe_scale * 100, action.Text))
        print('%s @ %s%%: client=%sx%s, footer=%s..%s' %
              (form_class.__name__, probe_scale * 100,
               form.ClientSize.Width, form.ClientSize.Height, footer.Top, footer.Bottom))
        form.Dispose()
if failures:
    raise Exception('\n'.join(failures))
print('PASS: 33 in-memory layout scenarios; live DPI/Revit verification pending.')
