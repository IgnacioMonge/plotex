# Plotex Changelog

All changes relative to Veusz 4.2 (base fork).

---

## v1.7.0 (work in progress) — Sprint 2+3+4

### Sprint 4 — LOW cleanup, hardening, docs (this slice)

#### Security: tighter safe_eval attribute filter
- New `forbidden_attrs` blacklist in `safe_eval.py` rejects access to
  `lib`, `core`, `distutils`, `f2py`, `testing`, `ctypeslib`, plus
  introspection helpers (`globals`, `locals`, `vars`, `dir`, `exec`,
  `eval`, `compile`, `open`, `input`, `breakpoint`, `exit`, `quit`,
  `system_info`, `show_config`, `info`, `lookfor`, `source`, `test`,
  `setup`, `subclasshook`). Pre-fix the visitor only blocked attributes
  prefixed with `__`/`func_`/`im_`/`tb_`, so a chain like
  `numpy.lib.npyio.read_array_header_1_0(...)` survived parse-time
  validation.

#### LOW dialogs / cleanup
- `widgets/shape.py` ImageFile draw path wrapped in `painter_state`:
  opacity + clipPath now restore via try/finally even if `drawImage`
  raises. The previous code restored opacity manually only on the
  success path, and the `setClipping(False)` toggle didn't run if
  drawImage threw between setClipPath and the toggle.
- `dialogs/exceptiondialog.py` `ExceptionSendDialog` is now created with
  `WA_DeleteOnClose` so it is reaped promptly after Send/Cancel.
- `windows/commandpalette.py` palette gets `WA_DeleteOnClose`. Pre-fix
  the popup leaked references to QActions captured at open time; if any
  of those actions were subsequently deleted (tab change), invoking
  the palette later raised `RuntimeError: wrapped C/C++ object …
  has been deleted`.
- `dataimport/capture.py` `_setTimeout` no longer assigns the return of
  static `QTimer.singleShot` to `self.timer` (singleShot returns None;
  the attribute was misleading dead code).
- `dataimport/base.py` removed the duplicate `self.olddatasets = [...]`
  comprehension that was discarded by the very next assignment to
  `[]` — pure dead code.

#### Docs / fork attribution
- `INSTALL.md` retitled and clarified: the Windows binary at
  `IgnacioMonge/plotex/releases` ships **Plotex**; the
  `veusz.github.io` link, PPA, flatpak, conda-forge entries describe
  upstream Veusz, kept for reference because the build/runtime
  requirements are the same.
- `Documents/man-page/veusz.pod` BUGS link → Plotex issues; AUTHORS
  acknowledges the fork in addition to upstream.

### Tests
- 18 new regression tests covering safe_eval forbidden attrs (12
  parametrised cases), setting validators (Distance/IntOrAuto/Filename/
  FloatList type-strict), and ENVIRON whitelist (credentials filtered,
  PATH retained). Total now **107**, all green.

---

## v1.7.0 (work in progress) — Sprint 2+3: settings, security, UX, build

### Security
- `evaluate.py` ENVIRON now exposes only a whitelist of locale/system
  vars (PATH, HOME, USER, LANG, LC_*, TZ, OS info, TEMP) and filters
  out anything containing TOKEN / SECRET / PASSWORD / AUTH /
  ACCESS_KEY / API_KEY / etc. Pre-fix a malicious .vsz could read the
  host process environment (AWS keys, GitHub tokens, DB passwords)
  via `ENVIRON['…']` in a label expression and exfiltrate it via an
  exported PDF.
- `document/export.py` now refuses to write the final PS/EPS file when
  the destination path is a symlink (or resolves outside the directory
  the user picked). Previously `os.remove(self.filename)` followed
  the symlink, deleting the link's target and writing our export to
  an arbitrary location — exploitable from a .vsz that triggers an
  automated export.
- `embed_remote.py`: `unsafe_mode` is no longer forced on for every
  embedded session. It's now opt-in via the `PLOTEX_EMBED_UNSAFE=1`
  environment variable, with a stderr warning printed the first time
  it is enabled. Pre-fix a host program embedding Plotex could
  silently load any user-supplied .vsz with the safe-mode prompt
  bypassed.

