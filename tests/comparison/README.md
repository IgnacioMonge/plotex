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
Inherited platform-sensitive exclusions remain explicit in `runselftest.py`;
optional dependencies are reported separately. Font fallback can still vary
between platforms.

A missing reference is a failure. Do not regenerate references to silence a
failure without checking the input data, geometry, text and visible styles.
