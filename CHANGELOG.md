# Plotex Changelog

All changes relative to Veusz 4.2 (base fork).

## v1.4 (2026-03-22)

### New Widgets
- **Violin plot** — KDE density estimation, split mode, raincloud layout, inner box/quartile/stick annotations, 6 dedicated formatting tabs
- **Bracket connector** — statistical comparison brackets for boxplots/bars, group-based positioning, auto-Y, stacking, label offset, configurable label background (white/transparent/custom), draggable

### Curve Fitting (Major Rewrite)
- **scipy.optimize.least_squares** replaces custom Levenberg-Marquardt (10-50x faster for complex fits)
- **Fit dialog** — dedicated dialog with function presets (Linear, Quadratic, Power, Exponential, Gaussian, Lorentzian, Sigmoidal, Michaelis-Menten, Hill, Log, Cubic), auto-detect parameters from expression, parameter table with initial/fitted/error columns, goodness-of-fit report (chi2, dof, R2)
- **Auto result label** — checkbox to create/update a label on the graph with equation, R2, and parameter errors
- **Confidence bands** (95% CI) — covariance-based with Jacobian propagation
- **Prediction bands** — includes residual variance
- Band color matches fit line color
- Band data persists in .vsz files (instant load on reopen)
- Fast path for linear regression (numpy-only, no eval)
- NaN-safe fitting (clean abort on failed fits)
- Normal approximation fallback when scipy.stats unavailable
- Runtime warnings suppressed during optimization

### BoxPlot Enhancements
- **Individual data points (strip plot)** — jitter as fraction of box width (ggplot2 convention)
- **Independent point formatting** — PointsFill, PointsLine with custom SVG circle icons (vs diamond for outliers)
- **Fill palette** — auto-color multiple datasets from discrete palettes (cb-set1, npg, nejm, lancet, jama, aaas, okabe-ito, cb-set2, cb-dark2, cb-paired, or any imported colormap)
- **showOutliers toggle** — outliers auto-hidden when strip points active (ggplot2 behavior)
- Fill changed from BrushExtended to simple Brush (cleaner UI: Color, Style, Transparency, Hide)
- Settings reordered: mean marker, points, outliers

### Violin Plot Enhancements
- Fill palette support (same as boxplot)
- Auto-coloring with discrete palettes

### Plot Themes (13 presets)
- **Classic** — white background, L-shaped axes, no grid (Nature, Cell, Science)
- **Black & White** — gray grid, black border
- **Publication** — thick axes, ticks outside, no grid (NEJM, Lancet, JAMA)
- **Minimal** — no axes, light grid
- **Dark** — dark background for presentations
- **ggplot2** — gray panel, white grid (Wickham, H.)
- **Seaborn** — whitegrid style (Waskom, M.)
- **The Economist** — blue-gray panel, horizontal grid
- **FiveThirtyEight** — light gray, no axes, thick grid
- **Tufte** — maximum data-ink ratio, no grid (Tufte, E.)
- **BMJ** — box axes with ticks inside (British Medical Journal)
- **GraphPad Prism** — L-shaped axes, ticks outside, 14pt font
- **Solarized Light** — Schoonover palette, low contrast

### Color System
- **Palette-aware color picker** — popup replaces system QColorDialog, shows active theme colors, basic colors, and discrete colormap palettes with hex input
- **Import colormaps from file** — supports .txt/.csv (RGB 0-1), .gpl (GIMP Palette), .cpt (GMT Color Table)
- **ColorBrewer palettes** — cb-set1, cb-set2, cb-paired, cb-dark2, cb-blues, cb-reds, cb-ylorrd, cb-rdbu
- **Journal palettes** — npg, nejm, lancet, jama, aaas, okabe-ito
- **Scientific colormaps** — viridis, inferno, magma, plasma, cividis, batlow, vik, roma, hot-body

### Data Import
- **Excel import** (.xlsx, .xlsm) — sheet selector, header row, skip rows, preview, linked files
- **ODS import** (.ods) — LibreOffice/OpenOffice support, same UI as Excel
- **JSON import** — dict-of-arrays, array-of-dicts, nested paths

### Snapping & Guides
- **Snap engine** — objects snap to graph bounds, centers, and sibling widget edges (8px threshold)
- **User-defined guides** — horizontal/vertical draggable lines, auto center cross on activation
- **Guide management** — View ribbon group with icons (show, add H, add V, reset), toggle preserves positions

### Rendering Optimization
- **QPen/QBrush caching** — cached per settings object, invalidated by key comparison
- **Axis coordinate caching** — tick coordinates cached by axis location
- **Spatial hash for label overlap** — O(n) amortized instead of O(n2)
- **Batch SetData** — skip setModified per dataset during file loading
- **Bytecode cache** — .vszc files with MD5 hash for faster reload
- **Race condition fix** — antialias + page color passed as immutable job data to render thread