### Settings & data integrity
- `Reference.resolve()` now detects circular references (visited set +
  64-hop cap) and raises `ResolveException` instead of recursing until
  Python's stack overflows. Pre-fix a stylesheet loop crashed the
  interpreter on the next access.
- `OperationSettingSet.do()` now restores the previous value if
  `setting.set()` raises mid-operation. A propagation that failed
  partway through used to leave the setting half-modified, with no
  undo entry.
- `Dataset.invalidDataPoints` cache key now uses the array buffer
  address + shape + dtype + strides + document changeset, and the
  cache entry holds strong references to the wrapped arrays. Pre-fix
  the cache used `id(array)`, which CPython can recycle once the
  original array is GC'd → false hits returning the wrong invalid
  mask.
- `setting.py` type-strict normalizers: `Distance` rejects non-str,
  `IntOrAuto` and `FloatList` reject `bool` (subclass of `int` —
  silently coerced True→1), `FloatList` rejects `inf`/`nan`,
  `Filename` rejects non-str (was crashing with `AttributeError` on
  `.replace`).

### UX
- `dialogs/fitdialog.py` `_doFit` now uses an `_fit_in_progress` flag
  + `OverrideCursor` + `try/finally` cleanup, and the four
  `processEvents()` calls collapsed to one with input events excluded.
  Pre-fix a user clicking Close mid-fit fired `accept()` while
  `actionFit` was still running — operating on a half-destroyed
  dialog.
- `Cancel` in the Preferences dialog already restores
  color_scheme/font/QApplication.font (Sprint 1); ENVIRON whitelist
  and tighter validators above further reduce surprise mutations.
- `defn_fits.readDataFromFile` collects per-item failures in
  `_import_errors` instead of aborting the entire FITS import on the
  first malformed HDU. The user keeps the valid HDUs and gets a list
  of what failed.
- New `utils.safe_singleShot(ms, widget, callback)` helper checks
  whether the widget (and its sip C++ side) is still alive before
  firing. Migrated from raw `QTimer.singleShot` in datacreate2d,
  dataeditdialog (×4), export, filterdialog, histodata, importdialog,
  plugin. Pre-fix closing the dialog within the singleShot delay
  raised a `RuntimeError: wrapped C/C++ object … has been deleted`
  on every fire.

### Threading
- `document/doc.py` `_acquireWriteLock` no longer pumps the Qt event
  loop between tryLockForWrite attempts. The render thread releases
  its read lock on its own; pumping events here let timer ticks /
  cross-thread signals call back into `applyOperation`, escalating
  the depth counter without ever releasing the underlying
  `QReadWriteLock`.

### Numerical correctness
- `widgets/boxplot.py` 1.5×IQR top whisker now `max(..., 0)`-clamps
  the searchsorted index. Pre-fix `-1` wrapped around to the maximum
  via Python negative indexing — silently emitting the wrong whisker
  on heavily asymmetric data.
- `datasets/histo.py` guards `numbins <= 0` and `maxval == minval`
  before computing bin width. Pre-fix `delta = 0` produced N
  coincident bin edges.
- `widgets/fit.py` `resid_var` returns `nan` when `dof <= 0` instead
  of silently dividing by 1 — over-fitted models no longer get
  bogus prediction bands.

### Build, packaging, tests
- URLs throughout the codebase now point at `IgnacioMonge/plotex`
  (was a mix of `imongegar/plotex`, upstream `veusz/veusz`, etc.).
- `requirements.txt` adds upper bounds (`numpy<3`, `PyQt6<7`,
  `sip<7`, `astropy<8`, `h5py<4`) so a transitive major-version bump
  cannot silently break the app.
- `build_msvc.bat` honours pre-set `VCVARS` and `QMAKE_EXE` env vars
  before falling back to defaults — reduces edit-this-file friction
  on CI / non-default installs.
