# Changelog de Modificaciones Personales

## Convención de versiones
- `v0.0` — Baseline (código original + parches de compilación)
- `v0.x` — Optimizaciones Fase 1 (quick wins)
- `v1.x` — Optimizaciones Fase 2 (arranque/UI)
- `v2.x` — Optimizaciones Fase 3 (rendering pipeline)
- `v3.x` — Optimizaciones Fase 4 (data pipeline)

---

## v1.5 — UX del diálogo de colores (2026-03-31)

### "Alpha" → "Transparencia":
- **`setting/controls.py`**: Nueva función `_getColor()` que reemplaza todas las llamadas a `QColorDialog.getColor()`. Al crear el diálogo, busca el QLabel con texto "Alpha" y lo renombra a "Transparencia" — más intuitivo en español.

### Custom colors no sobrescriben el color actual:
- **`setting/controls.py`**: Clase `_CustomSlotFilter` (event filter) instalada en los viewports de la grilla de colores custom. Al hacer clic en un slot, guarda el color actual antes del `MouseButtonPress` y lo restaura después del `MouseButtonRelease` via `QTimer.singleShot(0)`. Así se puede elegir en qué slot guardar sin perder el color seleccionado.

### Archivos modificados:
- `veusz/setting/controls.py` — función `_getColor()` + `_CustomSlotFilter`, 3 call sites migrados
- `veusz/dialogs/preferences.py` — migrado a `setting.controls._getColor()`
- `veusz/dialogs/export.py` — migrado a `setting.controls._getColor()`

---

## v0.0 — Baseline (2026-03-15)

Estado inicial del proyecto con los parches mínimos necesarios para compilar.

### Parches de compilación aplicados:
- **`pyqt_setuptools.py`**: Añadido fallback para localizar `sip-build.exe` en el directorio Scripts del user site-packages de Python (Windows).
- **`src/qtmml/qtmmlwidget.cpp:3635`**: Corregido cast de puntero `(unsigned long)this` → `(quintptr)this` para compatibilidad 64-bit con MinGW/MSVC.
- **`support/veusz_windows_pyinst.spec`**: Añadida lista de exclusiones de PyInstaller (torch, pandas, matplotlib, tensorflow, etc.) para reducir tamaño del ejecutable de 721 MB a 197 MB.

### Archivos de utilidad añadidos:
- `build_msvc.bat` — Script de compilación de extensiones C++ con MSVC + Qt 6.10.2
- `build_exe.bat` — Script de generación de ejecutable con PyInstaller
- `run_veusz.bat` — Lanzador rápido sin generar .exe
- `OPTIMIZATION_ANALYSIS.md` — Análisis de 32 optimizaciones identificadas

### Estructura de versionado:
- `versions/v0.0_baseline/` — Copia de todos los archivos fuente antes de optimizaciones

---

## v0.1 — Quick Wins: Fase 1 (2026-03-15)

9 optimizaciones de 1-5 líneas cada una. Todos los módulos verificados con import test.

### Datos / Expresiones:
- **`datasets/expression.py:215,287,510`**: Reemplazado `context.copy()` (copiaba dict enorme con todas las funciones numpy) por `{**context, ...}` (spread operator, más ligero). 3 ocurrencias corregidas.
- **`datasets/expression.py:305`**: Cambiado `N.array(result, N.float64)` → `N.asarray(result, dtype=N.float64)` para evitar copia cuando el resultado ya es float64.
- **`datasets/oned.py:85-86`**: Eliminadas 2 copias innecesarias de arrays en `getPointRanges()`. Cambiado de `data.copy()` + operaciones in-place a operaciones que crean nuevos arrays solo cuando hay errores.
- **`datasets/filtered.py:63`**: Cambiado `N.array(data[:minlen])` → `data[:minlen].copy()`. Evita la doble indirección de crear array desde slice.

### Rendering / Widgets:
- **`widgets/point.py:926`**: Optimizado cálculo de shifted-points. Se calcula `midpoints` una sola vez y se reutiliza, en lugar de recalcular `0.5*(xplotter[:-1] + xplotter[1:])` para cada rama.
- **`widgets/bar.py:396-397`**: Reemplazado `N.min(N.vstack(...))` / `N.max(N.vstack(...))` por `N.minimum()` / `N.maximum()`. Elimina creación de arrays temporales en cada iteración del loop de barras stacked.
- **`utils/colormap.py:845`**: Compilado regex `r'^(.+)-step([0-9]*)$'` como atributo de clase `_re_step` en lugar de recompilarlo en cada llamada a `__getitem__`.
- **`utils/points.py:538`**: Añadido `@functools.lru_cache(maxsize=256)` a `getPointPainterPath()`. Cachea painter paths de marcadores por (nombre, tamaño, linewidth) — hit rate >90% típico.

