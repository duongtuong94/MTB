# -*- coding: utf-8 -*-
"""Move Grid/Level ends in bulk and switch the chosen ends to 2D.

Workflow:
1. Run command.
2. Drag one rectangle. Only Grid and Level elements are accepted.
3. Click one target point.

For every selected Grid/Level, the endpoint on the clicked side is switched to
ViewSpecific (2D) and moved to the projection of the clicked point on that
Datum. The endpoint may be extended or shortened. The opposite endpoint is
preserved, and the moved endpoint is not allowed to cross it.
"""

from pyrevit import revit, DB, forms
from Autodesk.Revit.UI.Selection import ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException, InvalidOperationException

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView

PARAMETER_TOLERANCE = 1.0e-9
VECTOR_TOLERANCE = 1.0e-12


class DatumSelectionFilter(ISelectionFilter):
    def AllowElement(self, element):
        # Cho phép cả Grid và Level
        return isinstance(element, (DB.Grid, DB.Level))

    def AllowReference(self, reference, position):
        return False


def vector_xy(point_from, point_to):
    delta = point_to - point_from
    return (
        delta.DotProduct(view.RightDirection),
        delta.DotProduct(view.UpDirection)
    )


def distance_squared_in_view(point_a, point_b):
    vx, vy = vector_xy(point_a, point_b)
    return (vx * vx) + (vy * vy)


def midpoint(point_a, point_b):
    return DB.XYZ(
        (point_a.X + point_b.X) * 0.5,
        (point_a.Y + point_b.Y) * 0.5,
        (point_a.Z + point_b.Z) * 0.5
    )


def get_datum_curve_in_view(datum, prefer_view_specific=True):
    extent_types = (
        (DB.DatumExtentType.ViewSpecific, DB.DatumExtentType.Model)
        if prefer_view_specific
        else (DB.DatumExtentType.Model, DB.DatumExtentType.ViewSpecific)
    )

    for extent_type in extent_types:
        try:
            curves = datum.GetCurvesInView(extent_type, view)
            if curves is not None and curves.Count > 0:
                return curves[0]
        except Exception:
            pass

    try:
        return datum.Curve
    except Exception:
        return None


def curve_orientation_matches_datum(datum, view_curve):
    try:
        model_curve = datum.Curve

        view_dx, view_dy = vector_xy(
            view_curve.GetEndPoint(0),
            view_curve.GetEndPoint(1)
        )
        model_dx, model_dy = vector_xy(
            model_curve.GetEndPoint(0),
            model_curve.GetEndPoint(1)
        )

        dot_value = (view_dx * model_dx) + (view_dy * model_dy)
        if abs(dot_value) > VECTOR_TOLERANCE:
            return dot_value >= 0.0

        view_start = view_curve.GetEndPoint(0)
        view_end = view_curve.GetEndPoint(1)
        model_start = model_curve.GetEndPoint(0)
        model_end = model_curve.GetEndPoint(1)

        same_score = (
            distance_squared_in_view(view_start, model_start)
            + distance_squared_in_view(view_end, model_end)
        )
        reversed_score = (
            distance_squared_in_view(view_start, model_end)
            + distance_squared_in_view(view_end, model_start)
        )
        return same_score <= reversed_score
    except Exception:
        return True


def datum_end_from_curve_index(datum, view_curve, curve_index):
    same_orientation = curve_orientation_matches_datum(datum, view_curve)

    if same_orientation:
        return DB.DatumEnds.End0 if curve_index == 0 else DB.DatumEnds.End1

    return DB.DatumEnds.End1 if curve_index == 0 else DB.DatumEnds.End0


def curve_index_from_datum_end(datum, view_curve, datum_end):
    same_orientation = curve_orientation_matches_datum(datum, view_curve)

    if same_orientation:
        return 0 if datum_end == DB.DatumEnds.End0 else 1

    return 1 if datum_end == DB.DatumEnds.End0 else 0


def collect_datum_data(datums):
    data = []
    failed_count = 0

    for datum in datums:
        try:
            if not datum.CanBeVisibleInView(view):
                failed_count += 1
                continue

            curve = get_datum_curve_in_view(datum, True)
            if curve is None or not curve.IsBound:
                failed_count += 1
                continue

            data.append({
                'datum': datum,
                'curve': curve,
                'point0': curve.GetEndPoint(0),
                'point1': curve.GetEndPoint(1)
            })
        except Exception:
            failed_count += 1

    return data, failed_count


def get_common_side_direction(datum_data, picked_point):
    reference_item = None
    reference_index = None
    nearest_distance = None

    for item in datum_data:
        for curve_index, endpoint in (
                (0, item['point0']),
                (1, item['point1'])):
            current_distance = distance_squared_in_view(endpoint, picked_point)
            if nearest_distance is None or current_distance < nearest_distance:
                nearest_distance = current_distance
                reference_item = item
                reference_index = curve_index

    if reference_item is None:
        return None

    reference_mid = midpoint(
        reference_item['point0'],
        reference_item['point1']
    )
    reference_end = (
        reference_item['point0']
        if reference_index == 0
        else reference_item['point1']
    )

    direction_x, direction_y = vector_xy(reference_mid, reference_end)
    length_squared = (direction_x * direction_x) + (direction_y * direction_y)

    if length_squared <= VECTOR_TOLERANCE:
        return None

    return direction_x, direction_y