- `plotex_installer.iss` adds `[UninstallDelete]` for
  `%LOCALAPPDATA%\Plotex` (bytecode cache + HMAC key from the v1.5.2
  loader hardening).
- `support/veusz_windows_pyinst.spec` makes optional hidden imports
  (`iminuit`, `astropy`, `h5py`) actually optional — the build no
  longer fails when they aren't installed; just emits a `SKIP …`
  line and ships an exe without those features.
- `tests/conftest.py` provides a session-scoped `QApplication` so
  test modules don't recreate it on import.
- `utils/openEncoding(filename, encoding, mode='r', errors='replace')`
  now accepts `errors=` as a keyword. Callers that need to detect
  encoding corruption can pass `errors='strict'`; the historical
  silent-replacement default is preserved.

---

## v1.6.0 (work in progress) — Sprint 1: HIGH quick wins

Builds on v1.5.2. Fixes 16 HIGH-severity issues from the 2026-04-27 audit.

### QPainter state-stack safety
- Added `utils.painter_state(painter)` context manager: pairs save/restore in
  a `try/finally` so an exception mid-draw can no longer leave the painter
  with a residual clip/transform/brush.
- Migrated `painthelper.renderToPainter` (the root of the render tree) and
  12 widgets to the new helper: `contour`, `colorbar`, `kaplanmeier`, `key`,
  `vectorfield`, `textlabel`, `axisbroken`, `axis` (drawGrid +
  drawAutoMirror), `point`, `ternary` (3 labels), `shape` (BoxShape),
  `ridgeline`. Pre-fix any one of these could corrupt the rest of the page
  on failure; in batch exports it could corrupt every following page.
- `document/export.py` ExportPrinter wraps `QPainter(printer)` in
  try/finally so `painter.end()` always runs.

### Capture / IPC hardening
- `dataimport/capture.py`: `shell=True` replaced with `shlex.split` +
  `shell=False`. Shell-injection sink eliminated. Buffer capped at 16 MiB
  (was unbounded — a producer with no newlines could exhaust memory).
  `Popen.wait(timeout=5)` after kill so we never leak a zombie. Windows
  TASKKILL via `subprocess.run` instead of `os.system`.
- `embed.py`: `sendCommand` now holds `QLock`/`threading.Lock` so concurrent
  callers cannot interleave length headers and JSON payloads on the shared
  socket. `writeToSocket` raises `ConnectionError` on `BrokenPipeError` /
  `ConnectionResetError`. `startRemote` guarded with `_start_lock` against
  concurrent first-init. `exitQt` reaps the remote child with bounded wait.
- `embed_remote.py`: `readFromSocket` wraps the body in `try/finally` that
  restores the notifier + non-blocking socket even on partial read.
  `slotDataToRead` catches non-socket exceptions and surfaces them via
  `writeOutput` instead of leaving the client hung.

### Resource leaks
- `urlopen` × 4 (`exceptiondialog`, `utils/version`, `utils/feedback`,
  `plugins/votable`) now use `with` + bounded timeout. `version.py` switched
  to HTTPS (was plain http — MITM-able).
- `dialogs/export.py`: the per-export `QTimer` is stopped + disconnected +
  `deleteLater`'d before being replaced, so a fast double-Export can't leave
  the previous timer firing against a stale closure.
- `dialogs/importdialog.py` and `dialogs/capturedialog.py`:
  `QFileSystemModel` and `QCompleter` now parented to the dialog (or
  completer) so the filesystem watcher doesn't leak handles on Windows.
- `dialogs/capturedialog.py`: added `closeEvent` that calls `slotCancel`
  when the user closes with the WM X — pre-fix the read/display/update
  timers and the underlying capture stream stayed alive in the background.

### Threading correctness
- `dialogs/dataeditdialog.py`: each `QAbstractTableModel` now auto-disconnects
  its `signalModified` slot when destroyed (helper: `_autoDisconnectOnDestroyed`).
  Previously the document held a strong reference into a sip-deleted Python
  wrapper and emitted into nothing — eventually crashing.
