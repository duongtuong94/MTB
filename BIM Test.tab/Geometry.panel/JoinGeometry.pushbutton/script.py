# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals

try:
    unicode
except NameError:
    unicode = str

import clr
import System

clr.AddReference('System.Windows.Forms')
clr.AddReference('System.Drawing')

from System.Drawing import Point, Size, Font, FontStyle, SystemColors, ContentAlignment
from System.Windows.Forms import (
    Form, Panel, Label, ComboBox, Button, RadioButton, GroupBox,
    FlowLayoutPanel, FlowDirection, FormBorderStyle, FormStartPosition,
    MessageBox, MessageBoxButtons, MessageBoxIcon, AnchorStyles,
    ComboBoxStyle, DialogResult, BorderStyle, Padding,
    AutoScaleMode, DockStyle, TableLayoutPanel, ColumnStyle, RowStyle,
    SizeType, AutoSizeMode
)

from pyrevit import revit, DB, script
from bim_ui import configure_form, px, table, flow, section, viewport


# -----------------------------------------------------------------------------
# Revit context
# -----------------------------------------------------------------------------
doc = revit.doc
uidoc = revit.uidoc
active_view = doc.ActiveView


# -----------------------------------------------------------------------------
# Persistent settings
# -----------------------------------------------------------------------------
CONFIG_SECTION = 'MTBTools_AutoJoinGeometry'
config = script.get_config(CONFIG_SECTION)

DEFAULT_PAIRS = [
    (7, 9),    # Structural Columns -> Structural Framing
    (8, 10),   # Structural Floors -> Structural Walls
]

CATEGORY_LABELS = [
    u'Architectural Columns',
    u'Architectural Floors',
    u'Architectural Walls',
    u'Ceilings',
    u'Structural Foundations',
    u'Generic Models',
    u'Roofs',
    u'Structural Columns',
    u'Structural Floors',
    u'Structural Framing',
    u'Structural Walls',
]


def _config_value(name, default_value):
    """Read a pyRevit config value safely, including damaged old config."""
    try:
        value = getattr(config, name)
        if value is None:
            return default_value
        return value
    except Exception:
        try:
            return config.get_option(name, default_value)
        except Exception:
            return default_value


def load_saved_pairs():
    """Return saved ComboBox index pairs or reliable defaults."""
    raw_value = _config_value('last_pairs', '')
    if raw_value is None:
        return list(DEFAULT_PAIRS)

    try:
        raw_text = unicode(raw_value).strip()
    except Exception:
        raw_text = ''

    if not raw_text:
        return list(DEFAULT_PAIRS)

    loaded_pairs = []
    try:
        for pair_text in raw_text.split(';'):
            pair_text = pair_text.strip()
            if not pair_text:
                continue

            parts = pair_text.split(',')
            if len(parts) != 2:
                continue

            left_index = int(parts[0].strip())
            right_index = int(parts[1].strip())

            if (0 <= left_index < len(CATEGORY_LABELS) and
                    0 <= right_index < len(CATEGORY_LABELS)):
                loaded_pairs.append((left_index, right_index))
    except Exception:
        loaded_pairs = []

    return loaded_pairs if loaded_pairs else list(DEFAULT_PAIRS)


def load_saved_scope(selected_count):
    """Restore previous scope, but never enable Selection when it is empty."""
    try:
        last_scope = unicode(_config_value('last_scope', 'selection')).lower()
    except Exception:
        last_scope = 'selection'

    return last_scope == 'selection' and selected_count > 0


def save_preferences(rows_panel, use_selection):
    """Save all visible category rows and the current scope."""
    serialized_pairs = []

    try:
        for control in rows_panel.Controls:
            left_index = int(control.left_combo.SelectedIndex)
            right_index = int(control.right_combo.SelectedIndex)

            if (0 <= left_index < len(CATEGORY_LABELS) and
                    0 <= right_index < len(CATEGORY_LABELS)):
                serialized_pairs.append(
                    u'{0},{1}'.format(left_index, right_index)
                )
    except Exception:
        serialized_pairs = []

    if not serialized_pairs:
        serialized_pairs = [
            u'{0},{1}'.format(left_index, right_index)
            for left_index, right_index in DEFAULT_PAIRS
        ]

    try:
        config.last_pairs = u';'.join(serialized_pairs)
        config.last_scope = u'selection' if use_selection else u'view'
        script.save_config()
    except Exception:
        # Saving preferences must never stop the actual Auto Join command.
        pass


