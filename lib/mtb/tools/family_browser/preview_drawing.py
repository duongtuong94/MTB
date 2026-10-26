# -*- coding: utf-8 -*-
"""Bitmap helpers, independent of the Revit API. Geometry is supplied as points."""
from __future__ import unicode_literals

import clr
clr.AddReference('System.Drawing')
from System import Array
from System.Drawing import Bitmap, Graphics, Color, Pen, SolidBrush, PointF
from System.Drawing.Drawing2D import SmoothingMode, GraphicsPath, FillMode


def load_bitmap(path):
    original = Bitmap(path)
    try:
        return Bitmap(original)
    finally:
        original.Dispose()


def has_content(image):
    """Reject uniformly blank thumbnails before considering the next fallback."""
    if image is None or image.Width < 2 or image.Height < 2:
        return False
    values = set()
    for y in range(0, image.Height, max(1, image.Height // 64)):
        for x in range(0, image.Width, max(1, image.Width // 64)):
            color = image.GetPixel(x, y)
            if color.A > 20:
                values.add((color.R // 16, color.G // 16, color.B // 16))
                if len(values) >= 3:
                    return True
    return len(values) >= 2


def draw_geometry(paths, model=False, size=256):
    points = [p for path, fill in paths for p in path]
    if not points:
        return None
    spans = [max(p[i] for p in points) - min(p[i] for p in points) for i in range(3)]
    axes = sorted(range(3), key=lambda i: spans[i], reverse=True)[:2]
    axes.sort()
    def project(p):
        if model:
            return ((p[0] - p[1]) * 0.8660254, p[2] - (p[0] + p[1]) * 0.5)
        return p[axes[0]], p[axes[1]]
    flat = [project(p) for p in points]
    left, right = min(p[0] for p in flat), max(p[0] for p in flat)
    bottom, top = min(p[1] for p in flat), max(p[1] for p in flat)
    extent = max(right - left, top - bottom)
    if extent <= 1e-10:
        return None
    scale = (size - 30.0) / extent
    cx, cy = (left + right) / 2.0, (bottom + top) / 2.0
    def screen(point):
        x, y = project(point)
        return PointF(size / 2.0 + (x - cx) * scale, size / 2.0 - (y - cy) * scale)
    image = Bitmap(size, size)
    graphics = Graphics.FromImage(image)
    pen = Pen(Color.FromArgb(35, 45, 55), 1.4)
    brush = SolidBrush(Color.FromArgb(65, 75, 85))
    filled = GraphicsPath(FillMode.Alternate)
    try:
        graphics.Clear(Color.White)
        graphics.SmoothingMode = SmoothingMode.AntiAlias
        for path, fill in paths:
            if fill and len(path) >= 3:
                filled.AddPolygon(Array[PointF]([screen(p) for p in path]))
        graphics.FillPath(brush, filled)
        for path, fill in paths:
            if len(path) >= 2:
                graphics.DrawLines(pen, Array[PointF]([screen(p) for p in path]))
        return image
    except Exception:
        image.Dispose()
        raise
    finally:
        filled.Dispose()
        brush.Dispose()
        pen.Dispose()
        graphics.Dispose()
