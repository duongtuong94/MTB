# BIM Test dialog layout

Color Filter, Copy Filters and Join Geometry use shared runtime layout helpers
in `lib/bim_ui.py`. This change keeps their existing WinForms controls and Revit
operations; it does not require a WPF migration.

- Forms can resize/maximize. Initial outer bounds fit the working area of Revit's
  monitor, excluding the taskbar; the cursor monitor is the fallback.
- Runtime dimensions and the form's DPI baseline describe the same DPI to avoid
  applying designer scaling to already measured controls.
- Headings occupy separate automatically measured rows above content.
- List/data areas can scroll. A small viewport may need horizontal scrolling;
  it must not force text or controls to overlap.
- Primary actions and Close occupy a separate wrapping footer outside the
  scrollable content. Status text wraps within the available width.
- Join Geometry rows use actual ComboBox/Button preferred heights when resized.

## Verification

`tests/probe_ui_layout.py` constructs the actual UI classes using pyRevit's
IronPython/.NET assemblies without opening Revit or executing model operations.
The probe injects synthetic font and spacing scales of 100%, 125%, 150%, 175%,
200%, 250% and 300%. It also tests a 960 x 640 outer window at 100%, 150%, 250%
and 300%: 33 scenarios for three forms.

Assertions check AutoSize text height, sibling overlap, footer bounds, and button
bounds inside the footer. `probe_ui_layout.ps1` hosts the probe with the local
pyRevit IronPython runtime (an explicit EnginePath can select another install).

These are layout checks, not proof of Windows/Revit per-monitor DPI behavior.
Final checks in Revit should cover opening on the laptop at 250%, resizing,
maximizing, scrolling to all options, cancelling with Esc, and moving between
monitors with different scale. Actual process DPI awareness belongs to Revit;
the extension does not modify the host's DPI settings.

## Distribution

Commit/push these changes from the development checkout, then use Update Tools
in the installed extension and Reload pyRevit. Copying files directly into a
separate Git checkout leaves local changes that block Update Tools.