# -----------------------------------------------------------------------------
# General helpers
# -----------------------------------------------------------------------------
def element_id_value(element_id):
    if element_id is None:
        return -1
    try:
        return int(element_id.Value)       # Revit 2024+
    except Exception:
        try:
            return int(element_id.IntegerValue)
        except Exception:
            try:
                return int(element_id)
            except Exception:
                return -1


def unique_elements(elements):
    output = []
    seen_ids = set()

    for element in elements:
        if element is None or isinstance(element, DB.ElementType):
            continue

        value = element_id_value(element.Id)
        if value < 0 or value in seen_ids:
            continue

        seen_ids.add(value)
        output.append(element)

    return output


def get_view_bounding_box(element):
    """Prefer view-specific bounds; fall back to model bounds."""
    try:
        box = element.get_BoundingBox(active_view)
        if box is not None:
            return box
    except Exception:
        pass

    try:
        return element.get_BoundingBox(None)
    except Exception:
        return None


def bounding_boxes_intersect(first, second, tolerance=1e-7):
    """Broad-phase test only. JoinGeometry performs the real Revit validation."""
    try:
        first_box = get_view_bounding_box(first)
        second_box = get_view_bounding_box(second)

        if first_box is None or second_box is None:
            return False

        return not (
            first_box.Max.X < second_box.Min.X - tolerance or
            first_box.Min.X > second_box.Max.X + tolerance or
            first_box.Max.Y < second_box.Min.Y - tolerance or
            first_box.Min.Y > second_box.Max.Y + tolerance or
            first_box.Max.Z < second_box.Min.Z - tolerance or
            first_box.Min.Z > second_box.Max.Z + tolerance
        )
    except Exception:
        return False


def category_id_value(element):
    try:
        return element_id_value(element.Category.Id)
    except Exception:
        return -1


def builtin_category_value(builtin_category):
    try:
        return int(builtin_category)
    except Exception:
        try:
            return element_id_value(DB.ElementId(builtin_category))
        except Exception:
            return -999999999


def parameter_as_integer(element, builtin_parameter, default_value=None):
    try:
        parameter = element.get_Parameter(builtin_parameter)
        if parameter is not None and parameter.HasValue:
            return int(parameter.AsInteger())
    except Exception:
        pass
    return default_value


def floor_is_structural(element):
    """Read the Structural flag first; use Floor API behavior as fallback."""
    value = parameter_as_integer(
        element,
        DB.BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL,
        None
    )
    if value is not None:
        return value == 1

    # Revit exposes SpanDirectionAngle only for structural floors.
    try:
        _ = element.SpanDirectionAngle
        return True
    except Exception:
        return False


def wall_is_structural(element):
    """Use the wall Structural flag; StructuralUsage is a fallback."""
    value = parameter_as_integer(
        element,
        DB.BuiltInParameter.WALL_STRUCTURAL_SIGNIFICANT,
        None
    )
    if value is not None:
        return value == 1

    try:
        usage_text = unicode(element.StructuralUsage).replace(' ', '').lower()
        return usage_text not in ('nonbearing', 'nonstructural', 'none', '0')
    except Exception:
        return False


def element_matches_label(element, label):
    """Match Auto Join groups using built-in categories, not localized names."""
    if element is None or isinstance(element, DB.ElementType):
        return False

    category_value = category_id_value(element)

    if label == u'Architectural Columns':
        return category_value == builtin_category_value(DB.BuiltInCategory.OST_Columns)

    if label == u'Structural Columns':
        return category_value == builtin_category_value(DB.BuiltInCategory.OST_StructuralColumns)

    if label in (u'Architectural Floors', u'Structural Floors'):
        if category_value != builtin_category_value(DB.BuiltInCategory.OST_Floors):
            return False
        is_structural = floor_is_structural(element)
        return is_structural if label == u'Structural Floors' else not is_structural

    if label in (u'Architectural Walls', u'Structural Walls'):
        if category_value != builtin_category_value(DB.BuiltInCategory.OST_Walls):
            return False
        is_structural = wall_is_structural(element)
        return is_structural if label == u'Structural Walls' else not is_structural

    category_map = {
        u'Ceilings': DB.BuiltInCategory.OST_Ceilings,
        u'Structural Foundations': DB.BuiltInCategory.OST_StructuralFoundation,
        u'Generic Models': DB.BuiltInCategory.OST_GenericModel,
        u'Roofs': DB.BuiltInCategory.OST_Roofs,
        u'Structural Framing': DB.BuiltInCategory.OST_StructuralFraming,
    }

    builtin_category = category_map.get(label)
    return (
        builtin_category is not None and
        category_value == builtin_category_value(builtin_category)
    )


