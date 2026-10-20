# Graphical references

The references track Plotex output from `examples/` and `tests/selftests/`.
Run `python tests/runselftest.py` from the repository root with
`VEUSZ_INPLACE_TEST=1` and `QT_QPA_PLATFORM=minimal`.

The audit refresh was reviewed against the inherited Veusz references:

- Preserve numerical polyline points, image payloads and text content.
- Restore the missing fit/histogram curves and four boxplot outliers before
  accepting the new output.
- Accept existing Plotex automatic colors, label backgrounds and 4 pt margins,
  SVG grouping/marker representation and omission of redundant stroke defaults.
- Add the nine statistical examples which previously had no reference.

Reference environment: Windows 11, Python 3.11, NumPy 1.26.4, PyQt6/Qt 6.11.
The runner supplies fixed font metrics, ASCII text and one-decimal SVG numbers.
Every rendered case is compared; there are no named comparison exclusions.
Missing optional dependencies are reported separately. Font fallback can still
vary between platforms, especially for MathML's native font layout; the
references were verified in the Windows environment above.

The twelve formerly excluded cases were reviewed before enabling comparisons:

- Add five 3D references after checking the generating equations, error bars,
  surface meshes and 27 volume cells, and inspecting the rendered output.
- Add MathML after checking all four expressions, their operators and layout.
- Refresh spectrum, hatching, import, profile and 1D-to-2D references for the
  adopted Plotex styles and SVG grouping. Preserve data polylines and error
  ellipse shapes; relative SVG coordinates can accumulate subpixel rounding
  offsets at the selftest's one-decimal precision.
- Fix contour-label padding to use the same device font metrics as its text.
  All 47 contour polylines remain unchanged; the corrected label boxes place
  38 contour labels instead of the inherited reference's 33.

A missing reference is a failure. Do not regenerate references to silence a
failure without checking the input data, geometry, text and visible styles.
