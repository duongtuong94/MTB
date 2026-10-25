# XLineOpeningShaft manual verification

Run on a copy of a Revit project. Select one or more Shaft/Floor Opening elements
before running the command, or use the command's selection and Finish workflow.

1. One rectangular opening: two diagonals between opposite corners.
2. One sketch containing three disconnected closed profiles: three independent X
   marks, with no line spanning the gap between profiles.
3. Mixed selection of single-profile and multi-profile Openings: all valid
   profiles processed, summary counts elements and actual X marks separately.
4. Rotated rectangle/trapezoid: diagonals connect actual opposite vertices.
5. Circular or other non-four-line profiles: X uses each profile's own view-plane
   bounding rectangle, preserving the previous schematic representation.
6. Open, duplicated, self-crossing or touching boundaries: skip ambiguous groups
   and report Opening IDs. Never fall back to a box covering the whole Opening.
7. Nested profiles: odd-depth regions are solid islands, not openings. An outer
   opening containing an island is reported/skipped to avoid drawing through
   solid material. A separate nested void at even depth can get its own X.
8. Esc while selecting: exit without changes. A failed second diagonal must not
   leave a half-X. Each complete X is protected by a SubTransaction.
9. Check a plan on a nonzero level and a supported detail/section view. Curves
   are projected onto the active view plane; profiles collapsing to zero area in
   that view are skipped. A view rejecting DetailCurves reports an actual error,
   not a successful count.

Contour analysis uses the sampled curve geometry from Revit's Tessellate method.
Curved profiles and their intersection tests therefore have tessellation accuracy.
Running the tool again still creates additional detail lines, as before; this
change does not add duplicate-mark detection or deletion of existing annotations.

Automated tests: `python -m unittest discover -s tests -p test_opening_marks.py -v`.
They exercise contour analysis and the actual draw_x function with transaction
test doubles, not the Revit UI or real model geometry.