def collect_scope_elements(use_selection):
    if use_selection:
        selected_ids = list(uidoc.Selection.GetElementIds())
        return unique_elements([
            doc.GetElement(element_id) for element_id in selected_ids
        ])

    try:
        collector = DB.FilteredElementCollector(doc, active_view.Id)
        return unique_elements(list(collector.WhereElementIsNotElementType()))
    except Exception:
        return []


def elements_for_label(elements, label):
    return [element for element in elements if element_matches_label(element, label)]


def candidate_targets_in_current_view(cutter, target_label):
    """Use Revit's BoundingBoxIntersectsFilter instead of O(N^2) manual scanning."""
    box = get_view_bounding_box(cutter)
    if box is None:
        return []

    # Tiny expansion keeps face-touching elements from falling out on numerical noise.
    eps = 1e-7
    try:
        minimum = DB.XYZ(box.Min.X - eps, box.Min.Y - eps, box.Min.Z - eps)
        maximum = DB.XYZ(box.Max.X + eps, box.Max.Y + eps, box.Max.Z + eps)
        outline = DB.Outline(minimum, maximum)
        bb_filter = DB.BoundingBoxIntersectsFilter(outline)
        collector = DB.FilteredElementCollector(doc, active_view.Id)
        candidates = list(
            collector.WhereElementIsNotElementType().WherePasses(bb_filter)
        )
        return unique_elements([
            e for e in candidates if element_matches_label(e, target_label)
        ])
    except Exception:
        return []


def are_joined(first, second):
    try:
        return DB.JoinGeometryUtils.AreElementsJoined(doc, first, second)
    except Exception:
        return False


def first_element_cuts_second(first, second):
    try:
        return DB.JoinGeometryUtils.IsCuttingElementInJoin(
            doc, first, second
        )
    except Exception:
        return False


def switch_join_order(first, second):
    try:
        DB.JoinGeometryUtils.SwitchJoinOrder(doc, first, second)
        return first_element_cuts_second(first, second)
    except Exception:
        return False


