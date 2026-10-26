# -*- coding: utf-8 -*-
"""Modal gallery; returns explicit actions to command.py, never writes the model."""
from __future__ import unicode_literals

import clr
clr.AddReference('System.Windows.Forms')
clr.AddReference('System.Drawing')
from System.Drawing import Color, Size, ContentAlignment
from System.Windows.Forms import (Form, Label, TextBox, ComboBox, ComboBoxStyle, FlowLayoutPanel,
                                 PictureBox, PictureBoxSizeMode, Panel, DockStyle, Padding, BorderStyle,
                                 RowStyle, ColumnStyle, SizeType, ToolTip, MessageBox)
from bim_ui import configure_form, table, flow, button, px
from .service import filter_rows, page_rows, duplicate_name, validate_name, DensePatternError
from .preview import render


class RegionWindow(Form):
    def __init__(self, rows, draw_reason, view_scale, ask_name, selected_id=None, state=None):
        self.rows, self.draw_reason, self.view_scale = rows, draw_reason, view_scale
        self.ask_name = ask_name
        self.result = None
        self.selected = None
        self.state = dict(state or {})
        self.page = self.state.get('page', 0)
        self.images, self.cards = [], []
        self._loading = True
        configure_form(self, 'BIM Test | Filled Region Browser (Preview)', 1060, 720)
        self.tip = ToolTip()
        root = table(rows=5)
        root.Padding = Padding(px(self, 8))
        root.ColumnStyles.Add(ColumnStyle(SizeType.Percent, 100))
        for grow in (False, True, False, False, False):
            root.RowStyles.Add(RowStyle(SizeType.Percent, 100) if grow else RowStyle(SizeType.AutoSize))
        self.Controls.Add(root)
        toolbar = flow(self)
        self.search_label = Label(Text='Search:', AutoSize=True, Margin=Padding(px(self, 6)))
        self.search = TextBox(Text=self.state.get('search', ''), Width=px(self, 240))
        self.scope = ComboBox(DropDownStyle=ComboBoxStyle.DropDownList, Width=px(self, 140))
        for value in ('All Types', 'Masking', 'Transparent'):
            self.scope.Items.Add(value)
        self.scope.SelectedIndex = self.state.get('scope', 0)
        self.zoom_label = Label(Text='Pattern zoom:', AutoSize=True, Margin=Padding(px(self, 6)))
        self.zoom = ComboBox(DropDownStyle=ComboBoxStyle.DropDownList, Width=px(self, 85))
        for value in ('50%', '100%', '200%', '400%'):
            self.zoom.Items.Add(value)
        self.zoom.SelectedIndex = self.state.get('zoom', 1)
        self.refresh = button(self, 'Refresh', lambda s, e: self._request('refresh'))
        for item in (self.search_label, self.search, self.scope, self.zoom_label, self.zoom, self.refresh):
            item.Margin = Padding(px(self, 4))
            toolbar.Controls.Add(item)
        root.Controls.Add(toolbar, 0, 0)
        self.grid = FlowLayoutPanel(Dock=DockStyle.Fill, AutoScroll=True, WrapContents=True,
                                    BackColor=Color.FromArgb(241, 244, 249))
        self.grid.SizeChanged += self._size_cards
        root.Controls.Add(self.grid, 0, 1)
        self.selection = Label(Text='Select a filled region type.', Dock=DockStyle.Fill,
                               AutoEllipsis=True, Height=self.Font.Height + px(self, 8))
        root.Controls.Add(self.selection, 0, 2)
        footer = flow(self)
        self.previous = button(self, '<', lambda s, e: self._page(-1))
        self.next = button(self, '>', lambda s, e: self._page(1))
        self.draw = button(self, 'Draw Region', lambda s, e: self._request('draw'))
        self.duplicate = button(self, 'Duplicate', self._duplicate)
        self.edit = button(self, 'Edit Type', lambda s, e: self._request('edit'))
        self.close_button = button(self, 'Close', lambda s, e: self.Close())
        self.CancelButton = self.close_button
        for item in (self.previous, self.next, self.draw, self.duplicate, self.edit, self.close_button):
            footer.Controls.Add(item)
        root.Controls.Add(footer, 0, 3)
        self.status = Label(Dock=DockStyle.Fill, AutoEllipsis=True, Height=self.Font.Height + px(self, 8))
        root.Controls.Add(self.status, 0, 4)
        self.tip.SetToolTip(self.edit, 'Native Revit Type Properties. Edits affect all regions of this type. Duplicate first for variants.')
        self.tip.SetToolTip(self.draw, draw_reason or 'Close this browser and draw the boundary in native Revit Sketch mode.')
        self.tip.SetToolTip(self.zoom, 'Illustrative swatches, not a model view export. Boundary styles are set in Revit Sketch.')
        self.search.TextChanged += self._filter_changed
        self.scope.SelectedIndexChanged += self._filter_changed
        self.zoom.SelectedIndexChanged += self._filter_changed
        self.SizeChanged += self._adaptive
        self.FormClosed += self._closed
        self._loading = False
        self._adaptive()
        self._render(selected_id)

    def _adaptive(self, sender=None, args=None):
        compact = self.ClientSize.Width < px(self, 760)
        self.search_label.Visible = self.zoom_label.Visible = not compact
        self.search.Width = min(px(self, 240), max(px(self, 70), self.ClientSize.Width // 3))
        self.scope.Width = px(self, 115 if compact else 140)
        self.selection.Visible = not compact
        for item in (self.previous, self.next, self.draw, self.duplicate, self.edit, self.close_button):
            item.Padding = Padding(px(self, 6), px(self, 2 if compact else 4), px(self, 6), px(self, 2 if compact else 4))
        self.status.Height = self.Font.Height + px(self, 2 if compact else 8)
        self._size_cards()

    def _save_state(self):
        self.state = dict(search=self.search.Text, scope=self.scope.SelectedIndex,
                          zoom=self.zoom.SelectedIndex, page=self.page)

    def _filter_changed(self, sender=None, args=None):
        if not self._loading:
            self.page = 0
            self._render()

    def _clear(self):
        self.grid.SuspendLayout()
        try:
            controls = list(self.grid.Controls)
            self.grid.Controls.Clear()
            for item in controls:
                item.Dispose()
            for image in self.images:
                image.Dispose()
            self.images, self.cards = [], []
        finally:
            self.grid.ResumeLayout()

    def _render(self, selected_id=None):
        filtered = filter_rows(self.rows, self.search.Text, str(self.scope.SelectedItem))
        if selected_id is not None:
            indexes = [i for i, row in enumerate(filtered) if row['id'] == selected_id]
            if indexes:
                from .service import PAGE_SIZE
                self.page = indexes[0] // PAGE_SIZE
        shown, self.page, pages = page_rows(filtered, self.page)
        self._clear()
        self.selected = None
        self.grid.SuspendLayout()
        try:
            for row in shown:
                card = table(rows=3)
                card.Dock = getattr(DockStyle, 'None')
                card.BackColor = Color.White
                card.BorderStyle = BorderStyle.FixedSingle
                card.Padding = Padding(px(self, 6))
                card.Margin = Padding(px(self, 5))
                card.ColumnStyles.Add(ColumnStyle(SizeType.Percent, 100))
                for unused in range(3):
                    card.RowStyles.Add(RowStyle(SizeType.Absolute, 1))
                try:
                    if row['error']:
                        raise ValueError(row['error'])
                    image = render(row, (0.5, 1.0, 2.0, 4.0)[self.zoom.SelectedIndex], self.view_scale)
                    self.images.append(image)
                    sample = PictureBox(Dock=DockStyle.Fill, SizeMode=PictureBoxSizeMode.Zoom, Image=image)
                    message = 'Foreground: {0}\nBackground: {1}\n{2}; pattern line weight: {3}\nPreview is illustrative; boundary style is set in Sketch.'.format(
                        row['foreground']['name'], row['background']['name'],
                        'Masking' if row['masking'] else 'Transparent', row['line_weight'])
                    if row.get('preview_fit', 1) > 1:
                        picture = sample
                        sample = Panel(Dock=DockStyle.Fill)
                        badge = Label(Text='Auto-fit x{0}'.format(row['preview_fit']), Dock=DockStyle.Bottom,
                                      Height=self.Font.Height + px(self, 4), TextAlign=ContentAlignment.MiddleCenter)
                        sample.Controls.Add(picture)
                        sample.Controls.Add(badge)
                        message += '\n' + row['preview_note']
                except Exception as error:
                    sample = Label(Text='Preview too dense' if isinstance(error, DensePatternError) else 'Preview unavailable',
                                   Dock=DockStyle.Fill, TextAlign=ContentAlignment.MiddleCenter, ForeColor=Color.Gray)
                    message = str(error)
                name = Label(Text=row['name'], Dock=DockStyle.Fill, AutoEllipsis=True)
                info = Label(Text='FG: {0}\nBG: {1}'.format(row['foreground']['name'], row['background']['name']),
                             Dock=DockStyle.Fill, AutoEllipsis=True, ForeColor=Color.DimGray)
                card.Tag = row
                card.Click += self._select
                card.DoubleClick += self._double_click
                for index, item in enumerate((sample, name, info)):
                    item.Tag = row
                    item.Click += self._select
                    item.DoubleClick += self._double_click
                    self.tip.SetToolTip(item, row['name'] + '\n' + message)
                    card.Controls.Add(item, 0, index)
                # Panel children do not bubble Click/DoubleClick to the card.
                for item in sample.Controls:
                    item.Tag = row
                    item.Click += self._select
                    item.DoubleClick += self._double_click
                    self.tip.SetToolTip(item, row['name'] + '\n' + message)
                self.grid.Controls.Add(card)
                self.cards.append(card)
                if row['id'] == selected_id:
                    self.selected = row
            if not shown:
                self.grid.Controls.Add(Label(Text='No filled region types match. Change the filters or click Refresh.',
                                             AutoSize=True, Margin=Padding(px(self, 10))))
            self._size_cards()
        finally:
            self.grid.ResumeLayout()
        self.previous.Enabled = self.page > 0
        self.next.Enabled = self.page + 1 < pages
        self._update_selection()
        self.status.Text = '{0} types | Page {1}/{2} | Illustrative swatches; Edit Type affects all instances.'.format(len(filtered), self.page + 1, pages)
        self.tip.SetToolTip(self.status, self.status.Text)

    def _size_cards(self, sender=None, args=None):
        if not hasattr(self, 'grid'):
            return
        width = max(px(self, 100), min(px(self, 215), self.grid.ClientSize.Width - px(self, 28)))
        heights = (px(self, 145), self.Font.Height * 2 + px(self, 8), self.Font.Height * 2 + px(self, 8))
        for card in self.cards:
            card.Size = Size(width, sum(heights) + px(self, 14))
            for index, height in enumerate(heights):
                card.RowStyles[index].Height = height

    def _select(self, sender, args):
        self.selected = sender.Tag
        self._update_selection()

    def _update_selection(self):
        for card in self.cards:
            card.BackColor = Color.FromArgb(221, 237, 255) if card.Tag == self.selected else Color.White
        self.draw.Enabled = self.selected is not None and not self.draw_reason
        self.duplicate.Enabled = self.selected is not None and self.selected['can_duplicate']
        self.edit.Enabled = self.selected is not None
        self.selection.Text = (self.selected['name'] + ' | Edit Type changes all regions using this type.'
                               if self.selected else 'Select a filled region type.')
        self.tip.SetToolTip(self.selection, self.selection.Text)

    def _double_click(self, sender, args):
        self.selected = sender.Tag
        self._request('edit')

    def _duplicate(self, sender, args):
        if self.selected is None:
            return
        names = [row['name'] for row in self.rows]
        proposed = duplicate_name(self.selected['name'], names)
        while True:
            value = self.ask_name(proposed)
            if value is None:
                return
            try:
                name = validate_name(value, names)
                self._request('duplicate', name)
                return
            except ValueError as error:
                MessageBox.Show(str(error), 'Duplicate Filled Region Type')
                proposed = value

    def _page(self, delta):
        self.page += delta
        self._render()

    def _request(self, action, name=None):
        if action != 'refresh' and self.selected is None:
            return
        if action == 'draw' and self.draw_reason:
            return
        self._save_state()
        self.result = (action, self.selected['id'] if self.selected else None, name)
        self.Close()

    def _closed(self, sender, args):
        self._clear()
        self.tip.Dispose()
