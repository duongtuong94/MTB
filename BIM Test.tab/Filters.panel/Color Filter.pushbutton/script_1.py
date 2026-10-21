# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals

"""MTB Color Filter - independent implementation for pyRevit / Revit 2025.

Design goals:
- Self-contained: no private DLLs, no telemetry, no logging.
- Category -> parameter -> value workflow.
- Algorithmic palettes (Soft / Vivid / Spectrum); no third-party palette tables.
- Select closes the dialog and returns control to Revit without zooming.
- Graphic overrides never modify Projection Line settings.
"""

try:
    unicode
except NameError:
    unicode = str

import clr
import math
import colorsys
import re
import traceback
import random

clr.AddReference('System.Windows.Forms')
clr.AddReference('System.Drawing')

from System import EventArgs
from System.Collections.Generic import List, HashSet
from System.Drawing import Color, Point, Size, Font
from System.Windows.Forms import (
    Form, Label, Button, ComboBox, ComboBoxStyle, ListView, View, ListBox, TextBox, ColorDialog,
    ColumnHeader, GroupBox, RadioButton, CheckBox, NumericUpDown,
    FormStartPosition, FormBorderStyle, DialogResult, MessageBox,
    MessageBoxButtons, MessageBoxIcon, AnchorStyles, FlatStyle
)

from pyrevit import revit, DB

doc = revit.doc
uidoc = revit.uidoc
active_view = doc.ActiveView


def u(value, fallback=u''):
    try:
        if value is None:
            return fallback
        return unicode(value)
    except Exception:
        return fallback


def eid_value(eid):
    try:
        return int(eid.Value)
    except Exception:
        try:
            return int(eid.IntegerValue)
        except Exception:
            return -1


def same_eid(a, b):
    return eid_value(a) == eid_value(b)


def to_net_ids(ids):
    result = List[DB.ElementId]()
    seen = set()
    for item in ids:
        try:
            eid = item.Id if hasattr(item, 'Id') else item
            key = eid_value(eid)
            if key >= 0 and key not in seen:
                seen.add(key)
                result.Add(eid)
        except Exception:
            pass
    return result


def element_name(element, fallback=u'<Unnamed>'):
    if element is None:
        return fallback
    try:
        name = element.Name
        if name:
            return u(name)
    except Exception:
        pass
    return fallback


def safe_category(element):
    try:
        if element.Category is not None:
            return element.Category
    except Exception:
        pass
    return None


def collect_elements(scope_project):
    try:
        if scope_project:
            items = DB.FilteredElementCollector(doc).WhereElementIsNotElementType()
        else:
            items = DB.FilteredElementCollector(doc, active_view.Id).WhereElementIsNotElementType()
        result = []
        for e in items:
            if safe_category(e) is not None:
                result.append(e)
        return result
    except Exception:
        return []


def get_type_element(element):
    try:
        tid = element.GetTypeId()
        if eid_value(tid) >= 0:
            return doc.GetElement(tid)
    except Exception:
        pass
    return None


class ParamDescriptor(object):
    def __init__(self, source, pid, name):
        self.source = source
        self.pid = pid
        self.pid_value = eid_value(pid)
        self.name = u(name)

    @property
    def label(self):
        return u'{0} — {1}'.format(self.name, self.source)


class ValueRecord(object):
    def __init__(self, display, storage, raw, ids):
        self.display = u(display)
        self.storage = storage
        self.raw = raw
        self.ids = list(ids)
        self.rgb = (220, 220, 220)


def iter_parameters(element, source):
    owner = element if source == 'Instance' else get_type_element(element)
    if owner is None:
        return []
    try:
        return list(owner.Parameters)
    except Exception:
        return []


def parameter_for_descriptor(element, desc):
    owner = element if desc.source == 'Instance' else get_type_element(element)
    if owner is None:
        return None
    try:
        for p in owner.Parameters:
            try:
                if eid_value(p.Id) == desc.pid_value:
                    return p
            except Exception:
                pass
    except Exception:
        pass
    return None


def parameter_value(parameter):
    if parameter is None or not parameter.HasValue:
        return None
    st = parameter.StorageType
    try:
        if st == DB.StorageType.String:
            raw = parameter.AsString()
            if raw is None:
                raw = u''
            return (st, u(raw), u(raw) if u(raw) else u'<Blank>')
        if st == DB.StorageType.Integer:
            raw = int(parameter.AsInteger())
            shown = parameter.AsValueString()
            return (st, raw, u(shown) if shown else u(raw))
        if st == DB.StorageType.Double:
            raw = float(parameter.AsDouble())
            shown = parameter.AsValueString()
            return (st, raw, u(shown) if shown else u'{0:.6g}'.format(raw))
        if st == DB.StorageType.ElementId:
            rid = parameter.AsElementId()
            raw = eid_value(rid)
            shown = parameter.AsValueString()
            if not shown:
                target = doc.GetElement(rid)
                shown = element_name(target, u'<None>') if target else u'<None>'
            return (st, raw, u(shown))
    except Exception:
        return None
    return None


def value_key(storage, raw):
    if storage == DB.StorageType.Double:
        return ('D', round(float(raw), 9))
    if storage == DB.StorageType.Integer:
        return ('I', int(raw))
    if storage == DB.StorageType.ElementId:
        return ('E', int(raw))
    return ('S', u(raw))