def exception_text(exception):
    try:
        return unicode(exception.Message)
    except Exception:
        return unicode(exception)


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
class PairRow(Panel):
    """Stable DPI-friendly row without nested TableLayoutPanel."""

    def __init__(self, left_index=0, right_index=1):
        Panel.__init__(self)

        self.Height = 42
        self.MinimumSize = Size(320, 42)
        self.Margin = Padding(0)

        self.left_combo = ComboBox()
        self.left_combo.DropDownStyle = ComboBoxStyle.DropDownList
        for item in CATEGORY_LABELS:
            self.left_combo.Items.Add(item)
        self.left_combo.SelectedIndex = max(
            0, min(int(left_index), len(CATEGORY_LABELS) - 1)
        )

        self.reverse_button = Button()
        self.reverse_button.Text = u'⇄'
        self.reverse_button.Font = Font('Segoe UI Symbol', 10, FontStyle.Bold)
        self.reverse_button.Click += self.reverse_values

        self.right_combo = ComboBox()
        self.right_combo.DropDownStyle = ComboBoxStyle.DropDownList
        for item in CATEGORY_LABELS:
            self.right_combo.Items.Add(item)
        self.right_combo.SelectedIndex = max(
            0, min(int(right_index), len(CATEGORY_LABELS) - 1)
        )

        self.Controls.Add(self.left_combo)
        self.Controls.Add(self.reverse_button)
        self.Controls.Add(self.right_combo)

        self.SizeChanged += self._layout_controls
        self._layout_controls(None, None)

    def _layout_controls(self, sender, args):
        """Lay out controls from actual row width, not design-time pixels."""
        w = max(px(self, 320), self.ClientSize.Width)
        h = max(self.left_combo.PreferredHeight + px(self, 12), self.ClientSize.Height)

        side_margin = px(self, 4)
        gap = px(self, 8)
        reverse_w = max(px(self, 50), self.reverse_button.PreferredSize.Width)

        available = w - (side_margin * 2) - reverse_w - (gap * 2)
        combo_w = max(px(self, 100), int(available / 2))

        combo_h = px(self, 28)
        try:
            combo_h = max(px(self, 24), self.left_combo.PreferredHeight)
        except Exception:
            pass

        y_combo = max(2, int((h - combo_h) / 2))
        button_h = max(combo_h, self.reverse_button.PreferredSize.Height)
        y_button = max(2, int((h - button_h) / 2))

        left_x = side_margin
        reverse_x = left_x + combo_w + gap
        right_x = reverse_x + reverse_w + gap
        right_w = max(px(self, 100), w - right_x - side_margin)

        self.left_combo.Location = Point(left_x, y_combo)
        self.left_combo.Size = Size(combo_w, combo_h)

        self.reverse_button.Location = Point(reverse_x, y_button)
        self.reverse_button.Size = Size(reverse_w, button_h)

        self.right_combo.Location = Point(right_x, y_combo)
        self.right_combo.Size = Size(right_w, combo_h)

    def reverse_values(self, sender, args):
        left_index = self.left_combo.SelectedIndex
        self.left_combo.SelectedIndex = self.right_combo.SelectedIndex
        self.right_combo.SelectedIndex = left_index

    def selected_pair(self):
        left_item = self.left_combo.SelectedItem
        right_item = self.right_combo.SelectedItem
        if left_item is None or right_item is None:
            return None
        return unicode(left_item), unicode(right_item)