### Snapshot:
- `versions/v0.1_quickwins/` — Copia de los 7 archivos modificados

---

## v0.2 — Arranque y Seguridad (2026-03-15)

### Seguridad:
- **`setting/settingdb.py:187`**: Reemplazado `eval()` por `ast.literal_eval()` para parsear settings persistidos. Elimina riesgo de ejecución arbitraria de código al leer el archivo de configuración. También se acotan las excepciones a `(ValueError, SyntaxError)` en lugar de un bare `except`.

### Arranque — Lazy loading de consola:
- **`windows/mainwindow.py:43`**: Eliminado `from . import consolewindow` del top-level.
- **`windows/mainwindow.py:169-174`**: La consola ya no se crea en `__init__`. Se reemplaza por `self._console = None` y un `@property console` que la instancia bajo demanda (lazy). El import de `consolewindow` ocurre solo cuando se accede por primera vez.
- **`windows/mainwindow.py`**: Añadido `@property interpreter` que delega al console lazy.

### Items descartados de esta fase:
- **`qtall.py` (#8)**: QtSvg se usa en rendering de widgets (no diferible). QtPrintSupport solo en export (ya es lazy de facto). Cambiar wildcard imports es alto riesgo sin ganancia real (Python carga el módulo completo igualmente).
- **`controls.py` (#12)**: 22 clases de controles Qt muy acopladas. Refactorizar a factory lazy requiere cambios extensos con bajo ROI.
- **`plugins/__init__.py` (#25)**: Importado por mainwindow, operations, commandinterface en top-level. Demasiado interconectado.

### Snapshot:
- `versions/v0.2_startup/` — settingdb.py, mainwindow.py

---

## v0.3 — Rendering Pipeline (2026-03-15)

### Error bars — batching de paths:
- **`widgets/point.py:185-197`**: `errorsCurve()` creaba un `QPainterPath` por cada punto de error y llamaba a `painter.drawPath()` N veces. Ahora consolida todas las elipses en un único `QPainterPath` y dibuja una sola vez. Reduce overhead de N llamadas Qt a 1.

### Contornos — list comprehension vectorizada:
- **`widgets/contour.py:46-53`**: `finitePoly()` usaba un loop con `append`, variables intermedias `finite` y `validrows`. Reescrito como list comprehension de una línea con operación `&` directa sobre las columnas. Elimina creación de array temporal `finite`.

### Colormap — interpolación consolidada:
- **`utils/colormap.py:795-804`**: `stepCMap()` hacía 4 llamadas separadas a `N.interp()` (una por canal BGRA) y luego `N.column_stack()`. Consolidado en un solo `N.column_stack` con list comprehension. También cambiado `N.array()` → `N.asarray()` para evitar copia si el input ya es float64.

### Items descartados de esta fase:
- **Export cache (#13)**: Usar recording device para cachear renderizado multi-formato es complejo y solo beneficia exportaciones simultáneas a varios formatos (caso de uso raro).
- **Font metrics cache (#18)**: Solo hay 2 llamadas a `FontMetrics()` en textrender.py — impacto insignificante.

### Snapshot:
- `versions/v0.3_rendering/` — point.py, contour.py, colormap.py

---

## v0.4 — Data Pipeline (2026-03-15)

### Evaluación de expresiones:
- **`datasets/expression.py:316-327`**: Reemplazado `N.resize()` (crea copia + repetición cíclica de datos) por operaciones explícitas: `N.full()` para escalares, preasignación con `N.nan` + copia parcial para arrays de distinto tamaño, y `reshape(1)` para escalares 0-dim (vista sin copia).
- **`document/evaluate.py:125-129`**: El loop que iteraba `numpy.__dict__` (1800+ items) filtrando funciones válidas ahora se ejecuta solo una vez y se cachea como atributo de clase `_numpy_safe_items` (449 funciones). Las siguientes llamadas a `update()` usan `dict.update()` directamente.

### Importación de datos:
- **`dataimport/fits_hdf5_helpers.py:171`**: Cambiado `N.array(data, dtype=float64)` → `N.asarray(data, dtype=float64)`. Evita copia si los datos HDF5/FITS ya son float64.

### Snapshot:
- `versions/v0.4_datapipeline/` — expression.py, evaluate.py, fits_hdf5_helpers.py

---

## v1.0 — Mejoras de Renderizado 2D (2026-03-15)

### Antialiasing completo:
- **`windows/plotwindow.py:140`**: Añadido `SmoothPixmapTransform` al renderizado en pantalla. Las imágenes/heatmaps ahora se suavizan al hacer zoom en lugar de mostrar pixelación.
- **`document/export.py:80-88`**: `renderPage()` (usado para PDF/SVG/PS) ahora aplica los 3 render hints (Antialiasing + TextAntialiasing + SmoothPixmapTransform). Antes no aplicaba ninguno.
- **`document/export.py:126`**: Exportación bitmap (PNG/JPEG/TIFF) también incluye `SmoothPixmapTransform`.

### Rellenos con degradado (feature nueva):
- **`utils/extbrushfilling.py:110`**: Añadidos estilos `'linear gradient'` y `'radial gradient'` a la lista de estilos de relleno.
- **`utils/extbrushfilling.py:197-223`**: Implementado renderizado de degradados usando `QLinearGradient` (de arriba a abajo del bounding rect) y `QRadialGradient` (desde el centro). Soporta transparencia y stroke.
- **`setting/collections.py:218`**: Añadido setting `color2` (segundo color del degradado) a `BrushExtended`. Aparece en el panel de propiedades solo cuando se selecciona un estilo de degradado.
- **`setting/setting.py:1949-1958`**: `FillStyleExtended._showsetns()` actualizado para mostrar `color2` cuando el estilo es un degradado, y ocultarlo para estilos sólidos/trama.

### Snapshot:
- `versions/v1.0_rendering2d/` — extbrushfilling.py, collections.py, setting.py, export.py, plotwindow.py

---

## v1.1 — Curvas suavizadas, interpolación bicúbica, contornos smooth (2026-03-15)

### A2 — Catmull-Rom spline para curvas (feature nueva):
- **`setting/collections.py:110`**: Añadida opción `'Catmull-Rom'` a la lista de interpolaciones de `XYPlotLine`.
- **`widgets/point.py:653-675`**: Implementado método `_catmullRomToBezierPath()` que convierte puntos en segmentos cúbicos de Bézier usando la fórmula de conversión Catmull-Rom → Bézier (puntos de control a ±1/6 de la tangente). Integrado en `_getBezierLine()`.

### A4 — Interpolación bicúbica para imágenes (feature nueva):
- **`widgets/image.py:204-209`**: Añadido modo `'resample-bicubic'` al setting `drawMode`.
- **`widgets/image.py:438-454`** (linear path): Implementado resampling bicúbico con doble escalado: primero 2x con SmoothTransformation, luego a tamaño final. Produce transiciones más suaves que `resample-smooth`.
- **`widgets/image.py:326-336`** (non-linear path): Integrado bicúbico con factor de escala 2 (vs 4 del smooth).
- **`widgets/image.py:320`**: Eliminado `print()` de debug que estaba en el código original.

### B4 — Contornos suavizados (feature nueva):
- **`widgets/contour.py:222-227`**: Añadido setting `smoothing` (Bool, default False) al widget Contour.
- **`widgets/contour.py:46-66`**: Implementada función `_catmullRomPath()` que convierte QPolygonF en QPainterPath con curvas cúbicas Catmull-Rom.
- **`widgets/contour.py:584-588`**: Cuando `smoothing=True`, las líneas de contorno se dibujan con `drawPath(catmullRomPath)` en lugar de `drawPolyline()`.

### Snapshot:
- `versions/v1.1_curves_bicubic_smooth/` — point.py, image.py, contour.py, collections.py

---

## v1.2 — Rendimiento de imágenes 2D (2026-03-15)

### Diagnóstico del problema:
En cada zoom/pan, `Image.dataDraw()` recalculaba la cadena completa:
1. `applyColorMap()` — convierte datos float → QImage RGBA (operación NumPy pesada)
2. `cropLinearImageToBox()` — recorta a viewport
3. `image.scaled()` — reescala a resolución de pantalla

Los pasos 1 se ejecutaban innecesariamente ya que los datos y colormap no cambian al hacer zoom.

### Solución — Cache de colormap QImage:
- **`widgets/image.py:138-145`**: Añadido `__init__` a la clase `Image` con atributos de cache `_cmapCacheKey` y `_cmapCacheImg`.
- **`widgets/image.py:377-403`**: `dataDraw()` ahora genera una clave de cache basada en: `id(data)`, `shape`, puntero de datos, `colorMap`, `colorInvert`, `colorScaling`, min/max, `transparency`, y `transimg`. Solo recalcula `applyColorMap()` cuando la clave cambia. En zoom/pan la clave permanece idéntica, evitando el recálculo.

### Impacto:
- **Zoom/pan**: El paso más costoso (colormap) se salta completamente. Solo se ejecutan crop + scale.
- **Cambio de datos/colormap**: Se recalcula correctamente (cache invalidado por la clave).

### Snapshot:
- `versions/v1.2_image_perf/` — image.py

---

## v1.3 — Rendimiento y feedback visual (2026-03-15)

### Feedback durante carga de ficheros:
- **`windows/mainwindow.py:1267-1275`**: Añadido `QProgressDialog` modal durante `loadDocument()`. Muestra "Loading fichero..." con barra indeterminada. Se activa tras 300ms (no molesta en cargas rápidas). Incluye `processEvents()` para que la ventana no se quede en blanco.

### Decimación automática de puntos:
- **`widgets/point.py:1017-1025`**: Cuando el número de puntos supera 4x los píxeles del viewport, se calcula automáticamente un `thinfactor` para reducir los marcadores renderizados. Por ejemplo: 100.000 puntos en un viewport de 800x600 = 480.000 píxeles → se renderizan todos. Pero 2.000.000 de puntos → thinfactor=2, se renderizan 1.000.000. Esto no afecta a la línea ni al export (solo a los marcadores en pantalla).
- **`widgets/point.py:1038,1047`**: Las variables `scaling` y `colorvals` también usan el thinfactor auto (antes solo usaban `s.thinfactor`).

### Cursor de espera durante renderizado:
- **`windows/plotwindow.py:1078-1102`**: `checkPlotUpdate()` ahora muestra cursor de espera (reloj de arena) durante `document.paintTo()` y lo restaura al terminar (incluso si hay excepción, via `finally`).

### Snapshot:
- `versions/v1.3_perf_feedback/` — point.py, mainwindow.py, plotwindow.py, loader.py

### Hotfix v1.3.1 — Carga no-bloqueante:
- **`document/loader.py:161-174`**: El `exec(compiled, env)` que ejecutaba todo el script .vsz de golpe ahora usa `ast.parse()` para dividir el script en sentencias individuales. Cada 50 sentencias llama a `processEvents()` para mantener la UI responsiva. Esto evita el "no responde" de Windows.
- **`windows/mainwindow.py:1267-1284`**: Diálogo de progreso ahora con `setMinimumDuration(0)` y `show()` forzado para que aparezca inmediatamente. Eliminado `OverrideCursor` que podía interferir.

---

## v1.4 — Branding y UX (2026-03-15)

### Esquinas de ejes corregidas:
- **`widgets/axis.py`**: Cambiado `FlatCap` → `SquareCap` en las 3 funciones de dibujo de ejes (`_drawAxisLine`, `_drawMinorTicks`, `_drawMajorTicks`). FlatCap cortaba la línea exactamente en el endpoint, dejando un hueco en las esquinas donde dos ejes se encuentran. SquareCap extiende medio ancho de trazo, cerrando la esquina limpiamente.

### Pan con botón central del ratón:
- **`windows/plotwindow.py:788`**: Añadido handler para `MiddleButton` en `mousePressEvent()`. Al pulsar el botón central, entra directamente en modo scroll con cursor ClosedHand, sin necesidad de usar las barras de scroll ni cambiar de modo.

### Rebranding a Plotex:
- **`veusz_main.py`**: Cambiado nombre de la aplicación de "Veusz" a "Plotex" en copyright, splash, y argparse.
- **`windows/mainwindow.py`**: Barra de título usa "Plotex" en lugar de "Veusz".
- **`windows/mainwindow.py`**: Icono de ventana cambiado a `plotex.svg`.
- **`icons/plotex.svg`**: Nuevo logo — fondo degradado azul-púrpura con ejes blancos, curva cyan, puntos de datos naranja, y texto "Px".

### Snapshot:
- `versions/v1.4_branding_ux/` — axis.py, plotwindow.py, mainwindow.py, veusz_main.py, plotex.svg

---