def palette_rgb(mode, index, total):
    """Generate independent palettes algorithmically rather than storing RGB tables."""
    total = max(1, int(total))
    if mode == 'Soft':
        hue = ((index * 137.507764) + 8.0) % 360.0
        sat = 0.30 + 0.05 * ((index % 3) / 2.0)
        val = 0.96 - 0.025 * (index % 2)
    elif mode == 'Vivid':
        hue = ((index * 137.507764) + 20.0) % 360.0
        sat = 0.70 + 0.08 * ((index % 4) / 3.0)
        val = 0.90 + 0.05 * ((index % 2))
    else:  # Spectrum
        hue = ((float(index) / float(total)) * 330.0 + 10.0) % 360.0
        sat = 0.62 + 0.10 * ((index % 3) / 2.0)
        val = 0.94
    r, g, b = colorsys.hsv_to_rgb(hue / 360.0, sat, val)
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


def revit_color(rgb):
    return DB.Color(int(rgb[0]), int(rgb[1]), int(rgb[2]))


def text_color(rgb):
    # Readable text over color preview row.
    lum = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2])
    return Color.Black if lum > 150 else Color.White


def solid_fill_id():
    try:
        for fpe in DB.FilteredElementCollector(doc).OfClass(DB.FillPatternElement):
            try:
                fp = fpe.GetFillPattern()
                if fp and fp.IsSolidFill:
                    return fpe.Id
            except Exception:
                pass
    except Exception:
        pass
    return DB.ElementId.InvalidElementId


SOLID_FILL_ID = solid_fill_id()


def build_ogs(rgb, options):
    ogs = DB.OverrideGraphicSettings()
    color = revit_color(rgb) if rgb is not None else None

    # Intentionally no Projection Line override.
    if color is not None:
        if options['surface_fg'] and eid_value(SOLID_FILL_ID) >= 0:
            ogs.SetSurfaceForegroundPatternId(SOLID_FILL_ID)
            ogs.SetSurfaceForegroundPatternColor(color)

        if options['surface_bg'] and eid_value(SOLID_FILL_ID) >= 0:
            ogs.SetSurfaceBackgroundPatternId(SOLID_FILL_ID)
            ogs.SetSurfaceBackgroundPatternColor(color)

        if options['cut_fg'] and eid_value(SOLID_FILL_ID) >= 0:
            ogs.SetCutForegroundPatternId(SOLID_FILL_ID)
            ogs.SetCutForegroundPatternColor(color)

        if options['cut_bg'] and eid_value(SOLID_FILL_ID) >= 0:
            ogs.SetCutBackgroundPatternId(SOLID_FILL_ID)
            ogs.SetCutBackgroundPatternColor(color)

        if options['cut_line']:
            ogs.SetCutLineColor(color)

    if options['halftone']:
        ogs.SetHalftone(True)

    if options['transparency'] > 0:
        ogs.SetSurfaceTransparency(int(options['transparency']))

    return ogs

def clean_name(text, limit=80):
    value = re.sub(r'[\\/:{}\[\]|;<>?`~]', '_', u(text))
    value = re.sub(r'\s+', ' ', value).strip()
    return value[:limit] if value else u'Blank'


def make_filter_rule(desc, record):
    pid = desc.pid
    st = record.storage
    if st == DB.StorageType.String:
        return DB.ParameterFilterRuleFactory.CreateEqualsRule(pid, u(record.raw))
    if st == DB.StorageType.Integer:
        return DB.ParameterFilterRuleFactory.CreateEqualsRule(pid, int(record.raw))
    if st == DB.StorageType.Double:
        return DB.ParameterFilterRuleFactory.CreateEqualsRule(pid, float(record.raw), 1e-8)
    if st == DB.StorageType.ElementId:
        return DB.ParameterFilterRuleFactory.CreateEqualsRule(pid, DB.ElementId(int(record.raw)))
    raise Exception('Unsupported parameter storage type.')

def make_element_id_rule(parameter_id, target_id):
    """Force the ElementId rule overload; useful for Revit's Type parameter."""
    provider = DB.ParameterValueProvider(parameter_id)
    evaluator = DB.FilterNumericEquals()
    return DB.FilterElementIdRule(provider, evaluator, target_id)


def record_represents_type(record):
    """True when the selected value group corresponds to element type ids."""
    if record.storage != DB.StorageType.ElementId:
        return False
    target = int(record.raw)
    for eid in record.ids[:20]:
        try:
            e = doc.GetElement(eid)
            if e is not None and eid_value(e.GetTypeId()) == target:
                return True
        except Exception:
            pass
    return False


def type_parameter_candidates(record):
    """Return alternative ElementFilters for the built-in instance Type parameter."""
    if not record_represents_type(record):
        return []
    target_id = DB.ElementId(int(record.raw))
    result = []
    seen = set()
    for bip_name in ('ELEM_TYPE_PARAM', 'SYMBOL_ID_PARAM'):
        try:
            bip = getattr(DB.BuiltInParameter, bip_name)
            pid = DB.ElementId(bip)
            key = eid_value(pid)
            if key in seen:
                continue
            seen.add(key)
            rule = make_element_id_rule(pid, target_id)
            result.append((u'Type', DB.ElementParameterFilter(rule)))
        except Exception:
            pass
    return result