class AutoJoinForm(Form):
    """Measured DPI layout with a scrollable body and pinned actions."""

    def __init__(self):
        Form.__init__(self)

        configure_form(self, u'BIM Test | Join Geometry', 760, 580)

        self.result_pairs = None
        self.use_selection = False

        self.root = TableLayoutPanel()
        self.root.Dock = DockStyle.Fill
        self.root.Padding = Padding(12)
        self.root.Margin = Padding(0)
        self.root.ColumnCount = 1
        self.root.RowCount = 3
        self.root.ColumnStyles.Add(ColumnStyle(SizeType.Percent, 100.0))
        self.root.RowStyles.Add(RowStyle(SizeType.AutoSize))
        self.root.RowStyles.Add(RowStyle(SizeType.Percent, 100.0))
        self.root.RowStyles.Add(RowStyle(SizeType.AutoSize))
        self.Controls.Add(self.root)

        selected_count = len(list(uidoc.Selection.GetElementIds()))
        restore_selection = load_saved_scope(selected_count)

        # Scope
        scope_layout = flow(self, vertical=True)

        self.selected_radio = RadioButton()
        self.selected_radio.Text = u'Join all selected elements ({0})'.format(selected_count)
        self.selected_radio.AutoSize = True
        self.selected_radio.Enabled = selected_count > 0
        self.selected_radio.Checked = restore_selection
        self.selected_radio.Margin = Padding(0, 0, 0, 5)

        self.view_radio = RadioButton()
        self.view_radio.Text = u'Join all elements in current view'
        self.view_radio.AutoSize = True
        self.view_radio.Checked = not restore_selection
        self.view_radio.Margin = Padding(0)

        scope_layout.Controls.Add(self.selected_radio)
        scope_layout.Controls.Add(self.view_radio)
        scope_group = section(self, u'Scope', scope_layout)
        self.root.Controls.Add(scope_group, 0, 0)

        body = table(rows=2)
        body.ColumnStyles.Add(ColumnStyle(SizeType.Percent, 100.0))
        body.RowStyles.Add(RowStyle(SizeType.AutoSize))
        body.RowStyles.Add(RowStyle(SizeType.Percent, 100.0))
        self.root.Controls.Add(viewport(self, body, 580, 160), 0, 1)

        # Header
        header = TableLayoutPanel()
        header.Dock = DockStyle.Fill
        header.Margin = Padding(0, 0, 0, 4)
        header.Padding = Padding(2)
        header.BackColor = SystemColors.ActiveCaption
        header.ColumnCount = 3
        header.RowCount = 1
        header.ColumnStyles.Add(ColumnStyle(SizeType.Percent, 50.0))
        header.ColumnStyles.Add(ColumnStyle(SizeType.Absolute, float(px(self, 70))))
        header.ColumnStyles.Add(ColumnStyle(SizeType.Percent, 50.0))
        header.RowStyles.Add(RowStyle(SizeType.Percent, 100.0))

        left_label = Label()
        left_label.Text = u'Category [Priority]'
        left_label.TextAlign = ContentAlignment.MiddleCenter
        left_label.Dock = DockStyle.Fill
        left_label.AutoSize = True
        left_label.AutoEllipsis = True

        reverse_label = Label()
        reverse_label.Text = u'Reverse'
        reverse_label.TextAlign = ContentAlignment.MiddleCenter
        reverse_label.Dock = DockStyle.Fill
        reverse_label.AutoSize = True

        right_label = Label()
        right_label.Text = u'Join with Category'
        right_label.TextAlign = ContentAlignment.MiddleCenter
        right_label.Dock = DockStyle.Fill
        right_label.AutoSize = True
        right_label.AutoEllipsis = True

        header.Controls.Add(left_label, 0, 0)
        header.Controls.Add(reverse_label, 1, 0)
        header.Controls.Add(right_label, 2, 0)
        header.AutoSize = True
        body.Controls.Add(header, 0, 0)

        # Rows
        # Plain Panel is intentional here. Nested FlowLayoutPanel +
        # TableLayoutPanel was creating rows whose child controls were invisible
        # on some Revit/Windows DPI combinations.
        self.rows_panel = Panel()
        self.rows_panel.Dock = DockStyle.Fill
        self.rows_panel.Margin = Padding(0)
        self.rows_panel.AutoScroll = True
        self.rows_panel.BorderStyle = BorderStyle.FixedSingle
        self.rows_panel.SizeChanged += self._resize_rows
        body.Controls.Add(self.rows_panel, 0, 1)

        for left_index, right_index in load_saved_pairs():
            self.add_pair_row(left_index, right_index)

        # Bottom actions
        bottom = TableLayoutPanel()
        bottom.Dock = DockStyle.Fill
        bottom.AutoSize = True
        bottom.AutoSizeMode = AutoSizeMode.GrowAndShrink
        bottom.Margin = Padding(0, 10, 0, 0)
        bottom.ColumnCount = 3
        bottom.RowCount = 1
        bottom.ColumnStyles.Add(ColumnStyle(SizeType.AutoSize))
        bottom.ColumnStyles.Add(ColumnStyle(SizeType.Percent, 100.0))
        bottom.ColumnStyles.Add(ColumnStyle(SizeType.AutoSize))

        left_actions = FlowLayoutPanel()
        left_actions.AutoSize = True
        left_actions.AutoSizeMode = AutoSizeMode.GrowAndShrink
        left_actions.FlowDirection = FlowDirection.LeftToRight
        left_actions.WrapContents = True
        left_actions.Margin = Padding(0)

        self.remove_button = Button()
        self.remove_button.Text = u'−'
        self.remove_button.Font = Font('Segoe UI', 12, FontStyle.Bold)
        self.remove_button.AutoSize = True
        self.remove_button.MinimumSize = Size(42, 36)
        self.remove_button.Margin = Padding(0, 0, 6, 0)
        self.remove_button.Click += self.remove_row

        self.add_button = Button()
        self.add_button.Text = u'+'
        self.add_button.Font = Font('Segoe UI', 11, FontStyle.Bold)
        self.add_button.AutoSize = True
        self.add_button.MinimumSize = Size(42, 36)
        self.add_button.Margin = Padding(0)
        self.add_button.Click += self.add_row

        left_actions.Controls.Add(self.remove_button)
        left_actions.Controls.Add(self.add_button)

        right_actions = FlowLayoutPanel()
        right_actions.AutoSize = True
        right_actions.AutoSizeMode = AutoSizeMode.GrowAndShrink
        right_actions.FlowDirection = FlowDirection.LeftToRight
        right_actions.WrapContents = True
        right_actions.Margin = Padding(0)

        self.join_button = Button()
        self.join_button.Text = u'Auto Join'
        self.join_button.AutoSize = True
        self.join_button.MinimumSize = Size(112, 38)
        self.join_button.Padding = Padding(10, 2, 10, 2)
        self.join_button.Margin = Padding(0, 0, 8, 0)
        self.join_button.BackColor = SystemColors.ActiveCaption
        self.join_button.Click += self.confirm

        self.close_button = Button()
        self.close_button.Text = u'Close'
        self.close_button.AutoSize = True
        self.close_button.MinimumSize = Size(92, 38)
        self.close_button.Padding = Padding(10, 2, 10, 2)
        self.close_button.Margin = Padding(0)
        self.close_button.Click += self.close_form

        right_actions.Controls.Add(self.join_button)
        right_actions.Controls.Add(self.close_button)

        bottom.Controls.Add(left_actions, 0, 0)
        spacer = Panel()
        spacer.Dock = DockStyle.Fill
        bottom.Controls.Add(spacer, 1, 0)
        bottom.Controls.Add(right_actions, 2, 0)
        # One wrapping action strip prevents opposing button groups colliding.
        actions = flow(self)
        for action in (self.remove_button, self.add_button, self.join_button, self.close_button):
            action.AutoSize = True
            action.MinimumSize = Size(0, 0)
            action.Padding = Padding(px(self, 8), px(self, 4), px(self, 8), px(self, 4))
            actions.Controls.Add(action)
        self.root.Controls.Add(actions, 0, 2)

        self.CancelButton = self.close_button
        self.Shown += self._on_shown

    def _on_shown(self, sender, args):
        self._resize_rows(sender, args)

    def _row_width(self):
        # ClientSize already excludes a visible vertical scrollbar.
        return max(px(self, 320), self.rows_panel.ClientSize.Width - px(self, 10))

    def _layout_rows(self, scroll_to_control=None):
        """Manually position rows so controls cannot disappear in nested layouts."""
        try:
            self.rows_panel.SuspendLayout()
        except Exception:
            pass

        # Layout from top. Resetting scroll avoids coordinate drift while resizing.
        try:
            current_scroll_y = -self.rows_panel.AutoScrollPosition.Y
        except Exception:
            current_scroll_y = 0
        # Reset scroll trước khi sắp xếp lại các row
        try:
            self.rows_panel.AutoScrollPosition = Point(0, 0)
        except Exception:
            pass

        width = self._row_width()
        top = px(self, 5)
        gap = px(self, 4)

        for control in self.rows_panel.Controls:
            try:
                row_h = max(px(self, 42), control.left_combo.PreferredHeight + px(self, 12),
                            control.reverse_button.PreferredSize.Height + px(self, 8))
                control.Location = Point(px(self, 4), top)
                control.Size = Size(width, row_h)
                control.Visible = True
                control._layout_controls(None, None)
                top += row_h + gap
            except Exception:
                pass

        try:
            self.rows_panel.AutoScrollMinSize = Size(0, top + 4)
            self.rows_panel.ResumeLayout(True)
            self.rows_panel.PerformLayout()
        except Exception:
            try:
                self.rows_panel.ResumeLayout()
            except Exception:
                pass

        if scroll_to_control is not None:
            try:
                self.rows_panel.ScrollControlIntoView(scroll_to_control)
            except Exception:
                pass
        elif current_scroll_y > 0:
            try:
                content_height = top + 4
                viewport_height = self.rows_panel.ClientSize.Height
                max_scroll_y = max(0, content_height - viewport_height)

                safe_scroll_y = min(current_scroll_y, max_scroll_y)

                self.rows_panel.AutoScrollPosition = Point(
                    0,
                    safe_scroll_y
                )
            except Exception:
                pass

    def _resize_rows(self, sender, args):
        self._layout_rows()

    def add_pair_row(self, left_index=None, right_index=None, scroll_to_new=False):
        if left_index is None or right_index is None:
            if self.rows_panel.Controls.Count > 0:
                previous_row = self.rows_panel.Controls[
                    self.rows_panel.Controls.Count - 1
                ]
                left_index = previous_row.left_combo.SelectedIndex
                right_index = previous_row.right_combo.SelectedIndex
            else:
                left_index, right_index = DEFAULT_PAIRS[0]

        row = PairRow(left_index, right_index)
        row.Size = Size(self._row_width(), 42)
        self.rows_panel.Controls.Add(row)

        self._layout_rows(row if scroll_to_new else None)
        return row

    def add_row(self, sender, args):
        self.add_pair_row(scroll_to_new=True)

    def remove_row(self, sender, args):
        count = self.rows_panel.Controls.Count
        if count > 1:
            self.rows_panel.Controls.RemoveAt(count - 1)
            self._layout_rows()

    def close_form(self, sender, args):
        save_preferences(
            self.rows_panel,
            self.selected_radio.Checked
        )
        self.DialogResult = DialogResult.Cancel
        self.Close()

    def confirm(self, sender, args):
        pairs = []
        seen_pairs = set()

        for control in self.rows_panel.Controls:
            selected_pair = control.selected_pair()
            if selected_pair is None:
                continue

            left_label, right_label = selected_pair

            if left_label == right_label:
                answer = MessageBox.Show(
                    u'Có cặp cùng Category: “{0}”.\n\n'
                    u'Tiếp tục xử lý các phần tử cùng nhóm?'.format(left_label),
                    u'Auto Join Geometry',
                    MessageBoxButtons.YesNo,
                    MessageBoxIcon.Warning
                )
                if answer != DialogResult.Yes:
                    return

            key = (left_label, right_label)
            if key not in seen_pairs:
                seen_pairs.add(key)
                pairs.append(key)

        if not pairs:
            MessageBox.Show(
                u'Chưa có cặp Category hợp lệ.',
                u'Auto Join Geometry',
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning
            )
            return

        if self.selected_radio.Checked:
            selected_count = len(list(uidoc.Selection.GetElementIds()))
            if selected_count == 0:
                MessageBox.Show(
                    u'Current Selection đang được chọn nhưng Revit không có phần tử nào được chọn.',
                    u'Auto Join Geometry',
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning
                )
                return

        save_preferences(
            self.rows_panel,
            self.selected_radio.Checked
        )

        self.result_pairs = pairs
        self.use_selection = self.selected_radio.Checked
        self.DialogResult = DialogResult.OK
        self.Close()


