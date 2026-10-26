# -*- coding: utf-8 -*-
"""Illustrative two-layer swatches. Never creates Revit elements/views."""
from __future__ import unicode_literals

import clr
clr.AddReference('System.Drawing')
from System.Drawing import Bitmap, Graphics, Color, Pen, SolidBrush
from System.Drawing.Drawing2D import SmoothingMode
from .service import swatch_plan


def render(row, zoom=1.0, view_scale=50, size=256):
    # Plan before allocating graphics resources, so failed density attempts do
    # not draw partial layers or allocate a new bitmap on every retry.
    plans, factor = swatch_plan(row, zoom, view_scale, size)
    row['preview_fit'] = factor
    row['preview_note'] = ('Auto-fit x{0}: requested zoom {1:g}%, effective zoom {2:g}%. Pattern definition unchanged.'.format(
        factor, zoom * 100, zoom * factor * 100) if factor > 1 else '')
    image = Bitmap(size, size)
    graphics = Graphics.FromImage(image)
    border = Pen(Color.FromArgb(160, 170, 185), 1.0)
    try:
        graphics.SmoothingMode = SmoothingMode.AntiAlias
        graphics.Clear(Color.White)
        # Light checkerboard makes transparent vs masking region distinguishable.
        if not row['masking']:
            brush = SolidBrush(Color.FromArgb(241, 244, 247))
            try:
                for x in range(0, size, 16):
                    for y in range(0, size, 16):
                        if (x // 16 + y // 16) % 2 == 0:
                            graphics.FillRectangle(brush, x, y, 16, 16)
            finally:
                brush.Dispose()
        for layer, strokes in plans:
            color = Color.FromArgb(*layer['color'])
            brush = SolidBrush(color)
            pen = Pen(color, max(0.7, min(3.0, row['line_weight'] * 0.25)))
            try:
                if layer['solid']:
                    graphics.FillRectangle(brush, 0, 0, size, size)
                else:
                    for x1, y1, x2, y2 in strokes:
                        if abs(x2 - x1) + abs(y2 - y1) < 0.1:
                            graphics.FillEllipse(brush, float(x1 - 0.7), float(y1 - 0.7), 1.4, 1.4)
                        else:
                            graphics.DrawLine(pen, float(x1), float(y1), float(x2), float(y2))
            finally:
                pen.Dispose()
                brush.Dispose()
        graphics.DrawRectangle(border, 0, 0, size - 1, size - 1)
        return image
    except Exception:
        image.Dispose()
        raise
    finally:
        border.Dispose()
        graphics.Dispose()