def filter_candidates(desc, record):
    """Build candidates without pre-rejecting them from a utility-list lookup."""
    result = []
    try:
        # Force ElementId evaluator for ElementId storage to avoid overload ambiguity.
        if record.storage == DB.StorageType.ElementId:
            rule = make_element_id_rule(desc.pid, DB.ElementId(int(record.raw)))
        else:
            rule = make_filter_rule(desc, record)
        result.append((u'Direct', DB.ElementParameterFilter(rule)))
    except Exception:
        pass

    # 'Type' shown on an instance is a special but common View Filter case.
    for item in type_parameter_candidates(record):
        result.append(item)
    return result


def try_set_parameter_filter(pfe, desc, record):
    """Ask the actual ParameterFilterElement to accept a candidate rule."""
    last_error = None
    for mode, element_filter in filter_candidates(desc, record):
        try:
            # First use Revit's instance-level applicability check when available.
            try:
                applicable = pfe.AllRuleParametersApplicable(element_filter)
            except Exception:
                applicable = True
            if not applicable:
                last_error = u'{0} rule is not applicable.'.format(mode)
                continue
            pfe.SetElementFilter(element_filter)
            return True, mode, None
        except Exception as ex:
            last_error = u(ex)
    return False, None, last_error or u'Revit rejected all parameter-filter rules.'


def _id_values(collection):
    values = set()
    try:
        for eid in collection:
            values.add(eid_value(eid))
    except Exception:
        pass
    return values


def filterable_parameter_values(category_ids):
    """Return parameter ids Revit permits in a view parameter filter for these categories."""
    try:
        return _id_values(DB.ParameterFilterUtilities.GetFilterableParametersInCommon(doc, category_ids))
    except Exception:
        return set()


def category_is_filterable(category_id):
    try:
        return eid_value(category_id) in _id_values(DB.ParameterFilterUtilities.GetAllFilterableCategories())
    except Exception:
        # Older/minor builds: let Revit perform the final validation.
        return True


def type_ids_for_record(record):
    result = []
    seen = set()
    for eid in record.ids:
        try:
            element = doc.GetElement(eid)
            if element is None:
                continue
            tid = element.GetTypeId()
            key = eid_value(tid)
            if key >= 0 and key not in seen:
                seen.add(key)
                result.append(tid)
        except Exception:
            pass
    return result


def _type_parameter_id(category_ids):
    """Find the built-in type selector parameter that is filterable for this category."""
    filterable = filterable_parameter_values(category_ids)
    for bip_name in ('ELEM_TYPE_PARAM', 'SYMBOL_ID_PARAM'):
        try:
            bip = getattr(DB.BuiltInParameter, bip_name)
            pid = DB.ElementId(bip)
            if eid_value(pid) in filterable:
                return pid
        except Exception:
            pass
    return None


def type_id_filter(record, category_ids):
    """Fallback for Type-source values using OR(Type == matching type ids)."""
    type_param_id = _type_parameter_id(category_ids)
    if type_param_id is None:
        return None

    type_ids = type_ids_for_record(record)
    if not type_ids:
        return None

    filters = List[DB.ElementFilter]()
    for tid in type_ids:
        try:
            rule = DB.ParameterFilterRuleFactory.CreateEqualsRule(type_param_id, tid)
            filters.Add(DB.ElementParameterFilter(rule))
        except Exception:
            pass

    if filters.Count == 0:
        return None
    if filters.Count == 1:
        return filters[0]
    try:
        return DB.LogicalOrFilter(filters)
    except Exception:
        return None


def build_parameter_filter(desc, record, category_ids):
    """Build a validated filter. Returns (ElementFilter, used_type_id_fallback, error)."""
    filterable = filterable_parameter_values(category_ids)

    # Preferred path: the selected parameter itself is valid for this category.
    if desc is not None and desc.pid_value in filterable:
        try:
            direct = DB.ElementParameterFilter(make_filter_rule(desc, record))
            try:
                applicable = DB.ParameterFilterElement.AllRuleParametersApplicable(doc, category_ids, direct)
            except Exception:
                applicable = True
            if applicable:
                return direct, False, None
        except Exception:
            pass

    # Type parameters can be readable from the ElementType while not being legal
    # rule parameters for instance-based view filters. Preserve the selected value
    # by matching the actual Type Id(s) represented by this value group.
    if desc is not None and desc.source == 'Type':
        fallback = type_id_filter(record, category_ids)
        if fallback is not None:
            try:
                applicable = DB.ParameterFilterElement.AllRuleParametersApplicable(doc, category_ids, fallback)
            except Exception:
                applicable = True
            if applicable:
                return fallback, True, None

    name = desc.name if desc is not None else u'?'
    return None, False, u'Parameter "{0}" is not available to Revit View Filters for this category.'.format(name)


def unique_filter_name(base):
    names = set()
    try:
        for f in DB.FilteredElementCollector(doc).OfClass(DB.FilterElement):
            try:
                names.add(u(f.Name))
            except Exception:
                pass
    except Exception:
        # Fallback for builds/engines where the abstract base class is awkward.
        for cls in (DB.ParameterFilterElement, DB.SelectionFilterElement):
            try:
                for f in DB.FilteredElementCollector(doc).OfClass(cls):
                    names.add(u(f.Name))
            except Exception:
                pass
    if base not in names:
        return base
    i = 2
    while True:
        candidate = u'{0} ({1})'.format(base, i)
        if candidate not in names:
            return candidate
        i += 1