# -----------------------------------------------------------------------------
# Show UI
# -----------------------------------------------------------------------------
form = AutoJoinForm()

if form.ShowDialog() != DialogResult.OK or not form.result_pairs:
    raise SystemExit


# -----------------------------------------------------------------------------
# Collect elements and build category diagnostics
# -----------------------------------------------------------------------------
scope_elements = collect_scope_elements(form.use_selection)

if not scope_elements:
    MessageBox.Show(
        u'Không tìm thấy phần tử trong phạm vi đã chọn.',
        u'Auto Join Geometry',
        MessageBoxButtons.OK,
        MessageBoxIcon.Warning
    )
    raise SystemExit

labels_used = set()
for left_label, right_label in form.result_pairs:
    labels_used.add(left_label)
    labels_used.add(right_label)

# For Current View this is used for counts and cutter lists. Candidate targets are
# still retrieved cutter-by-cutter with BoundingBoxIntersectsFilter.
category_cache = {}
for label in labels_used:
    category_cache[label] = elements_for_label(scope_elements, label)


# -----------------------------------------------------------------------------
# Join operation
# -----------------------------------------------------------------------------
joined_count = 0
already_joined_count = 0
switched_count = 0
failed_count = 0
candidate_count = 0
skipped_same_count = 0
no_bbox_count = 0
processed_pairs = set()
error_samples = []
pair_stats = []

