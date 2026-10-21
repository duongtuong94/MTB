# -*- coding: utf-8 -*-
"""Runtime-measured WinForms layout shared by BIM Test dialogs.

All design distances are converted to the current window DPI once. Since these
forms are built at runtime, AutoScaleDimensions must describe that same DPI,
not the designer's default font/DPI. Controls then use preferred sizes and dock
layout; WinForms can scale them again when the host supports a DPI transition.
"""
from __future__ import unicode_literals

import clr
clr.AddReference('System.Windows.Forms')
clr.AddReference('System.Drawing')
from System.Drawing import Font, Size, SizeF, Point
from System.Windows.Forms import (
    AutoScaleMode, FormBorderStyle, FormStartPosition, Screen, Padding,
    TableLayoutPanel, ColumnStyle, RowStyle, SizeType, DockStyle,
    FlowLayoutPanel, FlowDirection, AutoSizeMode, Panel, Label, Button,
)


def dpi_scale(control):
    graphics = control.CreateGraphics()
    try:
        return float(graphics.DpiX) / 96.0
    finally:
        graphics.Dispose()


def px(control, value):
    return max(1, int(round(value * dpi_scale(control))))


def configure_form(form, title, width, height):
    form.Text = title
    form.Font = Font('Segoe UI', 9.0)
    form.FormBorderStyle = FormBorderStyle.Sizable
    form.MaximizeBox = True
    form.MinimizeBox = False
    form.ShowIcon = False
    form.StartPosition = FormStartPosition.Manual
    # Choose Revit's monitor before creating this dialog's window handle.
    try:
        from pyrevit import HOST_APP
        screen = Screen.FromHandle(HOST_APP.uiapp.MainWindowHandle)
    except Exception:
        screen = Screen.FromPoint(SystemCursorPosition())
    area = screen.WorkingArea
    form.Location = Point(area.Left + 20, area.Top + 20)
    scale = dpi_scale(form)
    form.AutoScaleDimensions = SizeF(96.0 * scale, 96.0 * scale)
    form.AutoScaleMode = AutoScaleMode.Dpi
    form.ClientSize = Size(px(form, width), px(form, height))
    form.MinimumSize = Size(min(px(form, 400), area.Width),
                            min(px(form, 300), area.Height))

    def fit(sender=None, args=None):
        current = Screen.FromHandle(form.Handle).WorkingArea
        margin = px(form, 8)
        max_width = max(1, current.Width - 2 * margin)
        max_height = max(1, current.Height - 2 * margin)
        form.MinimumSize = Size(min(px(form, 400), max_width),
                                min(px(form, 300), max_height))
        form.Size = Size(min(form.Width, max_width), min(form.Height, max_height))
        form.Location = Point(max(current.Left, min(form.Left, current.Right - form.Width)),
                              max(current.Top, min(form.Top, current.Bottom - form.Height)))
    fit()
    form.Location = Point(area.Left + max(0, (area.Width - form.Width) // 2),
                          area.Top + max(0, (area.Height - form.Height) // 2))
    form.Shown += fit
    try:
        form.DpiChanged += fit
    except AttributeError:
        pass


def SystemCursorPosition():
    from System.Windows.Forms import Cursor
    return Cursor.Position


def table(columns=1, rows=1, autosize=False):
    result = TableLayoutPanel(Dock=DockStyle.Fill, ColumnCount=columns, RowCount=rows)
    result.Margin = Padding(0)
    result.AutoSize = autosize
    result.AutoSizeMode = AutoSizeMode.GrowAndShrink
    return result


def flow(control, vertical=False):
    result = FlowLayoutPanel(AutoSize=True, WrapContents=not vertical)
    result.AutoSizeMode = AutoSizeMode.GrowAndShrink
    result.Dock = DockStyle.Top
    result.Margin = Padding(0)
    result.Padding = Padding(0)
    result.FlowDirection = FlowDirection.TopDown if vertical else FlowDirection.LeftToRight
    return result


def section(control, title, child, fill=False):
    """A separate measured heading row avoids GroupBox text/content overlap."""
    result = table(rows=2, autosize=not fill)
    result.ColumnStyles.Add(ColumnStyle(SizeType.Percent, 100.0))
    result.RowStyles.Add(RowStyle(SizeType.AutoSize))
    result.RowStyles.Add(RowStyle(SizeType.Percent, 100.0) if fill else RowStyle(SizeType.AutoSize))
    result.Padding = Padding(px(control, 4))
    result.Margin = Padding(px(control, 3))
    heading = Label(Text=title, AutoSize=True)
    heading.Margin = Padding(0, 0, 0, px(control, 5))
    heading.Dock = DockStyle.Top
    result.Controls.Add(heading, 0, 0)
    result.Controls.Add(child, 0, 1)
    return result


def button(control, text, handler=None):
    result = Button(Text=text, AutoSize=True)
    result.AutoSizeMode = AutoSizeMode.GrowAndShrink
    result.Padding = Padding(px(control, 8), px(control, 4), px(control, 8), px(control, 4))
    result.Margin = Padding(px(control, 3))
    if handler is not None:
        result.Click += handler
    return result


def viewport(control, content, width, height):
    """Scroll only the content; the parent can keep its footer visible."""
    host = Panel(Dock=DockStyle.Fill, AutoScroll=True)
    host.Margin = Padding(0)
    content.Dock = getattr(DockStyle, 'None')
    host.Controls.Add(content)
    busy = [False]

    def layout(sender=None, args=None):
        if busy[0]:
            return
        busy[0] = True
        try:
            # Screen-space coordinates must account for the current scroll offset.
            content.Location = host.AutoScrollPosition
            content.Size = Size(max(px(control, width), host.ClientSize.Width - px(control, 20)),
                                max(px(control, height), host.ClientSize.Height - px(control, 20)))
            host.AutoScrollMinSize = content.Size
        finally:
            busy[0] = False
    host.SizeChanged += layout
    host.Scroll += layout
    control.Shown += layout
    return host
