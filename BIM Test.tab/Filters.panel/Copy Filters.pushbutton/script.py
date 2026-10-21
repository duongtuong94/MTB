# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals

try:
    unicode
except NameError:
    unicode = str

import clr
clr.AddReference('System.Windows.Forms')
clr.AddReference('System.Drawing')

from System.Drawing import Point, Size, Font, FontStyle, SystemColors
from System.Windows.Forms import (
    Form, CheckedListBox, Label, Button, GroupBox, RadioButton,
    FormBorderStyle, FormStartPosition, DialogResult, MessageBox,
    MessageBoxButtons, MessageBoxIcon
)

from pyrevit import revit, DB
from companytools_common import eid_value, view_can_receive_filters, view_display_name
from bim_ui import configure_form, px, table, flow, section, button, viewport
from System.Windows.Forms import DockStyle, RowStyle, ColumnStyle, SizeType, Padding


doc = revit.doc
uidoc = revit.uidoc
source_view = doc.ActiveView


class CopyFiltersForm(Form):
    def __init__(self):
        Form.__init__(self)
        configure_form(self, u'BIM Test | Copy Filters', 800, 600)

        self.filter_ids = []
        self.all_views = []
        self.open_views = []
        self.current_views = []

        self.filters_list = CheckedListBox()
        self.filters_list.CheckOnClick = True
        self.filters_list.Dock = DockStyle.Fill
        self.filters_list.IntegralHeight = False
        self.filters_list.HorizontalScrollbar = True

        self.views_list = CheckedListBox()
        self.views_list.CheckOnClick = True
        self.views_list.Dock = DockStyle.Fill
        self.views_list.IntegralHeight = False
        self.views_list.HorizontalScrollbar = True

        self.copy_button = button(self, u'Copy', self.copy_click)
        self.copy_button.BackColor = SystemColors.ActiveCaption

        self.open_radio = RadioButton()
        self.open_radio.Text = u'Active Views'
        self.open_radio.AutoSize = True
        self.open_radio.CheckedChanged += self.view_scope_changed

        self.all_radio = RadioButton()
        self.all_radio.Text = u'All Views'
        self.all_radio.AutoSize = True
        self.all_radio.Checked = True
        self.all_radio.CheckedChanged += self.view_scope_changed

        scope = flow(self)
        scope.Controls.Add(self.open_radio)
        scope.Controls.Add(self.all_radio)

        close_button = button(self, u'Close', lambda s, e: self.Close())
        self.CancelButton = close_button

        self.status = Label()
        self.status.AutoSize = True
        self.status.Dock = DockStyle.Top
        self.status.Text = u'Source: {0}'.format(source_view.Name)

        root = table(rows=3)
        root.Padding = Padding(px(self, 8))
        root.ColumnStyles.Add(ColumnStyle(SizeType.Percent, 100.0))
        root.RowStyles.Add(RowStyle(SizeType.Percent, 100.0))
        root.RowStyles.Add(RowStyle(SizeType.AutoSize))
        root.RowStyles.Add(RowStyle(SizeType.AutoSize))
        self.Controls.Add(root)
        content = table(columns=2)
        content.ColumnStyles.Add(ColumnStyle(SizeType.Percent, 50.0))
        content.ColumnStyles.Add(ColumnStyle(SizeType.Percent, 50.0))
        content.RowStyles.Add(RowStyle(SizeType.Percent, 100.0))
        for column, title, listing in ((0, u'Filters to copy', self.filters_list),
                                       (1, u'Destination Views / Templates', self.views_list)):
            pane = table(rows=3)
            pane.ColumnStyles.Add(ColumnStyle(SizeType.Percent, 100.0))
            pane.RowStyles.Add(RowStyle(SizeType.Percent, 100.0))
            pane.RowStyles.Add(RowStyle(SizeType.AutoSize))
            pane.RowStyles.Add(RowStyle(SizeType.AutoSize))
            pane.Controls.Add(section(self, title, listing, fill=True), 0, 0)
            actions = flow(self)
            actions.Controls.Add(button(self, u'Check All',
                lambda s, e, target=listing: self.set_all(target, True)))
            actions.Controls.Add(button(self, u'Uncheck All',
                lambda s, e, target=listing: self.set_all(target, False)))
            pane.Controls.Add(actions, 0, 1)
            if column == 1:
                pane.Controls.Add(section(self, u'Views', scope), 0, 2)
            content.Controls.Add(pane, column, 0)
        root.Controls.Add(viewport(self, content, 600, 260), 0, 0)
        root.Controls.Add(self.status, 0, 1)
        footer = flow(self)
        footer.Controls.Add(self.copy_button)
        footer.Controls.Add(close_button)
        root.Controls.Add(footer, 0, 2)

        def wrap_status(sender=None, args=None):
            self.status.MaximumSize = Size(max(1, root.ClientSize.Width - root.Padding.Horizontal), 0)
        root.SizeChanged += wrap_status
        wrap_status()

        self.load_data()

    def set_all(self, control, checked):
        for index in range(control.Items.Count):
            control.SetItemChecked(index, checked)

    def load_data(self):
        try:
            ordered = list(source_view.GetOrderedFilters())
        except Exception:
            ordered = list(source_view.GetFilters())

        self.filter_ids = []
        self.filters_list.Items.Clear()
        for filter_id in ordered:
            element = doc.GetElement(filter_id)
            if element is None:
                continue
            self.filter_ids.append(filter_id)
            self.filters_list.Items.Add(element.Name)

        all_views = []
        for view in DB.FilteredElementCollector(doc).OfClass(DB.View):
            try:
                if eid_value(view.Id) == eid_value(source_view.Id):
                    continue
                if view_can_receive_filters(view):
                    all_views.append(view)
            except Exception:
                pass
        self.all_views = sorted(all_views, key=lambda x: view_display_name(x).lower())

        open_ids = set()
        try:
            for ui_view in uidoc.GetOpenUIViews():
                open_ids.add(eid_value(ui_view.ViewId))
        except Exception:
            pass
        self.open_views = [x for x in self.all_views if eid_value(x.Id) in open_ids]
        self.refresh_views()

        if not self.filter_ids:
            self.copy_button.Enabled = False
            self.status.Text = u'Active View has no filters: {0}'.format(source_view.Name)

    def refresh_views(self):
        self.current_views = self.open_views if self.open_radio.Checked else self.all_views
        self.views_list.Items.Clear()
        for view in self.current_views:
            self.views_list.Items.Add(view_display_name(view))

    def view_scope_changed(self, sender, args):
        if sender.Checked:
            self.refresh_views()

    def copy_click(self, sender, args):
        selected_filter_ids = [self.filter_ids[i] for i in range(self.filters_list.Items.Count)
                               if self.filters_list.GetItemChecked(i)]
        selected_views = [self.current_views[i] for i in range(self.views_list.Items.Count)
                          if self.views_list.GetItemChecked(i)]

        if not selected_filter_ids:
            MessageBox.Show(u'Please select at least one filter.', u'Copy Filters',
                            MessageBoxButtons.OK, MessageBoxIcon.Warning)
            return
        if not selected_views:
            MessageBox.Show(u'Please select at least one destination view.', u'Copy Filters',
                            MessageBoxButtons.OK, MessageBoxIcon.Warning)
            return

        copied = 0
        skipped = []
        try:
            with revit.Transaction(u'Copy Filters'):
                for target in selected_views:
                    for filter_id in selected_filter_ids:
                        try:
                            existing = [eid_value(x) for x in target.GetFilters()]
                            if eid_value(filter_id) not in existing:
                                target.AddFilter(filter_id)
                            target.SetFilterOverrides(filter_id, source_view.GetFilterOverrides(filter_id))
                            target.SetFilterVisibility(filter_id, source_view.GetFilterVisibility(filter_id))
                            try:
                                target.SetIsFilterEnabled(filter_id, source_view.GetIsFilterEnabled(filter_id))
                            except Exception:
                                pass
                            copied += 1
                        except Exception as ex:
                            filter_element = doc.GetElement(filter_id)
                            skipped.append(u'{0} / {1}: {2}'.format(
                                target.Name,
                                filter_element.Name if filter_element else eid_value(filter_id),
                                unicode(ex)
                            ))
        except Exception as ex:
            MessageBox.Show(unicode(ex), u'Copy Filters Error',
                            MessageBoxButtons.OK, MessageBoxIcon.Error)
            return

        message = u'Copied {0} filter settings to {1} views.'.format(copied, len(selected_views))
        if skipped:
            message += u'\n\nSkipped: {0}\n{1}'.format(len(skipped), u'\n'.join(skipped[:8]))
        MessageBox.Show(message, u'Copy Filters', MessageBoxButtons.OK,
                        MessageBoxIcon.Warning if skipped else MessageBoxIcon.Information)
        self.DialogResult = DialogResult.OK
        self.Close()


if doc.IsFamilyDocument:
    MessageBox.Show(u'Copy Filters does not run in a Family Document.', u'Copy Filters',
                    MessageBoxButtons.OK, MessageBoxIcon.Warning)
else:
    CopyFiltersForm().ShowDialog()
