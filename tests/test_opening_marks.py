import ast
import math
import os
import random
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from opening_marks import opening_marks


def polygon(points):
    return [{'points': [a, b], 'linear': True}
            for a, b in zip(points, points[1:] + points[:1])]


def square(x=0, y=0, size=2):
    return polygon([(x, y), (x + size, y), (x + size, y + size), (x, y + size)])


def scrambled(edges):
    result = []
    for i, edge in enumerate(edges):
        result.append(dict(edge, points=list(reversed(edge['points'])) if i % 2 else edge['points']))
    random.Random(42).shuffle(result)
    return result


class ContourTests(unittest.TestCase):
    def test_single_rectangle(self):
        result = opening_marks(square())
        self.assertEqual(1, len(result['marks']))
        self.assertFalse(result['errors'])
        for a, b in result['marks'][0]:
            self.assertAlmostEqual(math.sqrt(8), math.dist(a, b))

    def test_three_disconnected_holes_in_one_opening(self):
        result = opening_marks(scrambled(square() + square(5) + square(10)))
        self.assertEqual(3, len(result['marks']))
        self.assertFalse(result['errors'])
        for mark in result['marks']:
            # No diagonal may span the space between independent holes.
            for a, b in mark:
                self.assertAlmostEqual(math.sqrt(8), math.dist(a, b))

    def test_rotated_trapezoid_joins_actual_opposite_corners(self):
        vertices = [(2, 0), (4, 2), (1, 4), (0, 1)]
        result = opening_marks(scrambled(polygon(vertices)))
        expected = {frozenset((vertices[0], vertices[2])), frozenset((vertices[1], vertices[3]))}
        self.assertEqual(expected, {frozenset(pair) for pair in result['marks'][0]})

    def test_circle_single_closed_curve(self):
        points = [(math.cos(i * math.pi / 16), math.sin(i * math.pi / 16)) for i in range(33)]
        result = opening_marks([{'points': points, 'closed': True}])
        self.assertEqual(1, len(result['marks']))
        self.assertFalse(result['errors'])

    def test_two_circles_each_get_own_bbox(self):
        edges = []
        for x in (0, 10):
            points = [(x + math.cos(i * math.pi / 8), math.sin(i * math.pi / 8)) for i in range(16)]
            edges.append({'points': points, 'closed': True})
        result = opening_marks(edges)
        self.assertEqual(2, len(result['marks']))
        self.assertTrue(all(math.dist(a, b) < 3 for mark in result['marks'] for a, b in mark))

    def test_two_arcs_make_one_loop(self):
        points = [(math.cos(i * math.pi / 8), math.sin(i * math.pi / 8)) for i in range(17)]
        result = opening_marks(scrambled([{'points': points[:9]}, {'points': points[8:]}]))
        self.assertEqual(1, len(result['marks']))

    def test_endpoint_tolerance(self):
        edges = square()
        edges[0]['points'][0] = (0.0000001, 0)
        result = opening_marks(scrambled(edges), tolerance=1e-6)
        self.assertEqual(1, len(result['marks']))

    def test_open_contour_does_not_destroy_independent_good_loop(self):
        result = opening_marks(square()[:-1] + square(10))
        self.assertEqual(1, len(result['marks']))
        self.assertIn('open_or_branched', result['errors'])

    def test_duplicate_edge_is_ambiguous(self):
        edges = square()
        result = opening_marks(edges + [edges[0]])
        self.assertFalse(result['marks'])
        self.assertIn('open_or_branched', result['errors'])

    def test_self_crossing_is_rejected(self):
        result = opening_marks(polygon([(0, 0), (2, 2), (0, 2), (2, 0)]))
        self.assertFalse(result['marks'])
        self.assertIn('self_intersection_or_zero_area', result['errors'])

    def test_crossing_separate_loops_are_rejected(self):
        result = opening_marks(square() + square(1, 1))
        self.assertFalse(result['marks'])
        self.assertIn('touching_or_crossing_loops', result['errors'])

    def test_touching_at_edge_is_rejected(self):
        self.assertFalse(opening_marks(square() + square(2, 0))['marks'])

    def test_touching_at_vertex_is_rejected(self):
        self.assertFalse(opening_marks(square() + square(2, 2))['marks'])

    def test_nested_island_is_not_marked_or_crossed(self):
        result = opening_marks(square(size=10) + square(2, 2, 2))
        self.assertFalse(result['marks'])
        self.assertEqual(1, result['islands'])
        self.assertIn('opening_contains_solid_island', result['errors'])

    def test_hole_inside_island_and_separate_hole(self):
        result = opening_marks(square(size=20) + square(2, 2, 10) + square(4, 4, 2) + square(30))
        self.assertEqual(2, len(result['marks']))
        self.assertEqual(1, result['islands'])

    def test_tiny_or_projected_flat_loop_is_skipped(self):
        self.assertFalse(opening_marks(square(size=0.001), minimum_length=0.01)['marks'])
        self.assertFalse(opening_marks(polygon([(0, 0), (1, 0), (2, 0), (3, 0)]))['marks'])

    def test_large_world_coordinates(self):
        self.assertEqual(1, len(opening_marks(square(1e9, 1e9))['marks']))

    def test_empty_or_invalid_edges(self):
        self.assertFalse(opening_marks([])['marks'])
        result = opening_marks([{'points': []}, {'points': [(float('nan'), 0), (0, 0)]}])
        self.assertFalse(result['marks'])
        self.assertEqual(2, len(result['errors']))


class DrawTransactionTests(unittest.TestCase):
    def run_mark(self, fail_second):
        path = Path(__file__).resolve().parents[1] / 'BIM Test.tab/2DView.panel/Line.stack/XLineOpeningShaft.pushbutton/script.py'
        source = ast.parse(path.read_text(encoding='utf-8'))
        draw = next(node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == 'draw_x')
        document = SimpleNamespace(lines=[])
        calls = []

        def create(view, line):
            calls.append(line)
            if len(calls) == 2 and fail_second:
                raise RuntimeError('Revit rejected second diagonal')
            document.lines.append(line)

        document.Create = SimpleNamespace(NewDetailCurve=create)
        states = SimpleNamespace(Started='started', Committed='committed')

        class Sub:
            def __init__(self, doc):
                self.state = None
            def Start(self):
                self.state = states.Started
            def Commit(self):
                self.state = states.Committed
                return self.state
            def GetStatus(self):
                return self.state
            def RollBack(self):
                document.lines.clear()
                self.state = 'rolledback'
            def Dispose(self):
                pass

        namespace = {'doc': document, 'view': object(), 'SubTransaction': Sub,
                     'TransactionStatus': states, 'Line': SimpleNamespace(CreateBound=lambda a, b: (a, b)),
                     'unproject': lambda point, frame: point}
        exec(compile(ast.Module(body=[draw], type_ignores=[]), str(path), 'exec'), namespace)
        if fail_second:
            with self.assertRaises(RuntimeError):
                namespace['draw_x']([((0, 0), (2, 2)), ((0, 2), (2, 0))], None)
        else:
            namespace['draw_x']([((0, 0), (2, 2)), ((0, 2), (2, 0))], None)
        return document.lines

    def test_both_diagonals_commit(self):
        self.assertEqual(2, len(self.run_mark(False)))

    def test_second_diagonal_failure_rolls_back_first(self):
        self.assertEqual([], self.run_mark(True))


if __name__ == '__main__':
    unittest.main()
