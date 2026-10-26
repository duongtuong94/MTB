# -*- coding: utf-8 -*-
"""Pure filtering, naming and hatch geometry. No Revit/.NET/UI imports."""
from __future__ import unicode_literals

import math

PAGE_SIZE = 32
DRAW_VIEWS = ('FloorPlan', 'CeilingPlan', 'EngineeringPlan', 'AreaPlan', 'Section',
              'Elevation', 'Detail', 'DraftingView', 'Legend')


class DensePatternError(ValueError):
    pass


def filter_rows(rows, search='', scope='All Types'):
    words = search.lower().split()
    result = []
    for row in rows:
        if scope == 'Masking' and not row['masking']:
            continue
        if scope == 'Transparent' and row['masking']:
            continue
        text = ' '.join((row['name'], row['foreground']['name'], row['background']['name'])).lower()
        if all(word in text for word in words):
            result.append(row)
    return sorted(result, key=lambda item: (item['name'].lower(), item['id']))


def validate_name(name, existing):
    name = name.strip()
    if not name:
        raise ValueError('Enter a name for the new type.')
    if any(ord(char) < 32 for char in name):
        raise ValueError('The name cannot contain control characters.')
    if name.lower() in set(value.lower() for value in existing):
        raise ValueError('A filled region type with this name already exists.')
    return name


def duplicate_name(original, existing):
    names = set(name.lower() for name in existing)
    base, index = original + ' Copy', 1
    result = base
    while result.lower() in names:
        index += 1
        result = base + ' ' + str(index)
    return result


def page_rows(rows, page):
    pages = max(1, (len(rows) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    return rows[page * PAGE_SIZE:(page + 1) * PAGE_SIZE], page, pages


def draw_view_reason(view_type, template=False):
    if template or view_type not in DRAW_VIEWS:
        return 'Open a plan, section, elevation, detail, drafting or legend view to draw a region.'
    return ''


def _line_interval(origin, direction, width, height):
    low, high = -float('inf'), float('inf')
    for coordinate, delta, bound in zip(origin, direction, (width, height)):
        if abs(delta) < 1e-12:
            if coordinate < 0 or coordinate > bound:
                return None
        else:
            a, b = -coordinate / delta, (bound - coordinate) / delta
            low, high = max(low, min(a, b)), min(high, max(a, b))
    return (low, high) if low <= high else None


def normalized_segments(values, encoding='signed'):
    """Convert Revit's unsigned alternating dash/gap list to signed PAT runs.

    PAT text is already signed. Some API data retains those signs; preserve it.
    Nonnegative GetSegments arrays follow dash/gap order (as used by Autodesk's
    viewer with Pen.DashPattern), not 'draw every positive entry'. Never infer
    this convention for a PAT/source list that lacks the explicit API marker.
    """
    values = list(values)
    if encoding != 'revit' or not values or any(value < 0 for value in values):
        return values
    if len(values) % 2:
        values = values + values
    return [value if index % 2 == 0 else -value for index, value in enumerate(values)]


def hatch_segments(grids, width, height, pixels_per_foot, limit=6000):
    """Clip PAT-style grids including signed dash/gap/dot runs and line shifts.

    Inputs use Revit internal feet/radians. Output uses bitmap coordinates.
    Dense/degenerate grids fail explicitly instead of freezing the dialog.
    """
    w, h = width / float(pixels_per_foot), height / float(pixels_per_foot)
    strokes = []
    for grid in grids:
        angle, offset = grid['angle'], grid['offset']
        if abs(offset) < 1e-10:
            raise DensePatternError('Pattern spacing is too small for this preview.')
        u = (math.cos(angle), math.sin(angle))
        v = (-u[1], u[0])
        origin, shift = grid['origin'], grid['shift']
        distances = [((x - origin[0]) * v[0] + (y - origin[1]) * v[1]) / offset
                     for x, y in ((0, 0), (w, 0), (0, h), (w, h))]
        first, last = int(math.ceil(min(distances))) - 1, int(math.floor(max(distances))) + 1
        if last - first > 2000:
            raise DensePatternError('Dense pattern: increase Pattern Zoom.')
        segments = normalized_segments(grid.get('segments', []), grid.get('segment_encoding', 'signed'))
        period = sum(abs(s) for s in segments)
        if segments and period < 1e-10:
            raise DensePatternError('Pattern dash cycle is too small for this preview.')
        for index in range(first, last + 1):
            base = (origin[0] + index * (offset * v[0] + shift * u[0]),
                    origin[1] + index * (offset * v[1] + shift * u[1]))
            interval = _line_interval(base, u, w, h)
            if interval is None:
                continue
            low, high = interval
            runs = []
            if not segments:
                runs.append((low, high))
            else:
                cycles = int(math.ceil((high - low) / period)) + 2
                if cycles * len(segments) > limit:
                    raise DensePatternError('Dense dashed pattern: increase Pattern Zoom.')
                first_position = math.floor(low / period) * period
                for cycle in range(cycles + 1):
                    position = first_position + cycle * period
                    if position > high:
                        break
                    cursor = position
                    for length in segments:
                        if length >= 0 and cursor <= high and cursor + length >= low:
                            runs.append((max(cursor, low), min(cursor + length, high)))
                        cursor += abs(length)
            for start, end in runs:
                if len(strokes) >= limit:
                    raise DensePatternError('Dense pattern: increase Pattern Zoom.')
                strokes.append(((base[0] + start * u[0]) * pixels_per_foot,
                                height - (base[1] + start * u[1]) * pixels_per_foot,
                                (base[0] + end * u[0]) * pixels_per_foot,
                                height - (base[1] + end * u[1]) * pixels_per_foot))
    return strokes


def swatch_plan(row, zoom=1.0, view_scale=50, size=256, max_attempts=9):
    """Plan both layers at one shared scale; auto-fit dense swatches as a whole.

    The original grids/dashes/colors are never changed or selectively dropped.
    Each attempt is bounded by hatch_segments. No partial/one-layer bitmap is
    returned when another layer exceeds its budget.
    """
    foreground = row['foreground']
    layers = ([foreground] if foreground['solid'] and not foreground['none'] else
              (row['background'], foreground))
    if zoom <= 0 or max_attempts < 1:
        raise ValueError('Preview zoom and attempt count must be positive.')
    last_error = None
    for attempt in range(max_attempts):
        factor = 2 ** attempt
        plans = []
        try:
            for layer in layers:
                if layer['none']:
                    continue
                strokes = []
                if not layer['solid']:
                    ppf = 1152.0 * zoom * factor
                    if layer['target'] == 'Model':
                        ppf /= max(1, view_scale)
                    strokes = hatch_segments(layer['grids'], size, size, ppf)
                plans.append((layer, strokes))
            return plans, factor
        except DensePatternError as error:
            last_error = error
    raise DensePatternError('Pattern exceeds the bounded preview budget even after auto-fit. {0}'.format(last_error))
