# -*- coding: utf-8 -*-
"""Pure 2D contour analysis for Opening marks (Revit internal length units).

Each edge provides sampled points and a linear flag. No assumption is made
about edge order or direction. Ambiguous/touching boundaries are not guessed.
"""
from __future__ import division

import math


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def on_segment(p, a, b, tolerance):
    length = distance(a, b)
    if length <= tolerance:
        return distance(p, a) <= tolerance
    return (abs(cross(a, b, p)) <= tolerance * length and
            min(a[0], b[0]) - tolerance <= p[0] <= max(a[0], b[0]) + tolerance and
            min(a[1], b[1]) - tolerance <= p[1] <= max(a[1], b[1]) + tolerance)


def intersects(a, b, c, d, tolerance):
    if any((on_segment(c, a, b, tolerance), on_segment(d, a, b, tolerance),
            on_segment(a, c, d, tolerance), on_segment(b, c, d, tolerance))):
        return True
    return ((cross(a, b, c) > 0) != (cross(a, b, d) > 0) and
            (cross(c, d, a) > 0) != (cross(c, d, b) > 0))


def sides(polygon):
    return list(zip(polygon, polygon[1:] + polygon[:1]))


def inside(point, polygon):
    result = False
    for a, b in sides(polygon):
        if (a[1] > point[1]) != (b[1] > point[1]):
            x = a[0] + (point[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if point[0] < x:
                result = not result
    return result


def contour_loops(edges, tolerance):
    """Return ordered loops and component errors, retaining independent good loops."""
    endpoints, valid = [], []
    errors = []
    for edge in edges:
        points = list(edge['points'])
        if len(points) < 2 or any(math.isnan(v) or math.isinf(v) for p in points for v in p):
            errors.append('invalid_edge')
            continue
        if edge.get('closed') and distance(points[0], points[-1]) > tolerance:
            points.append(points[0])
        valid.append({'points': points, 'linear': edge.get('linear', False)})
        endpoints.extend((points[0], points[-1]))
    parents = list(range(len(endpoints)))

    def find(node):
        while parents[node] != node:
            parents[node] = parents[parents[node]]
            node = parents[node]
        return node

    for i, point in enumerate(endpoints):
        for j in range(i):
            if distance(point, endpoints[j]) <= tolerance:
                parents[find(i)] = find(j)
    adjacency, nodes = {}, []
    for i in range(len(valid)):
        pair = (find(2 * i), find(2 * i + 1))
        nodes.append(pair)
        for node in pair:
            adjacency.setdefault(node, []).append(i)
    pending = set(range(len(valid)))
    loops = []
    while pending:
        first = min(pending)
        component, stack = set(), [first]
        while stack:
            edge_id = stack.pop()
            if edge_id in component:
                continue
            component.add(edge_id)
            for node in nodes[edge_id]:
                stack.extend(x for x in adjacency[node] if x not in component)
        pending.difference_update(component)
        if any(len(adjacency[node]) != 2 for i in component for node in nodes[i]):
            errors.append('open_or_branched')
            continue
        polygon, vertices, used = [], [], set()
        current = nodes[first][0]
        while len(used) < len(component):
            edge_id = next(i for i in adjacency[current] if i not in used)
            used.add(edge_id)
            edge = valid[edge_id]
            points = edge['points']
            if nodes[edge_id][0] != current:
                points = list(reversed(points))
            vertices.append(points[0])
            polygon.extend(points[:-1])
            current = nodes[edge_id][1] if nodes[edge_id][0] == current else nodes[edge_id][0]
        cleaned = []
        for point in polygon:
            if not cleaned or distance(cleaned[-1], point) > tolerance:
                cleaned.append(point)
        if len(cleaned) > 1 and distance(cleaned[0], cleaned[-1]) <= tolerance:
            cleaned.pop()
        if len(cleaned) < 3:
            errors.append('degenerate')
            continue
        segments = sides(cleaned)
        bad = any(intersects(a, b, c, d, tolerance)
                  for i, (a, b) in enumerate(segments)
                  for j, (c, d) in enumerate(segments)
                  if j > i + 1 and not (i == 0 and j == len(segments) - 1))
        area = abs(sum(cross(cleaned[0], a, b) for a, b in segments)) / 2.0
        if bad or area <= tolerance * tolerance:
            errors.append('self_intersection_or_zero_area')
            continue
        loops.append({'polygon': cleaned, 'vertices': vertices,
                      'quad': len(component) == 4 and all(valid[i]['linear'] for i in component)})
    return loops, errors


def opening_marks(edges, tolerance=1e-6, minimum_length=1e-4):
    """Return marks, solid-island count and reasons for skipped boundaries.

    Nested solid islands are not marked. A surrounding opening with an island
    is skipped rather than drawing diagonals across the solid material.
    """
    loops, errors = contour_loops(edges, tolerance)
    invalid = set()
    for i, loop in enumerate(loops):
        for j in range(i):
            if any(intersects(a, b, c, d, tolerance)
                   for a, b in sides(loop['polygon']) for c, d in sides(loops[j]['polygon'])):
                invalid.update((i, j))
    errors.extend('touching_or_crossing_loops' for i in sorted(invalid))
    marks, islands = [], 0
    for i, loop in enumerate(loops):
        if i in invalid:
            continue
        containers = [j for j, other in enumerate(loops)
                      if j != i and inside(loop['polygon'][0], other['polygon'])]
        # An invalid surrounding contour makes the void/solid classification ambiguous.
        if any(j in invalid for j in containers):
            errors.append('ambiguous_nesting')
            continue
        if len(containers) % 2:
            islands += 1
            continue
        if any(j != i and inside(other['polygon'][0], loop['polygon'])
               for j, other in enumerate(loops)):
            errors.append('opening_contains_solid_island')
            continue
        if loop['quad']:
            a, b, c, d = loop['vertices']
        else:
            xs = [p[0] for p in loop['polygon']]
            ys = [p[1] for p in loop['polygon']]
            a, c = (min(xs), min(ys)), (max(xs), max(ys))
            b, d = (min(xs), max(ys)), (max(xs), min(ys))
        diagonals = [(a, c), (b, d)]
        if any(distance(p, q) <= minimum_length for p, q in diagonals):
            errors.append('too_small')
            continue
        marks.append(diagonals)
    return {'marks': marks, 'islands': islands, 'errors': errors}