### UI/UX Improvements
- **Drag & drop** — .vsz files open in new tabs (works on plot area, empty state, tab bar)
- **Splash screen** — rounded corners (WA_TranslucentBackground + drawRoundedRect)
- **Zoom to page** on document load
- **Zoom preserved per page** across page switches
- **Window layout persisted** — dock widget positions saved/restored correctly (base64 encoding)
- **Empty state** — placeholder with logo, text, and drag & drop hint
- **Discard All** button when closing with multiple unsaved tabs
- **Format propagation** — hierarchical menu (this graph, this page, document, pick specific)
- **Image "Restore"** action — resets opacity, flip, greyscale, size, rotation
- **Rotated label background** — follows text rotation instead of axis-aligned bounding box
- **Legend reverse order** — also reverses keys within multi-key widgets (stacked bars)
- **Delete stays on page** — selects parent/sibling, not next page widget
- **Ribbon icons** — shorter text, all online help actions have icons, tutorial icon matches theme
- **Import dialog** — clears filename on show (no auto-preview of last file)
- **Polygon** — default triangle vertices visible on creation
- **Shapes** — fill visible by default (hide=False)

### Data Editor
- Spreadsheet-like editing (type to edit, Enter/Tab navigation)
- Paste from clipboard (Ctrl+V), Paste as New
- Readonly visual feedback, validation flash
- Smart Add Row
- "Use as" grouped in submenus

### Images
- Auto-embed on load (PNG, JPG, SVG)
- Opacity, flip H/V, greyscale, corner radius

### Bug Fixes
- IndexError guard in render thread (empty job queue)
- ZeroDivisionError guard in cgscale
- Safe undo/redo (check empty before pop)
- O(n2) list.pop(0) replaced by slice/index in HDF5 import
- OperationSettingPropagate crash fix for widget names with spaces
- TextLabel click selection bounds expansion
- Graph draw order (annotations last)
- Zoom across tabs (delegate pattern)
- Ternary fill geometry fix
- Duplicate file detection
- Bracket crash fix on drag without valid axes
- slotSelectMode KeyError fix for unknown actions
- Fit NaN crash prevention
- Force render after document load (fixes blank screen on open)

### Build
- PyInstaller spec optimized: strip=True, unnecessary DLLs excluded (opengl32sw 20MB, Qt6Pdf 5MB, SSL 4MB)
- Unnecessary Qt plugins removed (qoffscreen, qminimal, qtga, qwbmp, qicns)
- Build size: 198 MB -> 168 MB (-15%)
- Inno Setup installer with LZMA2 compression: 45 MB
- File associations for .vsz and .vszh5

### Security (Full audit — 22 items resolved)
- **CRITICAL**: Remote protocol rewritten from pickle+eval to JSON + whitelist command dispatch
- **CRITICAL**: MIME clipboard eval() replaced with ast.literal_eval() + type validation
- **CRITICAL**: Render thread isolation via QReadWriteLock on Document (concurrent readers, exclusive writers)
- **HIGH**: Console safe mode enabled by default — only documented commands allowed, arbitrary exec() blocked
- **HIGH**: Feedback/QSettings eval() replaced with ast.literal_eval() safe helpers
- **HIGH**: Bytecode cache (.vszc) hardened — reject symlinks, atomic write via tempfile+os.replace
- **HIGH**: Path traversal prevented in findFileOnImportPath — realpath + commonpath validation
- **HIGH**: eval() lambda in minuit fitting replaced with normal callable
- **HIGH**: Division by zero guard when dof==0 (N.nan fallback)
- **HIGH**: Empty array guard in image.py trimGrid/trimEdge
- **MEDIUM**: All bare excepts (13+) replaced with except Exception: (0 remaining)
- **MEDIUM**: JSON import wrapped in try/except with user-friendly error messages
- **MEDIUM**: Signal disconnect before reconnect in datasetbrowser (prevents duplicate calls)
- **MEDIUM**: QTimer/QMenu created with explicit parent (prevents ownership leaks)
- **MEDIUM**: Import moved from draw path to module level in fit.py
- **LOW**: Band settings (bandXData, etc.) marked readonly=True

### Code Quality
- Unused imports cleaned
- Strict main thread / render thread separation in fit widget
- No settings writes from render thread
- Debug logging in OperationSettingPropagate for path resolution failures

---

*Plotex is based on Veusz 4.2 by Jeremy Sanders.*
*Extended by M. Ignacio Monge Garcia.*
