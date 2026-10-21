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


doc = revit.doc
uidoc = revit.uidoc
source_view = doc.ActiveView


class CopyFiltersForm(Form):
    def __init__(self):
        Form.__init__(self)
        self.Text = u'Copy Filters'
        self.ClientSize = Size(587, 471)
        self.FormBorderStyle = FormBorderStyle.FixedDialog
        self.StartPosition = FormStartPosition.CenterScreen
        self.MaximizeBox = False
        self.MinimizeBox = False
        self.ShowIcon = False

        self.filter_ids = []
        self.all_views = []
        self.open_views = []
        self.current_views = []

        self.filters_list = CheckedListBox()
        self.filters_list.CheckOnClick = True
        self.filters_list.Location = Point(14, 24)
        self.filters_list.Size = Size(260, 326)

        self.views_list = CheckedListBox()
        self.views_list.CheckOnClick = True
        self.views_list.Location = Point(316, 24)
        self.views_list.Size = Size(260, 326)

        label_filters = Label()
        label_filters.Text = u'Select Filters to Copy'
        label_filters.AutoSize = True
        label_filters.Location = Point(86, 8)

        label_views = Label()
        label_views.Text = u'Copy Filters to Selected Views'
        label_views.AutoSize = True
        label_views.Location = Point(365, 8)

        arrow = Label()
        arrow.Text = u'⇒'
        arrow.Font = Font('Segoe UI Symbol', 18, FontStyle.Bold)
        arrow.AutoSize = True
        arrow.Location = Point(280, 180)

        self.copy_button = Button()
        self.copy_button.Text = u'Copy'
        self.copy_button.BackColor = SystemColors.ActiveCaption
        self.copy_button.Font = Font('Segoe UI', 9, FontStyle.Bold)
        self.copy_button.Location = Point(195, 361)
        self.copy_button.Size = Size(79, 25)
        self.copy_button.Click += self.copy_click

        filter_all = Button()
        filter_all.Text = u'Check All'
        filter_all.Location = Point(12, 361)
        filter_all.Size = Size(93, 23)
        filter_all.Click += lambda s, e: self.set_all(self.filters_list, True)

        filter_none = Button()
        filter_none.Text = u'Uncheck All'
        filter_none.Location = Point(12, 390)
        filter_none.Size = Size(93, 23)
        filter_none.Click += lambda s, e: self.set_all(self.filters_list, False)

        view_all = Button()
        view_all.Text = u'Check All'
        view_all.Location = Point(316, 361)
        view_all.Size = Size(93, 23)
        view_all.Click += lambda s, e: self.set_all(self.views_list, True)

        view_none = Button()
        view_none.Text = u'Uncheck All'
        view_none.Location = Point(316, 390)
        view_none.Size = Size(93, 23)
        view_none.Click += lambda s, e: self.set_all(self.views_list, False)

        view_group = GroupBox()
        view_group.Text = u'Views'
        view_group.Location = Point(429, 356)
        view_group.Size = Size(146, 61)

        self.open_radio = RadioButton()
        self.open_radio.Text = u'Active Views'
        self.open_radio.Location = Point(6, 18)
        self.open_radio.AutoSize = True
        self.open_radio.CheckedChanged += self.view_scope_changed

        self.all_radio = RadioButton()
        self.all_radio.Text = u'All Views'
        self.all_radio.Location = Point(6, 40)
        self.all_radio.AutoSize = True
        self.all_radio.Checked = True
        self.all_radio.CheckedChanged += self.view_scope_changed

        view_group.Controls.Add(self.open_radio)
        view_group.Controls.Add(self.all_radio)

        close_button = Button()
        close_button.Text = u'Close'
        close_button.Location = Point(501, 437)
        close_button.Size = Size(75, 23)
        close_button.Click += lambda s, e: self.Close()
        self.CancelButton = close_button

        self.status = Label()
        self.status.AutoSize = False
        self.status.Location = Point(12, 428)
        self.status.Size = Size(470, 34)
        self.status.Text = u'Source: {0}'.format(source_view.Name)

        for control in (
            self.filters_list, self.views_list, label_filters, label_views, arrow,
            self.copy_button, filter_all, filter_none, view_all, view_none,
            view_group, close_button, self.status
        ):
            self.Controls.Add(control)

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
