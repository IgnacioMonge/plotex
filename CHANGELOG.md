# Plotex Changelog

All changes relative to Veusz 4.2 (base fork).

---

## v1.5.1 (2026-04-11) — Hotfix: file loading hang on installed version

### Bug fix
- **Loader hang on Windows**: `tempfile.mkstemp()` blocks indefinitely when
  creating the bytecode cache (`.vszc`) in a protected directory such as
  `C:\Program Files`. `os.access(W_OK)` cannot reliably detect this on
  Windows (it checks the read-only flag, not ACLs).
  **Fix**: bytecode cache now always writes to `%LOCALAPPDATA%\Plotex\cache\`
  (Windows) or `~/.cache/plotex` (Unix), keyed by an MD5 hash of the
  original file path. This avoids any write to protected directories.

### Other improvements
- Loader `sigPhase` signal now uses explicit `QueuedConnection` to avoid
  calling widget methods from the worker thread (undefined behaviour in Qt 6).
- `build_installer.bat` cleans known stale DLLs from the dist directory
  before compiling the installer.

---

## v2.0 (2026-04-07) — First public release

### External code audit (6 rounds with ChatGPT)
All findings from CRITICAL to LOW resolved across 10 iterations:

- **Document locking**: reentrant write lock with thread-ID tracking and depth counting. No deadlocks, no skipped operations, no silent data loss.
- **Loader safety**: side-effect-free `serializeToText()` for snapshots. Document snapshot/restore on failed load (preserves data, changeset, undo history, modified flag). Worker thread no longer mutates evaluator/document state — compile only in worker, env construction + exec on main thread.
- **Render thread resilience**: exceptions no longer kill the thread. Queue accounting via try/finally ensures consistent state.
- **Axis labels**: statistical widgets (KM, ROC, Bland-Altman) set labels via `defaultAxisLabels()` in `OperationWidgetAdd`, fully undoable with reference state preserved.
- **Statistical correctness**: Hanley-McNeil 1982 SE formula for ROC AUC (Q1/Q2 terms). Mislabeled methods renamed honestly (approximate pointwise bands, not confidence bands).
- **Crash fixes**: bracket getRange() no longer mutates axis settings. fit.py fitRange uses correct getAxes() list API. painthelper rootstate None guards on all 4 consumers. Pareto div-by-zero guard. PieChart labels filtered with same mask as values. KaplanMeier groupData included in min-length. QQ plot scipy import guard.
- **Resource leaks**: QActionGroup parented to submenu. Loader callbacks with try/finally. HDF5 files with context manager.
- **Fit widget**: `log=` parameter on fitLM and minuitFit (no global stdout redirect). Asymmetric errors trimmed to data length. Dead fitDataFingerprint removed.
- **UI**: getClick uses QEventLoop with _click_valid flag. processEvents during load restricted to ExcludeUserInputEvents.

### Automated tests
39 regression tests covering: document locking (4), axis labels undo/redo (4), loader rollback (7), array alignment (2), statistical correctness (3), painthelper null guards (4), bracket getRange (1), fit safety (3), KM data edges (2), ROC edge cases (4), undo/redo extended (3), serialize roundtrip (2).

### Rebranding
- VeuszApp → PlotexApp
- Module docstrings, tutorial, console, embed API updated
- README with full feature list and Veusz attribution

### Other
- Qt upgraded to 6.11.0 / PyQt6 6.11.0
- PDF export DPI fix (content now scales with DPI, not just page size)
- Plugin add crash fix (variable shadowing of `_()` translation function)
- Ridgeline auto-color uses document color theme instead of hardcoded palette
- Per-graph theme application via right-click menu (14 themes)
- Copy-to-page menu now includes "called 'name'" variant
- KaplanMeier CI band controlled by ConfFill.hide (no redundant toggle)

---

## v1.4 (2026-03-22)

### New Widgets
- **Violin plot** — KDE density estimation, split mode, raincloud layout, inner box/quartile/stick annotations, 6 dedicated formatting tabs
- **Bracket connector** — statistical comparison brackets for boxplots/bars, group-based positioning, auto-Y, stacking, label offset, configurable label background
- **Kaplan-Meier** — step-function survival curves, censored marks, CI bands (Greenwood), group stratification
- **ROC curve** — diagnostic performance, AUC with Hanley-McNeil SE, Youden index, diagonal reference
- **Bland-Altman** — method comparison, bias ± limits of agreement, regression line, CI bands
- **QQ plot** — quantile-quantile against normal/uniform/exponential/t/chi2, approximate envelope band
- **Pie chart** — auto-grouping small slices, labels, donut mode
- **Pareto chart** — sorted bars with cumulative line
- **Ridgeline** — stacked KDE densities with overlap control
- **Heatmap** — 2D color matrix with annotations
- **Polar trending** — time-series on polar coordinates

### Curve Fitting (Major Rewrite)
- scipy.optimize.least_squares replaces custom LM (10-50x faster)
- Fit dialog with function presets, parameter table, goodness-of-fit report
- Confidence bands (95% CI) and prediction bands
- Band data persists in .vsz files
- Fast path for linear regression (numpy-only)

### BoxPlot Enhancements
- Individual data points (strip plot) with jitter
- Fill palette with auto-color from discrete palettes
- showOutliers toggle

### Plot Themes (14 presets)
Classic, Black & White, Publication, Minimal, Dark, ggplot2, Seaborn, Economist, FiveThirtyEight, Tufte, BMJ, GraphPad Prism, Solarized Light

### Color System
- Palette-aware color picker with hex input
- Import colormaps from file (.txt, .csv, .gpl, .cpt)
- ColorBrewer, journal, and scientific palettes
- 6 new palettes: Okabe-Ito, Wong, Tol-Vibrant, Tol-Muted, Tableau 10, Plotex

### Data Import
- Excel (.xlsx, .xlsm), ODS (.ods), JSON import

### Rendering Optimization
- QPen/QBrush caching, axis coordinate caching
- Spatial hash for label overlap (O(n) vs O(n²))
- Bytecode cache (.vszc) for faster reload
- Debounced zoom with fast preview

### UI/UX
- Ribbon toolbar, command palette, split view, rulers
- Drag & drop .vsz files, splash screen, empty state
- Zoom to page on load, zoom preserved per page
- Data editor with spreadsheet editing, paste from clipboard
- Image auto-embed, opacity, flip, greyscale, corner radius
- Pan with middle mouse button

### Security (22 items)
- Remote protocol: pickle+eval → JSON + whitelist
- MIME clipboard: eval() → ast.literal_eval()
- Render thread isolation via QReadWriteLock
- Console safe mode, path traversal prevention
- All bare excepts replaced with except Exception

### Build
- PyInstaller optimized: 198 MB → 168 MB
- Inno Setup installer with LZMA2: 45 MB
- File associations for .vsz/.vszh5

---

## v0.0–v1.3 (2026-03-15)

### v0.0 — Baseline
- Build patches: sip-build fallback, 64-bit pointer cast fix, PyInstaller exclusions (721→197 MB)

### v0.1 — Quick Wins
- Expression context spread operator, asarray for float64, array copy elimination
- Marker path LRU cache, regex precompile, min/max vectorization

### v0.2 — Startup & Security
- ast.literal_eval() for settings persistence
- Lazy console loading

### v0.3 — Rendering Pipeline
- Error bar path batching, contour list comprehension, colormap consolidation

### v0.4 — Data Pipeline
- Expression evaluation resize optimization, numpy safe items cache
- HDF5/FITS asarray optimization

### v1.0 — 2D Rendering
- Full antialiasing (screen + export)
- Linear and radial gradient fills

### v1.1 — Curves & Interpolation
- Catmull-Rom spline for XY plots
- Bicubic image interpolation
- Smooth contours

### v1.2 — Image Performance
- Colormap QImage cache (skip recalc on zoom/pan)

### v1.3 — Feedback & Decimation
- Progress dialog during file load
- Auto point decimation for large datasets
- Wait cursor during render

---

*Plotex is based on Veusz 4.2 by Jeremy Sanders.*
*Extended by M. Ignacio Monge Garcia with assistance from Claude (Anthropic).*