transaction = DB.Transaction(doc, u'Clean Join')

try:
    transaction.Start()

    for left_label, right_label in form.result_pairs:
        cutters = category_cache.get(left_label, [])
        scope_targets = category_cache.get(right_label, [])

        stat = {
            'left': left_label,
            'right': right_label,
            'cutters': len(cutters),
            'targets': len(scope_targets),
            'candidates': 0,
            'joined': 0,
            'existing': 0,
            'switched': 0,
            'failed': 0,
        }

        for cutter in cutters:
            cutter_id = element_id_value(cutter.Id)

            if form.use_selection:
                # Selection mode: both sides must belong to the user's selection.
                targets = [
                    target for target in scope_targets
                    if bounding_boxes_intersect(cutter, target)
                ]
            else:
                # Current View mode: let Revit's quick bounding-box filter find
                # candidates in the active view, then apply our category matcher.
                if get_view_bounding_box(cutter) is None:
                    no_bbox_count += 1
                    continue
                targets = candidate_targets_in_current_view(cutter, right_label)

            for target in targets:
                target_id = element_id_value(target.Id)

                if cutter_id == target_id:
                    skipped_same_count += 1
                    continue

                pair_key = (
                    min(cutter_id, target_id),
                    max(cutter_id, target_id)
                )
                if pair_key in processed_pairs:
                    continue
                processed_pairs.add(pair_key)

                candidate_count += 1
                stat['candidates'] += 1

                try:
                    if are_joined(cutter, target):
                        already_joined_count += 1
                        stat['existing'] += 1

                        # Left side is priority/cutting side when Revit supports
                        # a reversible join order for this pair.
                        if not first_element_cuts_second(cutter, target):
                            if switch_join_order(cutter, target):
                                switched_count += 1
                                stat['switched'] += 1
                        continue

                    DB.JoinGeometryUtils.JoinGeometry(doc, cutter, target)
                    joined_count += 1
                    stat['joined'] += 1

                    # Refresh join state before checking cut order. Join remains
                    # valid even when a specific category pair has no switchable order.
                    try:
                        doc.Regenerate()
                    except Exception:
                        pass

                    if not first_element_cuts_second(cutter, target):
                        if switch_join_order(cutter, target):
                            switched_count += 1
                            stat['switched'] += 1

                except Exception as join_exception:
                    failed_count += 1
                    stat['failed'] += 1
                    if len(error_samples) < 8:
                        error_samples.append(
                            u'{0} ↔ {1}: {2}'.format(
                                cutter_id,
                                target_id,
                                exception_text(join_exception)
                            )
                        )

        pair_stats.append(stat)

    transaction.Commit()