class ColorFilterForm(Form):
    def __init__(self):
        Form.__init__(self)
        self.Text = u'MTB Color Filter'
        self.StartPosition = FormStartPosition.CenterScreen
        self.FormBorderStyle = FormBorderStyle.Sizable
        self.ClientSize = Size(1348, 792)
        self.MinimumSize = Size(1160, 790)
        self.MaximizeBox = True
        self.MinimizeBox = True
        self.ShowIcon = False

        self.elements = []
        self.categories = []
        self.descriptors = []
        self.filtered_descriptors = []
        self.records = []
        self.action = None
        self.selection_ids = []
        self.single_rgb = (239, 190, 93)
        self._color_change_lock = False

        self._build_ui()
        self._wire()
        self._refresh_source()
        self._resize_value_columns()

    def _build_ui(self):
        # LEFT: Selection Range / Parameter Source / Category
        self.grp_scope = GroupBox(Text=u'Selection Range', Location=Point(12, 12), Size=Size(360, 62))
        self.rb_view = RadioButton(Text=u'Active View', Location=Point(12, 25), AutoSize=True, Checked=True)
        self.rb_project = RadioButton(Text=u'All Project', Location=Point(142, 25), AutoSize=True)
        self.grp_scope.Controls.Add(self.rb_view)
        self.grp_scope.Controls.Add(self.rb_project)
        self.grp_scope.Anchor = AnchorStyles.Top | AnchorStyles.Left
        self.Controls.Add(self.grp_scope)

        self.grp_source = GroupBox(Text=u'Parameter Source', Location=Point(12, 80), Size=Size(360, 62))
        self.rb_instance = RadioButton(Text=u'Instance', Location=Point(12, 25), AutoSize=True, Checked=True)
        self.rb_type = RadioButton(Text=u'Type', Location=Point(142, 25), AutoSize=True)
        self.grp_source.Controls.Add(self.rb_instance)
        self.grp_source.Controls.Add(self.rb_type)
        self.grp_source.Anchor = AnchorStyles.Top | AnchorStyles.Left
        self.Controls.Add(self.grp_source)

        self.grp_cat = GroupBox(Text=u'Category', Location=Point(12, 148), Size=Size(360, 580))
        self.lst_cat = ListBox(Location=Point(10, 23), Size=Size(340, 545))
        self.grp_cat.Controls.Add(self.lst_cat)
        self.grp_cat.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left
        self.lst_cat.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right
        self.Controls.Add(self.grp_cat)

        # CENTER: Search / Parameters
        self.grp_search = GroupBox(Text=u'Search', Location=Point(390, 12), Size=Size(360, 62))
        self.txt_param_search = TextBox(Location=Point(10, 24), Size=Size(340, 22))
        self.grp_search.Controls.Add(self.txt_param_search)
        self.grp_search.Anchor = AnchorStyles.Top | AnchorStyles.Left
        self.Controls.Add(self.grp_search)

        self.grp_params = GroupBox(Text=u'Parameters', Location=Point(390, 80), Size=Size(360, 648))
        self.lst_param = ListBox(Location=Point(10, 23), Size=Size(340, 613))
        self.grp_params.Controls.Add(self.lst_param)
        self.grp_params.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left
        self.lst_param.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right
        self.Controls.Add(self.grp_params)

        # VALUE
        self.grp_values = GroupBox(Text=u'Value', Location=Point(768, 12), Size=Size(405, 716))
        self.values = ListView()
        self.values.Location = Point(10, 23)
        self.values.Size = Size(385, 630)
        self.values.View = View.Details
        self.values.CheckBoxes = True
        self.values.FullRowSelect = True
        self.values.GridLines = False
        self.values.HideSelection = False
        self.values.Columns.Add(ColumnHeader(Text=u'Value', Width=245))
        self.values.Columns.Add(ColumnHeader(Text=u'Count', Width=55))
        self.values.Columns.Add(ColumnHeader(Text=u'Color', Width=80))
        self.grp_values.Controls.Add(self.values)
        self.btn_all = Button(Text=u'Check All', Location=Point(80, 665), Size=Size(90, 28))
        self.btn_none = Button(Text=u'Uncheck All', Location=Point(180, 665), Size=Size(100, 28))
        self.grp_values.Controls.Add(self.btn_all)
        self.grp_values.Controls.Add(self.btn_none)
        self.grp_values.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right
        self.values.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right
        self.btn_all.Anchor = AnchorStyles.Bottom | AnchorStyles.Left
        self.btn_none.Anchor = AnchorStyles.Bottom | AnchorStyles.Left
        self.Controls.Add(self.grp_values)

        # RIGHT: Color Options
        x = 1182
        self.grp_palette = GroupBox(Text=u'Color Options', Location=Point(x, 12), Size=Size(154, 253))
        self.rb_palette1 = RadioButton(Text=u'Palette 1', Location=Point(12, 23), AutoSize=True, Checked=True)
        self.rb_palette2 = RadioButton(Text=u'Palette 2', Location=Point(12, 49), AutoSize=True)
        self.rb_palette3 = RadioButton(Text=u'Palette 3', Location=Point(12, 75), AutoSize=True)
        self.rb_random = RadioButton(Text=u'Random', Location=Point(12, 101), AutoSize=True)
        self.rb_gradient = RadioButton(Text=u'Gradient', Location=Point(12, 127), AutoSize=True)
        self.rb_single = RadioButton(Text=u'Single Color', Location=Point(12, 153), AutoSize=True)
        self.rb_nocolor = RadioButton(Text=u'No Color', Location=Point(12, 179), AutoSize=True)
        self.btn_refresh_colors = Button(Text=u'Refresh', Location=Point(12, 211), Size=Size(86, 27))
        for c in (self.rb_palette1, self.rb_palette2, self.rb_palette3, self.rb_random,
                  self.rb_gradient, self.rb_single, self.rb_nocolor, self.btn_refresh_colors):
            self.grp_palette.Controls.Add(c)
        self.grp_palette.Anchor = AnchorStyles.Top | AnchorStyles.Right
        self.Controls.Add(self.grp_palette)

        # Graphic settings
        self.grp_graphics = GroupBox(Text=u'Graphic Settings', Location=Point(x, 274), Size=Size(154, 211))
        self.cb_surface_fg = CheckBox(Text=u'Surface FG', Location=Point(10, 25), AutoSize=True, Checked=True)
        self.cb_surface_bg = CheckBox(Text=u'Surface BG', Location=Point(10, 51), AutoSize=True)
        self.cb_cut_fg = CheckBox(Text=u'Cut FG', Location=Point(10, 77), AutoSize=True, Checked=True)
        self.cb_cut_bg = CheckBox(Text=u'Cut BG', Location=Point(10, 103), AutoSize=True)
        self.cb_cut_line = CheckBox(Text=u'Cut Line', Location=Point(10, 129), AutoSize=True)
        self.cb_halftone = CheckBox(Text=u'Halftone', Location=Point(80, 129), AutoSize=True)
        self.lbl_trans = Label(Text=u'Transparency', Location=Point(10, 163), AutoSize=True)
        self.num_trans = NumericUpDown(Location=Point(89, 159), Size=Size(54, 24), Minimum=0, Maximum=100, Value=0)
        for c in (self.cb_surface_fg, self.cb_surface_bg, self.cb_cut_fg, self.cb_cut_bg,
                  self.cb_cut_line, self.cb_halftone, self.lbl_trans, self.num_trans):
            self.grp_graphics.Controls.Add(c)
        self.grp_graphics.Anchor = AnchorStyles.Top | AnchorStyles.Right
        self.Controls.Add(self.grp_graphics)

        # Filter settings similar to old workflow
        self.grp_filter = GroupBox(Text=u'Filter Settings', Location=Point(x, 494), Size=Size(154, 158))
        self.cb_custom = CheckBox(Text=u'Custom Name', Location=Point(10, 24), AutoSize=True)
        self.txt_custom = TextBox(Location=Point(10, 48), Size=Size(134, 22), Enabled=False)
        self.cb_template = CheckBox(Text=u'Template', Location=Point(10, 78), AutoSize=True)
        self.cb_visible = CheckBox(Text=u'Visible', Location=Point(10, 102), AutoSize=True, Checked=True)
        self.cb_visible.ThreeState = False
        self.btn_filters = Button(Text=u'Filter', Location=Point(10, 126), Size=Size(134, 27))
        for c in (self.cb_custom, self.txt_custom, self.cb_template, self.cb_visible, self.btn_filters):
            self.grp_filter.Controls.Add(c)
        self.grp_filter.Anchor = AnchorStyles.Top | AnchorStyles.Right
        self.Controls.Add(self.grp_filter)

        self.grp_override = GroupBox(Text=u'Graphics', Location=Point(x, 659), Size=Size(154, 64))
        self.btn_reset_override = Button(Text=u'Reset', Location=Point(8, 23), Size=Size(64, 27))
        self.btn_override = Button(Text=u'Override', Location=Point(78, 23), Size=Size(68, 27))
        self.grp_override.Controls.Add(self.btn_reset_override)
        self.grp_override.Controls.Add(self.btn_override)
        self.grp_override.Anchor = AnchorStyles.Top | AnchorStyles.Right
        self.Controls.Add(self.grp_override)

        self.lbl_status = Label(Text=u'', Location=Point(1182, 728), Size=Size(154, 20), Anchor=AnchorStyles.Bottom | AnchorStyles.Right)
        self.Controls.Add(self.lbl_status)

        self.btn_select = Button(Text=u'Select', Location=Point(1182, 750), Size=Size(72, 28), Anchor=AnchorStyles.Bottom | AnchorStyles.Right)
        self.btn_close = Button(Text=u'Close', Location=Point(1264, 750), Size=Size(72, 28), Anchor=AnchorStyles.Bottom | AnchorStyles.Right)
        self.Controls.Add(self.btn_select)
        self.Controls.Add(self.btn_close)

    def _wire(self):
        self.rb_view.CheckedChanged += lambda s, e: self._scope_changed(s)
        self.rb_project.CheckedChanged += lambda s, e: self._scope_changed(s)
        self.rb_instance.CheckedChanged += lambda s, e: self._source_changed(s)
        self.rb_type.CheckedChanged += lambda s, e: self._source_changed(s)
        self.lst_cat.SelectedIndexChanged += lambda s, e: self._refresh_parameters()
        self.txt_param_search.TextChanged += lambda s, e: self._filter_parameter_list()
        self.lst_param.SelectedIndexChanged += lambda s, e: self._refresh_values()
        self.btn_all.Click += lambda s, e: self._set_checks(True)
        self.btn_none.Click += lambda s, e: self._set_checks(False)

        for rb in (self.rb_palette1, self.rb_palette2, self.rb_palette3, self.rb_random,
                   self.rb_gradient, self.rb_single, self.rb_nocolor):
            rb.CheckedChanged += self._color_mode_changed
        self.btn_refresh_colors.Click += lambda s, e: self._apply_color_mode(force=True)

        self.cb_custom.CheckedChanged += lambda s, e: self._toggle_custom_name()
        self.btn_select.Click += self._select
        self.btn_reset_override.Click += self._reset_override
        self.btn_override.Click += self._override
        self.btn_filters.Click += self._create_filters
        self.btn_close.Click += lambda s, e: self.Close()
        self.Resize += lambda s, e: self._resize_value_columns()

    def _resize_value_columns(self):
        # Only the Value pane stretches horizontally; keep Count/Color readable.
        try:
            available = max(150, int(self.values.ClientSize.Width) - 145)
            self.values.Columns[0].Width = available
            self.values.Columns[1].Width = 55
            self.values.Columns[2].Width = 80
        except Exception:
            pass

    def _scope_changed(self, sender):
        try:
            if sender.Checked:
                self._refresh_source()
        except Exception:
            pass

    def _source_changed(self, sender):
        try:
            if sender.Checked:
                self._refresh_parameters()
        except Exception:
            pass

    def _toggle_custom_name(self):
        self.txt_custom.Enabled = bool(self.cb_custom.Checked)

    def _parameter_source(self):
        return 'Type' if self.rb_type.Checked else 'Instance'

    def _current_color_mode(self):
        if self.rb_palette2.Checked:
            return 'Palette2'
        if self.rb_palette3.Checked:
            return 'Palette3'
        if self.rb_random.Checked:
            return 'Random'
        if self.rb_gradient.Checked:
            return 'Gradient'
        if self.rb_single.Checked:
            return 'Single'
        if self.rb_nocolor.Checked:
            return 'None'
        return 'Palette1'

    def _color_mode_changed(self, sender, args):
        if self._color_change_lock:
            return
        try:
            if sender.Checked:
                self._apply_color_mode(force=False)
        except Exception:
            pass

    def _refresh_source(self):
        self.elements = collect_elements(self.rb_project.Checked)
        cats = {}
        for e in self.elements:
            cat = safe_category(e)
            if cat is None:
                continue
            key = eid_value(cat.Id)
            if key not in cats:
                cats[key] = (cat, u(cat.Name))
        self.categories = sorted(cats.values(), key=lambda x: x[1].lower())
        self.lst_cat.Items.Clear()
        for cat, name in self.categories:
            self.lst_cat.Items.Add(name)
        if self.categories:
            self.lst_cat.SelectedIndex = 0
        else:
            self.lst_param.Items.Clear()
            self.values.Items.Clear()
            self.lbl_status.Text = u'No categories.'

    def _category_elements(self):
        idx = self.lst_cat.SelectedIndex
        if idx < 0 or idx >= len(self.categories):
            return []
        cat = self.categories[idx][0]
        cid = eid_value(cat.Id)
        return [e for e in self.elements if safe_category(e) is not None and eid_value(e.Category.Id) == cid]

    def _refresh_parameters(self):
        source = self._parameter_source()
        items = self._category_elements()
        unique = {}
        for e in items[:5000]:
            for p in iter_parameters(e, source):
                try:
                    name = u(p.Definition.Name)
                    pid = p.Id
                    key = (eid_value(pid), name)
                    if key not in unique:
                        unique[key] = ParamDescriptor(source, pid, name)
                except Exception:
                    pass
        self.descriptors = sorted(unique.values(), key=lambda d: d.name.lower())
        self._filter_parameter_list()

    def _filter_parameter_list(self):
        query = u(self.txt_param_search.Text).strip().lower()
        self.filtered_descriptors = [d for d in self.descriptors if (not query or query in d.name.lower())]
        self.lst_param.Items.Clear()
        for d in self.filtered_descriptors:
            self.lst_param.Items.Add(d.name)
        if self.filtered_descriptors:
            self.lst_param.SelectedIndex = 0
        else:
            self.records = []
            self.values.Items.Clear()
            self.lbl_status.Text = u'No parameters.'

    def _selected_descriptor(self):
        idx = self.lst_param.SelectedIndex
        if idx < 0 or idx >= len(self.filtered_descriptors):
            return None
        return self.filtered_descriptors[idx]

    def _refresh_values(self):
        desc = self._selected_descriptor()
        if desc is None:
            self.records = []
            self.values.Items.Clear()
            return
        grouped = {}
        for e in self._category_elements():
            p = parameter_for_descriptor(e, desc)
            data = parameter_value(p)
            if data is None:
                continue
            storage, raw, shown = data
            key = value_key(storage, raw)
            if key not in grouped:
                grouped[key] = [shown, storage, raw, []]
            grouped[key][3].append(e.Id)

        self.records = []
        for shown, storage, raw, ids in grouped.values():
            self.records.append(ValueRecord(shown, storage, raw, ids))
        self.records.sort(key=lambda r: r.display.lower())
        self._apply_color_mode(force=False)

    def _apply_color_mode(self, force=False):
        if not self.records:
            self._render_values()
            return
        mode = self._current_color_mode()
        total = len(self.records)

        if mode == 'Single':
            # Open picker only when user actually switches to Single Color.
            if not force:
                dlg = ColorDialog()
                dlg.FullOpen = True
                dlg.Color = Color.FromArgb(self.single_rgb[0], self.single_rgb[1], self.single_rgb[2])
                if dlg.ShowDialog() == DialogResult.OK:
                    self.single_rgb = (dlg.Color.R, dlg.Color.G, dlg.Color.B)
                else:
                    self._color_change_lock = True
                    try:
                        self.rb_palette1.Checked = True
                    finally:
                        self._color_change_lock = False
                    mode = 'Palette1'
            for record in self.records:
                record.rgb = self.single_rgb

        elif mode == 'None':
            for record in self.records:
                record.rgb = None

        elif mode == 'Random':
            for record in self.records:
                hue = random.random()
                sat = 0.45 + random.random() * 0.35
                val = 0.82 + random.random() * 0.16
                r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
                record.rgb = (int(r * 255), int(g * 255), int(b * 255))

        elif mode == 'Gradient':
            # Warm amber -> aqua/blue gradient, independent MTB color design.
            for i, record in enumerate(self.records):
                t = 0.0 if total <= 1 else float(i) / float(total - 1)
                hue = (38.0 + (205.0 - 38.0) * t) / 360.0
                sat = 0.48 + 0.18 * t
                val = 0.96 - 0.06 * t
                r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
                record.rgb = (int(r * 255), int(g * 255), int(b * 255))

        else:
            alg = 'Soft' if mode == 'Palette1' else ('Vivid' if mode == 'Palette2' else 'Spectrum')
            for i, record in enumerate(self.records):
                record.rgb = palette_rgb(alg, i, total)

        self._render_values()

    def _render_values(self):
        checked_keys = set()
        for item in self.values.Items:
            try:
                if item.Checked and item.Tag is not None:
                    r = item.Tag
                    checked_keys.add(value_key(r.storage, r.raw))
            except Exception:
                pass

        self.values.BeginUpdate()
        try:
            self.values.Items.Clear()
            for record in self.records:
                item = self.values.Items.Add(record.display)
                item.SubItems.Add(unicode(len(record.ids)))
                if record.rgb is None:
                    item.SubItems.Add(u'—')
                    item.BackColor = Color.White
                    item.ForeColor = Color.Black
                else:
                    item.SubItems.Add(u'{0},{1},{2}'.format(*record.rgb))
                    item.BackColor = Color.FromArgb(record.rgb[0], record.rgb[1], record.rgb[2])
                    item.ForeColor = text_color(record.rgb)
                item.Tag = record
                item.Checked = value_key(record.storage, record.raw) in checked_keys
            self.lbl_status.Text = u'{0} values'.format(len(self.records))
        finally:
            self.values.EndUpdate()

    def _set_checks(self, state):
        for item in self.values.Items:
            item.Checked = bool(state)

    def _selected_records(self):
        result = []
        for item in self.values.Items:
            try:
                if item.Checked and item.Tag is not None:
                    result.append(item.Tag)
            except Exception:
                pass
        return result

    def _options(self):
        return {
            'surface_fg': self.cb_surface_fg.Checked,
            'surface_bg': self.cb_surface_bg.Checked,
            'cut_fg': self.cb_cut_fg.Checked,
            'cut_bg': self.cb_cut_bg.Checked,
            'cut_line': self.cb_cut_line.Checked,
            'halftone': self.cb_halftone.Checked,
            'transparency': int(self.num_trans.Value),
        }

    def _select(self, sender, args):
        records = self._selected_records()
        if not records:
            MessageBox.Show(u'Check at least one value.', u'MTB Color Filter')
            return
        ids = []
        for r in records:
            ids.extend(r.ids)
        self.selection_ids = ids
        self.action = 'select'
        self.DialogResult = DialogResult.OK
        self.Close()

    def _reset_override(self, sender, args):
        records = self._selected_records()
        if not records:
            MessageBox.Show(u'Check at least one value.', u'MTB Color Filter')
            return

        tx = DB.Transaction(doc, 'MTB Reset Element Graphics')
        changed = 0
        failed = 0
        try:
            tx.Start()
            empty_ogs = DB.OverrideGraphicSettings()
            for record in records:
                for eid in record.ids:
                    try:
                        active_view.SetElementOverrides(eid, empty_ogs)
                        changed += 1
                    except Exception:
                        failed += 1
            tx.Commit()
            self.lbl_status.Text = u'Reset {0} / skip {1}'.format(changed, failed)
        except Exception:
            try:
                tx.RollBack()
            except Exception:
                pass
            MessageBox.Show(u'Reset graphics failed.\n\n{0}'.format(u(traceback.format_exc())), u'MTB Color Filter')

    def _override(self, sender, args):
        records = self._selected_records()
        if not records:
            MessageBox.Show(u'Check at least one value.', u'MTB Color Filter')
            return
        tx = DB.Transaction(doc, 'MTB Color Override')
        changed = 0
        failed = 0
        try:
            tx.Start()
            opts = self._options()
            for record in records:
                ogs = build_ogs(record.rgb, opts)
                for eid in record.ids:
                    try:
                        active_view.SetElementOverrides(eid, ogs)
                        changed += 1
                    except Exception:
                        failed += 1
            tx.Commit()
            self.lbl_status.Text = u'Override {0} / skip {1}'.format(changed, failed)
        except Exception:
            try:
                tx.RollBack()
            except Exception:
                pass
            MessageBox.Show(u'Override failed.\n\n{0}'.format(u(traceback.format_exc())), u'MTB Color Filter')

    def _target_filter_view(self):
        if self.cb_template.Checked:
            try:
                tid = active_view.ViewTemplateId
                if eid_value(tid) >= 0:
                    tv = doc.GetElement(tid)
                    if tv is not None:
                        return tv
            except Exception:
                pass
        return active_view

    def _create_filters(self, sender, args):
        records = self._selected_records()
        if not records:
            MessageBox.Show(u'Check at least one value.', u'MTB Color Filter')
            return

        desc = self._selected_descriptor()
        cat_idx = self.lst_cat.SelectedIndex
        if desc is None or cat_idx < 0 or cat_idx >= len(self.categories):
            return

        cat = self.categories[cat_idx][0]
        cats = List[DB.ElementId]()
        cats.Add(cat.Id)
        target_view = self._target_filter_view()
        custom_base = clean_name(u(self.txt_custom.Text), 70) if self.cb_custom.Checked else None

        tx = DB.Transaction(doc, 'MTB Create Color Filters')
        created_parameter = 0
        created_selection = 0
        failed = []

        try:
            tx.Start()
            opts = self._options()

            for record in records:
                if custom_base:
                    base = clean_name(u'{0} | {1}'.format(custom_base, record.display), 110)
                else:
                    base = clean_name(
                        u'MTB | {0} | {1} | {2}'.format(cat.Name, desc.name, record.display),
                        110
                    )
                name = unique_filter_name(base)

                # Preferred: real dynamic Revit Parameter Filter.
                pfe = None
                ok = False
                rule_mode = None
                rule_error = None
                try:
                    pfe = DB.ParameterFilterElement.Create(doc, name, cats)
                    ok, rule_mode, rule_error = try_set_parameter_filter(pfe, desc, record)
                    if ok:
                        target_view.SetFilterOverrides(pfe.Id, build_ogs(record.rgb, opts))
                        target_view.SetFilterVisibility(pfe.Id, bool(self.cb_visible.Checked))
                        created_parameter += 1
                        continue
                except Exception as ex:
                    rule_error = u(ex)

                if pfe is not None:
                    try:
                        doc.Delete(pfe.Id)
                    except Exception:
                        pass

                # Fallback: SelectionFilterElement. It still behaves as a View Filter
                # and preserves the exact current set when the chosen parameter cannot
                # legally be used in a ParameterFilterElement.
                sfe = None
                try:
                    selection_name = unique_filter_name(u'{0} [Selection]'.format(base))
                    sfe = DB.SelectionFilterElement.Create(doc, selection_name)
                    sfe.SetElementIds(to_net_ids(record.ids))
                    target_view.SetFilterOverrides(sfe.Id, build_ogs(record.rgb, opts))
                    target_view.SetFilterVisibility(sfe.Id, bool(self.cb_visible.Checked))
                    created_selection += 1
                except Exception as ex:
                    if sfe is not None:
                        try:
                            doc.Delete(sfe.Id)
                        except Exception:
                            pass
                    failed.append(u'{0}: {1}'.format(record.display, u(ex) or rule_error or u'Unknown error'))

            tx.Commit()

        except Exception:
            try:
                tx.RollBack()
            except Exception:
                pass
            MessageBox.Show(
                u'Create Filters failed.\n\n{0}'.format(u(traceback.format_exc())),
                u'MTB Color Filter'
            )
            return

        total_created = created_parameter + created_selection
        self.lbl_status.Text = u'Filters {0} / fail {1}'.format(total_created, len(failed))

        message = u'Created {0} filter(s).'.format(total_created)
        if created_parameter:
            message += u'\n\nParameter Filters: {0}'.format(created_parameter)
        if created_selection:
            message += u'\nSelection fallback: {0}'.format(created_selection)
        if failed:
            message += u'\n\nFailed:\n{0}'.format(u'\n'.join(failed[:12]))
        MessageBox.Show(message, u'MTB Color Filter')


try:
    form = ColorFilterForm()
    result = form.ShowDialog()
    if result == DialogResult.OK and form.action == 'select':
        uidoc.Selection.SetElementIds(to_net_ids(form.selection_ids))
except Exception:
    MessageBox.Show(
        u'MTB Color Filter could not start.\n\n{0}'.format(u(traceback.format_exc())),
        u'MTB Color Filter Error',
        MessageBoxButtons.OK,
        MessageBoxIcon.Error
    )