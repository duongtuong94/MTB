# -*- coding: utf-8 -*-
"""Modal, responsive WinForms browser. Only filesystem discovery uses a worker."""
from __future__ import unicode_literals

import os
import threading
try:
    import Queue as queue
except ImportError:
    import queue

import clr
clr.AddReference('System.Windows.Forms')
clr.AddReference('System.Drawing')
from System.Drawing import Color, Size, ContentAlignment, Point
from System.Windows.Forms import (
    Form, Label, TextBox, ComboBox, ComboBoxStyle, CheckBox, ListBox,
    FlowLayoutPanel, DockStyle, Padding, RowStyle, ColumnStyle, SizeType,
    BorderStyle, PictureBox, PictureBoxSizeMode, Panel, TrackBar, TickStyle,
    FolderBrowserDialog, DialogResult, Timer, ToolTip, MessageBox,
    ContextMenuStrip, ToolStripMenuItem,
)
from bim_ui import configure_form, px, table, flow, button
from .service import (GROUPS, PAGE_SIZE, filter_rows, category_counts, page_rows,
                      iter_family_paths, path_key, action_for, placement_reason, expand_types)


class BrowserWindow(Form):
    def __init__(self, library, store):
        self.library, self.store = library, store
        self.source = 'Project'
        self.rows = []
        self.filtered = []
        self.page = 0
        self.pages = 1
        self.selected = None
        self.result = None
        self._changing = False
        self._scanning = False
        self._busy = False
        self._cancel = None
        self._queue = None
        self._folder = ''
        self._errors = []
        self._images = []
        self._cards = []
        self._preview_jobs = []
        self._preview_busy = False
        self._close_after_busy = False
        self._files_processed = 0
        self._category_data = []
        self._category = None
        self._source_states = {}
        self._project = []
        self._folder_rows = []
        self._disposed_ui = False
        configure_form(self, 'BIM Test | Family Browser (Preview)', 1120, 760)
        self.tip = ToolTip()
        root = table(rows=6)
        root.Padding = Padding(px(self, 8))
        root.ColumnStyles.Add(ColumnStyle(SizeType.Percent, 100))
        for percent in (False, False, True, False, False, False):
            root.RowStyles.Add(RowStyle(SizeType.Percent, 100) if percent else RowStyle(SizeType.AutoSize))
        self.Controls.Add(root)

        toolbar = flow(self)
        self.project_button = button(self, 'Project', self._project_clicked)
        self.folder_button = button(self, 'Folder...', self._folder_clicked)
        self.recursive = CheckBox(Text='Include subfolders', AutoSize=True, Checked=True)
        self.search = TextBox(Width=px(self, 240))
        self.search.Margin = Padding(px(self, 5))
        self.search.TextChanged += self._filter_changed
        self.cancel_scan = button(self, 'Cancel', self._cancel_clicked)
        self.cancel_scan.Visible = False
        self.search_label = Label(Text='Search:', AutoSize=True, Margin=Padding(px(self, 6)))
        self.options = ContextMenuStrip()
        subfolders = ToolStripMenuItem('Include subfolders', Checked=True, CheckOnClick=True)
        def toggle_subfolders(sender, args):
            self.recursive.Checked = sender.Checked
        subfolders.Click += toggle_subfolders
        self.options.Items.Add(subfolders)
        for text, value in (('Small thumbnails', 100), ('Medium thumbnails', 150), ('Large thumbnails', 190)):
            menu_item = ToolStripMenuItem(text)
            def change_size(sender, args, size=value):
                self.zoom.Value = size
            menu_item.Click += change_size
            self.options.Items.Add(menu_item)
        self.more = button(self, 'Options', lambda s, e: self.options.Show(self.more, Point(0, self.more.Height)))
        self.more.Visible = False
        for item in (self.project_button, self.folder_button, self.recursive,
                     self.search_label, self.search, self.more, self.cancel_scan):
            toolbar.Controls.Add(item)
        root.Controls.Add(toolbar, 0, 0)

        filters = flow(self)
        self.group = ComboBox(DropDownStyle=ComboBoxStyle.DropDownList, Width=px(self, 130))
        for name in GROUPS:
            self.group.Items.Add(name)
        self.group.SelectedIndex = 0
        self.group.SelectedIndexChanged += self._filter_changed
        self.scope = ComboBox(DropDownStyle=ComboBoxStyle.DropDownList, Width=px(self, 140))
        for name in ('All Families', 'Favorites', 'Recent'):
            self.scope.Items.Add(name)
        self.scope.SelectedIndex = 0
        self.scope.SelectedIndexChanged += self._filter_changed
        self.show_categories = CheckBox(Text='Categories', AutoSize=True, Checked=True)
        self.show_categories.CheckedChanged += self._toggle_categories
        self.zoom = TrackBar(Minimum=100, Maximum=190, Value=150, TickStyle=TickStyle.None,
                             Width=px(self, 100), Height=px(self, 28), AutoSize=False)
        self.zoom.ValueChanged += self._zoom_changed
        self.zoom_label = Label(Text='Thumbnail size:', AutoSize=True, Margin=Padding(px(self, 5)))
        for item in (self.group, self.scope, self.show_categories, self.zoom_label, self.zoom):
            item.Margin = Padding(px(self, 4))
            filters.Controls.Add(item)
        root.Controls.Add(filters, 0, 1)

        self.body = table(columns=2)
        self.body.ColumnStyles.Add(ColumnStyle(SizeType.Absolute, px(self, 190)))
        self.body.ColumnStyles.Add(ColumnStyle(SizeType.Percent, 100))
        self.body.RowStyles.Add(RowStyle(SizeType.Percent, 100))
        self.categories = ListBox(Dock=DockStyle.Fill, IntegralHeight=False, HorizontalScrollbar=True)
        self.categories.SelectedIndexChanged += self._category_changed
        self.grid = FlowLayoutPanel(Dock=DockStyle.Fill, AutoScroll=True, WrapContents=True,
                                    BackColor=Color.FromArgb(241, 244, 249))
        self.grid.SizeChanged += self._resize_cards
        self.body.Controls.Add(self.categories, 0, 0)
        self.body.Controls.Add(self.grid, 1, 0)
        root.Controls.Add(self.body, 0, 2)

        self.selection_label = Label(Text='Select a type card.', AutoSize=False,
                                     Dock=DockStyle.Fill, AutoEllipsis=True, Height=self.Font.Height + px(self, 10))
        root.Controls.Add(self.selection_label, 0, 3)
        self.favorite = button(self, 'Add to Favorites', self._favorite_clicked)
        self.favorite.Enabled = False

        footer = flow(self)
        self.previous = button(self, '<', lambda s, e: self._change_page(-1))
        self.next_page = button(self, '>', lambda s, e: self._change_page(1))
        self.action = button(self, 'Select a type', self._apply_clicked)
        self.action.Enabled = False
        self.errors_button = button(self, 'Indexing issues', self._show_errors)
        self.errors_button.Visible = False
        close = button(self, 'Close', lambda s, e: self.Close())
        self.CancelButton = close
        for item in (self.previous, self.next_page, self.action, self.favorite, self.errors_button, close):
            footer.Controls.Add(item)
        root.Controls.Add(footer, 0, 4)
        self.status = Label(Text='Reading project families...', AutoSize=False, Dock=DockStyle.Fill,
                            AutoEllipsis=True, Height=self.Font.Height + px(self, 10))
        root.Controls.Add(self.status, 0, 5)
        self.tip.SetToolTip(self.search, 'Search family names, type names and categories.')
        self.tip.SetToolTip(self.previous, 'Previous page')
        self.tip.SetToolTip(self.next_page, 'Next page')
        self.tip.SetToolTip(self.recursive, 'Applied the next time you choose Folder.')
        self.tip.SetToolTip(self.action, 'Loading adds the family even if you cancel placement afterwards.')
        self.timer = Timer(Interval=60)
        self.timer.Tick += self._index_tick
        self.preview_timer = Timer(Interval=50)
        self.preview_timer.Tick += self._preview_tick
        self.Shown += self._shown
        self.FormClosed += self._closed
        self.FormClosing += self._closing
        self.SizeChanged += self._adaptive_layout
        self._compact = False
        self._adaptive_layout()

    def _adaptive_layout(self, sender=None, args=None):
        compact = self.ClientSize.Width < px(self, 760)
        self.search_label.Visible = not compact
        self.zoom_label.Visible = self.zoom.Visible = not compact
        self.project_button.Visible = self.folder_button.Visible = not self._scanning
        self.recursive.Visible = not compact and not self._scanning
        self.more.Visible = compact and not self._scanning
        self.group.Width = px(self, 100 if compact else 130)
        self.scope.Width = px(self, 110 if compact else 140)
        preferred = lambda control: control.GetPreferredSize(Size(0, 0)).Width
        reserved = (preferred(self.cancel_scan) if self._scanning else
                    preferred(self.project_button) + preferred(self.folder_button) + preferred(self.more))
        self.search.Width = (max(px(self, 40), self.ClientSize.Width - reserved - px(self, 60))
                             if compact else px(self, 240))
        # At extreme scale, move selected-family information into the status
        # line/tooltip instead of reserving another full-height text row.
        self.selection_label.Visible = not compact
        self.status.Height = self.Font.Height + px(self, 2 if compact else 10)
        for item in (self.group, self.scope, self.show_categories):
            item.Margin = Padding(px(self, 2 if compact else 4))
        for item in (self.project_button, self.folder_button, self.more,
                     self.previous, self.next_page, self.action, self.favorite):
            item.Padding = Padding(px(self, 6), px(self, 2 if compact else 4),
                                   px(self, 6), px(self, 2 if compact else 4))
        if compact and not self._compact:
            self.show_categories.Checked = False
        self._compact = compact

    def _shown(self, sender, args):
        try:
            self._project = expand_types(self.library.project_rows())
            self.rows = self._project
            self._refresh()
        except Exception as error:
            MessageBox.Show(str(error), 'Family Browser')

    def _set_status(self, text):
        self.status.Text = text
        self.tip.SetToolTip(self.status, text)

    def _filter_changed(self, sender=None, args=None):
        if not self._changing:
            self.page = 0
            self._refresh()

    def _refresh(self):
        if self._changing:
            return
        self._changing = True
        try:
            common = dict(group=str(self.group.SelectedItem), search=self.search.Text,
                          scope=str(self.scope.SelectedItem), favorites=self.store.data['favorites'],
                          recent=self.store.data['recent'])
            base = filter_rows(self.rows, **common)
            counts = category_counts(base)
            available = [key for key, label, count in counts]
            if self._category not in available:
                self._category = None
            self.categories.BeginUpdate()
            try:
                self.categories.Items.Clear()
                self._category_data = [None] + available
                self.categories.Items.Add('All Categories ({0})'.format(len(base)))
                for key, label, count in counts:
                    self.categories.Items.Add('{0} ({1})'.format(label, count))
                self.categories.SelectedIndex = self._category_data.index(self._category)
            finally:
                self.categories.EndUpdate()
            self.filtered = filter_rows(base, category=self._category,
                                        scope=str(self.scope.SelectedItem),
                                        favorites=self.store.data['favorites'], recent=self.store.data['recent'])
        finally:
            self._changing = False
        self._render_page()

    def _category_changed(self, sender, args):
        if not self._changing and self.categories.SelectedIndex >= 0:
            self._category = self._category_data[self.categories.SelectedIndex]
            self.page = 0
            self._refresh()

    def _release_cards(self):
        self.preview_timer.Stop()
        self._preview_jobs = []
        self.grid.SuspendLayout()
        try:
            controls = list(self.grid.Controls)
            self.grid.Controls.Clear()
            for control in controls:
                control.Dispose()
            for image in self._images:
                image.Dispose()
            self._images = []
            self._cards = []
        finally:
            self.grid.ResumeLayout()

    def _render_page(self):
        self._release_cards()
        self.selected = None
        self._update_selection()
        rows, self.page, self.pages = page_rows(self.filtered, self.page)
        self.grid.SuspendLayout()
        try:
            for row in rows:
                card = table(rows=4)
                card.Dock = getattr(DockStyle, 'None')
                card.BorderStyle = BorderStyle.FixedSingle
                card.Margin = Padding(px(self, 5))
                card.Padding = Padding(px(self, 5))
                card.BackColor = Color.White
                card.Tag = row
                picture = PictureBox(Dock=DockStyle.Fill, SizeMode=PictureBoxSizeMode.Zoom,
                                     BackColor=Color.White)
                preview = Panel(Dock=DockStyle.Fill)
                placeholder = Label(Text='Loading preview...', Dock=DockStyle.Fill,
                                    TextAlign=ContentAlignment.MiddleCenter, ForeColor=Color.Gray)
                preview.Controls.Add(picture)
                preview.Controls.Add(placeholder)
                placeholder.BringToFront()
                self._preview_jobs.append((row, picture, placeholder))
                name = ('\u2605 ' if row['key'] in self.store.data['favorites'] else '') + row['name']
                labels = [Label(Text=name, Dock=DockStyle.Fill, AutoEllipsis=True),
                          Label(Text=row.get('type_name') or '(No named type)', Dock=DockStyle.Fill, AutoEllipsis=True),
                          Label(Text=row['category'], Dock=DockStyle.Fill, AutoEllipsis=True, ForeColor=Color.DimGray)]
                for index, child in enumerate([preview] + labels):
                    child.Tag = row
                    child.Click += self._card_clicked
                    self.tip.SetToolTip(child, row['name'] + '\n' + row.get('type_name', '') + '\n' + row['category'] +
                                        ('\n' + row['path'] if row.get('path') else ''))
                    card.Controls.Add(child, 0, index)
                    card.RowStyles.Add(RowStyle(SizeType.Absolute, 1))
                for child in (picture, placeholder):
                    child.Tag = row
                    child.Click += self._card_clicked
                card.ColumnStyles.Add(ColumnStyle(SizeType.Percent, 100))
                card.Click += self._card_clicked
                self._cards.append(card)
                self.grid.Controls.Add(card)
            if not rows:
                self.grid.Controls.Add(Label(Text='No families match. Change the source or filters.',
                                             AutoSize=True, Margin=Padding(px(self, 12))))
            self._resize_cards()
        finally:
            self.grid.ResumeLayout()
        self.previous.Enabled = self.page > 0
        self.next_page.Enabled = self.page + 1 < self.pages
        if self._preview_jobs:
            self.preview_timer.Start()
        if not self._scanning:
            self._set_status('{0} | {1} types | Page {2}/{3}{4}'.format(
                self.source, len(self.filtered), self.page + 1, self.pages,
                ' | ' + self._folder if self.source == 'Folder' else ''))

    def _preview_tick(self, sender=None, args=None):
        if self._preview_busy or self._busy or self._scanning:
            return
        if not self._preview_jobs:
            self.preview_timer.Stop()
            return
        self._preview_busy = True
        row, picture, placeholder = self._preview_jobs.pop(0)
        try:
            image = self.library.preview(row)
            if picture.IsDisposed:
                if image is not None:
                    image.Dispose()
                return
            if image is not None:
                self._images.append(image)
                picture.Image = image
                picture.BringToFront()
                placeholder.Visible = False
                # A saved image may depict another type. Do not silently present
                # it as the selected type's actual geometry.
                if row.get('preview_note', '').startswith('Saved FAMILY'):
                    placeholder.Text = 'Family preview'
                    placeholder.Dock = DockStyle.Bottom
                    placeholder.Height = self.Font.Height + px(self, 3)
                    placeholder.Visible = True
                    placeholder.BringToFront()
            else:
                placeholder.Text = 'Preview unavailable'
            note = row.get('preview_note', '')
            for child in (picture, placeholder):
                self.tip.SetToolTip(child, row['name'] + '\n' + row.get('type_name', '') + '\n' + note)
        except Exception as error:
            placeholder.Text = 'Preview unavailable'
            self.tip.SetToolTip(placeholder, str(error))
            if getattr(error, 'fatal', False):
                self._preview_jobs = []
                self.preview_timer.Stop()
                self._close_after_busy = True
                MessageBox.Show(str(error), 'Preview document cleanup failed')
        finally:
            self._preview_busy = False
            if self._close_after_busy:
                self.Close()

    def _resize_cards(self, sender=None, args=None):
        if not hasattr(self, 'zoom'):
            return
        width = max(px(self, 100), min(px(self, self.zoom.Value + 40),
                                      self.grid.ClientSize.Width - px(self, 30)))
        image_height = px(self, self.zoom.Value)
        heights = [image_height, self.Font.Height * 2 + px(self, 6),
                   self.Font.Height * 2 + px(self, 5), self.Font.Height + px(self, 5)]
        for card in self._cards:
            card.Size = Size(width, sum(heights) + px(self, 12))
            for index, height in enumerate(heights):
                card.RowStyles[index].Height = height

    def _zoom_changed(self, sender, args):
        self._resize_cards()

    def _toggle_categories(self, sender, args):
        self.categories.Visible = self.show_categories.Checked
        self.body.ColumnStyles[0].Width = px(self, 190) if self.show_categories.Checked else 0

    def _card_clicked(self, sender, args):
        self.selected = sender.Tag
        for card in self._cards:
            card.BackColor = Color.FromArgb(221, 237, 255) if card.Tag == self.selected else Color.White
        self._update_selection()

    def _update_selection(self):
        row = self.selected
        if row:
            reason = placement_reason(row)
            self.selection_label.Text = row['name'] + ' | ' + row.get('type_name', '') + (' | ' + reason if reason else '')
            self.tip.SetToolTip(self.selection_label, self.selection_label.Text)
            if self._compact:
                self._set_status(self.selection_label.Text)
        else:
            self.selection_label.Text = 'Select a type card.'
        text, enabled = action_for(row, self.source)
        self.action.Text = text
        self.action.Enabled = enabled and not self._scanning
        self.favorite.Enabled = row is not None
        self.favorite.Text = ('Unfavorite' if row and row['key'] in self.store.data['favorites'] else 'Favorite')

    def _favorite_clicked(self, sender, args):
        if self.selected:
            self.store.toggle_favorite(self.selected['key'])
            self.store.save()
            self._refresh()

    def _change_page(self, delta):
        self.page += delta
        self._render_page()

    def _switch_source(self, source):
        self._source_states[self.source] = (self.search.Text, self.group.SelectedIndex,
                                           self.scope.SelectedIndex, self._category, self.page)
        self.source = source
        state = self._source_states.get(source, ('', 0, 0, None, 0))
        self._changing = True
        self.search.Text, self.group.SelectedIndex, self.scope.SelectedIndex = state[:3]
        self._category, self.page = state[3:]
        self._changing = False

    def _project_clicked(self, sender, args):
        if self._scanning or self._preview_busy:
            return
        self._switch_source('Project')
        self.rows = self._project
        self._refresh()

    def _folder_clicked(self, sender, args):
        if self._scanning or self._preview_busy:
            return
        dialog = FolderBrowserDialog(Description='Choose an RFA library folder', ShowNewFolderButton=False)
        dialog.SelectedPath = self._folder or self.store.data.get('folder', '')
        try:
            if dialog.ShowDialog(self) != DialogResult.OK:
                return
            chosen = dialog.SelectedPath
        finally:
            dialog.Dispose()
        self._switch_source('Folder')
        self._folder = chosen
        self.store.data['folder'] = chosen
        self._errors = []
        self.errors_button.Visible = False
        self._folder_rows = []
        self._files_processed = 0
        self.rows = self._folder_rows
        self.page = 0
        self._scanning = True
        self._cancel = threading.Event()
        self._queue = queue.Queue(maxsize=128)
        self.project_button.Enabled = self.folder_button.Enabled = False
        self.cancel_scan.Visible = True
        self._adaptive_layout()
        self._refresh()
        self._set_status('Discovering RFA files... Cancel stops between files.')
        messages, cancel = self._queue, self._cancel
        recursive = self.recursive.Checked

        def discover():
            # Absolutely no Revit API, WinForms controls or cache mutations here.
            def send(item):
                while not cancel.is_set():
                    try:
                        messages.put(item, timeout=0.1)
                        return True
                    except queue.Full:
                        pass
                return False
            try:
                seen = set()
                for path in iter_family_paths(chosen, recursive):
                    key = path_key(path)
                    if cancel.is_set():
                        return
                    if key not in seen:
                        seen.add(key)
                        if not send(('file', path)):
                            return
            except Exception as error:
                send(('error', str(error)))
            finally:
                send(('done', None))
        worker = threading.Thread(target=discover)
        worker.daemon = True
        worker.start()
        self.timer.Start()

    def _index_tick(self, sender, args):
        if self._busy or self._preview_busy or not self._scanning:
            return
        self._busy = True
        try:
            try:
                kind, value = self._queue.get_nowait()
            except queue.Empty:
                return
            if kind == 'done':
                self._finish_scan(False)
                return
            if kind == 'error':
                self._errors.append(value)
                return
            self._files_processed += 1
            self._set_status('Indexing file {0}: {1} | Cancel stops after this file.'.format(self._files_processed, os.path.basename(value)))
            try:
                row = self.library.inspect_file(value)
                self.rows.extend(expand_types([row]))
            except Exception as error:
                self._errors.append('{0}\n{1}'.format(value, error))
                # A document cleanup failure is not safe to continue past.
                if getattr(error, 'fatal', False):
                    self._close_after_busy = True
                    MessageBox.Show(str(error), 'Indexing document cleanup failed')
                    return
            if self._files_processed % 20 == 0:
                self._refresh()
                self.store.save()
        finally:
            self._busy = False
            if self._close_after_busy:
                self.Close()

    def _cancel_clicked(self, sender, args):
        self._finish_scan(True)

    def _finish_scan(self, cancelled):
        self.timer.Stop()
        if self._cancel:
            self._cancel.set()
        self._scanning = False
        self.project_button.Enabled = self.folder_button.Enabled = True
        self.cancel_scan.Visible = False
        self._adaptive_layout()
        self.errors_button.Visible = bool(self._errors)
        self.store.save()
        self._refresh()
        self._set_status('{0} | {1} types indexed | {2} issues. {3}'.format(
            'Indexing cancelled' if cancelled else 'Folder ready', len(self.rows), len(self._errors),
            self.store.warning or 'Source RFA files were not saved.'))

    def _show_errors(self, sender, args):
        MessageBox.Show('\n\n'.join(self._errors[:20]) +
                        ('\n\nShowing the first 20 issues.' if len(self._errors) > 20 else ''), 'Indexing issues')

    def _apply_clicked(self, sender, args):
        if self._busy or self._preview_busy:
            self._set_status('Please wait for the current family preview to finish, then try again.')
            return
        if self.selected and self.action.Enabled:
            self.result = (self.selected, self.selected.get('type_name', ''))
            self.Close()

    def _closing(self, sender, args):
        if self._busy or self._preview_busy:
            args.Cancel = True
            self._close_after_busy = True
            if self._cancel:
                self._cancel.set()
            self._set_status('Closing after the current RFA operation has finished...')

    def _closed(self, sender, args):
        self.timer.Stop()
        self.timer.Dispose()
        self.preview_timer.Stop()
        if self._cancel:
            self._cancel.set()
        self.store.save()
        self._release_cards()
        self.preview_timer.Dispose()
        self.tip.Dispose()
        self.options.Dispose()
        self._disposed_ui = True