except Exception as transaction_exception:
    try:
        if transaction.GetStatus() == DB.TransactionStatus.Started:
            transaction.RollBack()
    except Exception:
        pass

    MessageBox.Show(
        u'Auto Join thất bại và transaction đã được hoàn tác.\n\n{0}'.format(
            exception_text(transaction_exception)
        ),
        u'Auto Join Geometry',
        MessageBoxButtons.OK,
        MessageBoxIcon.Error
    )
    raise SystemExit


# -----------------------------------------------------------------------------
# Result — counts by selected category pair make "scanned but did nothing" visible
# -----------------------------------------------------------------------------
summary = (
    u'Hoàn tất Auto Join Geometry.\n\n'
    u'Phạm vi: {0}\n'
    u'Tổng element trong phạm vi: {1}\n'
    u'Cặp ứng viên theo Bounding Box: {2}\n'
    u'Join mới: {3}\n'
    u'Đã Join từ trước: {4}\n'
    u'Đảo thứ tự cắt: {5}\n'
    u'Không thể Join: {6}'
).format(
    u'Current Selection' if form.use_selection else u'Current View',
    len(scope_elements),
    candidate_count,
    joined_count,
    already_joined_count,
    switched_count,
    failed_count
)

summary += u'\n\nChi tiết từng cặp:'
for stat in pair_stats:
    summary += (
        u'\n• {0} ({1}) → {2} ({3}): candidates {4}, new {5}, existing {6}, fail {7}'
    ).format(
        stat['left'], stat['cutters'],
        stat['right'], stat['targets'],
        stat['candidates'], stat['joined'],
        stat['existing'], stat['failed']
    )

if no_bbox_count:
    summary += u'\n\nKhông có BoundingBox trong Active View: {0}'.format(no_bbox_count)

if error_samples:
    summary += (
        u'\n\nMột số lỗi Revit đã bỏ qua:\n- '
        + u'\n- '.join(error_samples)
    )

if candidate_count == 0:
    summary += (
        u'\n\nGợi ý: nếu một cặp hiện 0 element ở bên trái hoặc bên phải, '
        u'tool đã quét View nhưng không tìm thấy đúng nhóm Category/Structural tương ứng.'
    )

MessageBox.Show(
    summary,
    u'Auto Join Geometry',
    MessageBoxButtons.OK,
    MessageBoxIcon.Information if failed_count == 0 else MessageBoxIcon.Warning
)