- `widgets/image.py`: cache mutated from off-main render threads is now
  guarded by `QMutex`, and the cache holds a strong reference to the
  source `transimg` array so `id()` cannot be recycled by a later array
  and produce a false cache hit.
- `document/loader.py`: `_takeDocumentSnapshot` now acquires
  `QReadLocker(_render_lock)` so the serialised script + data dict +
  history lists are mutually consistent. Pre-fix a concurrent operation
  could mutate `thedoc.data` mid-snapshot, silently corrupting rollback.

### UX
- `dialogs/preferences.py`: Cancel now actually cancels. The dialog
  snapshots the original `color_scheme`, `ui_font*`, and `QApplication.font`
  on open; `reject()` restores them. Pre-fix moving the font spinner or
  changing the color scheme combo applied immediately and never reverted
  on Cancel — the button label was a lie.

### Tests
- 9 new regression tests covering the above (painter state, capture shell,
  embed shutdown guard, model auto-disconnect, snapshot under lock, image
  cache mutex). Total now: 84.

---

## v1.5.2 (2026-04-27) — Hotfix: security & build coherence

Sprint 0 from internal exhaustive audit (220+ findings, 10 parallel agents).

### Security (RCE / cache poisoning)
- **Bytecode cache authenticity**: `loader.py` cache now signed with HMAC-SHA256
  using a per-installation key in `%APPDATA%/Plotex/.cache_key` (chmod 600).
  Previous MD5 hash was stored *inside* the cache file itself — an attacker
  with write access to the cache dir could forge matching bytecode. HMAC with
  a key the attacker doesn't have closes that vector.
- **AST safe-mode validator**: `commandinterpreter._validate_safe_ast` now
  walks the entire AST recursively (`ast.walk`), rejecting any non-whitelisted
  Name/Call/Attribute/Subscript/Lambda/comprehension. Previous version only
  validated the top-level Call.func, allowing bypass via
  `Set('x', __import__('os').system(...))`.
- **safe_eval whitelist**: replaced blacklist of 17 names with explicit
  whitelist of approved numpy functions/attributes. Closes attribute-chain
  bypass via `getattr(numpy.lib.npyio, ...)`.
- **NumPy pickle**: `plugins/importplugin.py` `N.load()` now passes
  `allow_pickle=False` for `.npy`/`.npz`. Object arrays could deserialize
  arbitrary pickle code.
- **OperationWidgetPaste safe mode**: now sets `setSafeMode(True)` like
  OperationDataPaste. Previously, paste of malicious widget from clipboard
  could execute Python.

### Build & release coherence
- **VERSION** bumped to 1.5.2 (was 2.0; conflicted with installer/changelog).
- **`setup.cfg`**: `python_requires` syntax fixed (was `>= 3.8` without `=`,
  silently ignored by setuptools); `fits` extras `sampy` removed (package
  doesn't exist on PyPI; `;` is invalid extras separator).
- **PyInstaller spec**: removed phantom data entries (`embed.py`, `__init__.py`
  in cwd root that don't exist); added missing hidden imports `scipy`,
  `scipy.{stats,optimize,special}`, `iminuit`, `astropy`, `h5py` — without
  these, `fit`/`qqplot`/HDF5/FITS crashed with `ModuleNotFoundError` in the
  packaged app.
- **NumPy 2.x compat**: `roccurve.py` uses `N.trapezoid` when available,
  falls back to `N.trapz` (deprecated in 2.x). Tests already used
  `N.trapezoid`; production didn't.
- **Removed legacy NSIS build script** (`support/veusz_windows_build_installer.py`)
  pointing to `c:\build\veusz`, NSIS, `veusz.exe` — contradicted current Inno
  Setup flow.

### Threading
- **Loader worker timeout**: `bridge._event.wait()` now has 600s timeout
  (was indefinite; could hang permanently if main thread didn't process the
  signal).
- **Loader race finished/exec**: check `worker.isFinished()` before
  `loop.exec()` to avoid hang when worker completes before event loop starts.

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