def choose_same_side_curve_index(item, common_direction, picked_point):
    mid = midpoint(item['point0'], item['point1'])

    v0x, v0y = vector_xy(mid, item['point0'])
    v1x, v1y = vector_xy(mid, item['point1'])

    dir_x, dir_y = common_direction
    score0 = (v0x * dir_x) + (v0y * dir_y)
    score1 = (v1x * dir_x) + (v1y * dir_y)

    if abs(score0 - score1) <= VECTOR_TOLERANCE:
        distance0 = distance_squared_in_view(item['point0'], picked_point)
        distance1 = distance_squared_in_view(item['point1'], picked_point)
        return 0 if distance0 <= distance1 else 1

    return 0 if score0 > score1 else 1


def create_moved_curve(current_curve, picked_point, curve_end_index):
    if current_curve is None or not current_curve.IsBound:
        return None, 'invalid'

    unbound_curve = current_curve.Clone()
    unbound_curve.MakeUnbound()

    projection = unbound_curve.Project(picked_point)
    if projection is None:
        return None, 'invalid'

    target_parameter = projection.Parameter
    start_parameter = current_curve.GetEndParameter(0)
    end_parameter = current_curve.GetEndParameter(1)

    if curve_end_index == 0:
        if target_parameter >= end_parameter - PARAMETER_TOLERANCE:
            return None, 'crossed'
        new_start_parameter = target_parameter
        new_end_parameter = end_parameter
    else:
        if target_parameter <= start_parameter + PARAMETER_TOLERANCE:
            return None, 'crossed'
        new_start_parameter = start_parameter
        new_end_parameter = target_parameter

    if (
            abs(new_start_parameter - start_parameter) <= PARAMETER_TOLERANCE
            and abs(new_end_parameter - end_parameter) <= PARAMETER_TOLERANCE):
        return None, 'unchanged'

    new_curve = current_curve.Clone()
    new_curve.MakeBound(new_start_parameter, new_end_parameter)
    return new_curve, 'ok'


def pick_target_point():
    try:
        return uidoc.Selection.PickPoint(
            "Click the target line for the Grid/Level ends"
        )
    except InvalidOperationException:
        forms.alert(
            "The active view has no Work Plane.\n\n"
            "Run the command in a plan, elevation or section view with an "
            "active Work Plane.",
            title="Move Datum Ends 2D"
        )
        return None


def main():
    try:
        picked_elements = uidoc.Selection.PickElementsByRectangle(
            DatumSelectionFilter(),
            "Drag a rectangle to select Grids/Levels"
        )
    except OperationCanceledException:
        return

    datums = [element for element in picked_elements if isinstance(element, (DB.Grid, DB.Level))]
    if not datums:
        forms.alert("No Grid or Level was selected.", title="Move Datum Ends 2D")
        return

    try:
        picked_point = pick_target_point()
    except OperationCanceledException:
        return

    if picked_point is None:
        return

    datum_data, failed_count = collect_datum_data(datums)
    if not datum_data:
        forms.alert(
            "No selected item can be modified in the active view.",
            title="Move Datum Ends 2D"
        )
        return

    common_direction = get_common_side_direction(datum_data, picked_point)
    if common_direction is None:
        forms.alert(
            "Could not determine the clicked end side.",
            title="Move Datum Ends 2D"
        )
        return

    datum_end_pairs = []
    for item in datum_data:
        try:
            curve_index = choose_same_side_curve_index(
                item,
                common_direction,
                picked_point
            )
            datum_end = datum_end_from_curve_index(
                item['datum'],
                item['curve'],
                curve_index
            )
            datum_end_pairs.append((item['datum'], datum_end))
        except Exception:
            failed_count += 1

    moved_count = 0
    shortened_count = 0
    extended_count = 0
    crossed_count = 0
    unchanged_count = 0

    transaction = DB.Transaction(doc, "Move Datum Ends 2D")
    transaction.Start()

    try:
        valid_pairs = []

        for datum, datum_end in datum_end_pairs:
            try:
                datum.SetDatumExtentType(
                    datum_end,
                    view,
                    DB.DatumExtentType.ViewSpecific
                )
                valid_pairs.append((datum, datum_end))
            except Exception:
                failed_count += 1

        doc.Regenerate()

        for datum, datum_end in valid_pairs:
            try:
                current_curve = get_datum_curve_in_view(datum, True)
                if current_curve is None or not current_curve.IsBound:
                    failed_count += 1
                    continue

                curve_end_index = curve_index_from_datum_end(
                    datum,
                    current_curve,
                    datum_end
                )

                old_start = current_curve.GetEndParameter(0)
                old_end = current_curve.GetEndParameter(1)

                new_curve, status = create_moved_curve(
                    current_curve,
                    picked_point,
                    curve_end_index
                )

                if status == 'crossed':
                    crossed_count += 1
                    continue
                if status == 'unchanged':
                    unchanged_count += 1
                    continue
                if new_curve is None:
                    failed_count += 1
                    continue

                if not datum.IsCurveValidInView(
                        DB.DatumExtentType.ViewSpecific,
                        view,
                        new_curve):
                    failed_count += 1
                    continue

                new_start = new_curve.GetEndParameter(0)
                new_end = new_curve.GetEndParameter(1)

                old_length_parameter = old_end - old_start
                new_length_parameter = new_end - new_start

                datum.SetCurveInView(
                    DB.DatumExtentType.ViewSpecific,
                    view,
                    new_curve
                )

                moved_count += 1
                if new_length_parameter < old_length_parameter:
                    shortened_count += 1
                else:
                    extended_count += 1
            except Exception:
                failed_count += 1

        transaction.Commit()
    except Exception:
        if transaction.HasStarted():
            transaction.RollBack()
        raise


if __name__ == "__main__":
    try:
        main()
    except OperationCanceledException:
        pass
    except Exception as error:
        forms.alert(
            "Command failed:\n\n{0}".format(error),
            title="Move Datum Ends 2D"
        )