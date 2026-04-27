# -*- mode: python -*-

# Plotex PyInstaller spec — optimized for size and startup speed

import glob
import os
import os.path

# Resolve project root relative to this spec file so builds work from any cwd
_spec_dir = os.path.dirname(os.path.abspath(SPEC)) if 'SPEC' in globals() \
    else os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() \
    else os.path.abspath('.')
_project_root = os.path.abspath(os.path.join(_spec_dir, '..'))
if os.path.isdir(_project_root) and os.path.exists(
        os.path.join(_project_root, 'VERSION')):
    os.chdir(_project_root)

icon = os.path.abspath('icons\\plotex.ico')

# Hidden imports are referenced lazily by widgets / fit / qqplot /
# dataimport, so PyInstaller's static analysis misses them. scipy is
# required (fit, qqplot, statistics widgets); iminuit / astropy / h5py
# are optional — if not installed in the build environment, skip them
# and the corresponding features (Minuit fitting, FITS, HDF5) are simply
# absent from the bundled exe.
_required_hidden = [
    # File format libraries used by importers
    'yaml', 'openpyxl', 'xlrd',
    'odf', 'odf.opendocument', 'odf.table', 'odf.text',
    # Scientific stack — required
    'scipy', 'scipy.stats', 'scipy.optimize', 'scipy.special',
    'scipy.interpolate', 'scipy.signal', 'scipy.integrate',
]
_optional_hidden = [
    'iminuit',
    'astropy', 'astropy.io.fits',
    'h5py', 'h5py._hl', 'h5py._hl.files',
]
_hidden = list(_required_hidden)
import importlib.util as _ilu
for _name in _optional_hidden:
    _root = _name.split('.')[0]
    if _ilu.find_spec(_root) is not None:
        _hidden.append(_name)
    else:
        print('SKIP optional hidden import (not installed):', _name)

analysis = Analysis(
    ['..\\veusz\\veusz_main.py'],
    hiddenimports=_hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # ML/AI frameworks
        'torch', 'torchvision', 'torchaudio',
        'tensorflow', 'keras',
        # Heavy data libraries (not needed)
        'pandas',
        'matplotlib',
        'numba', 'llvmlite',
        'sympy',
        # Image processing (Qt handles images)
        'PIL', 'Pillow',
        # XML/HTML (not needed)
        'lxml', 'bs4', 'html5lib',
        # Windows COM
        'win32com', 'pythoncom', 'pywintypes',
        # Crypto/SSL (not needed for plotting)
        'cryptography', 'ssl', '_ssl',
        # Web/network
        'fsspec',
        'jinja2',
        'pygments',
        'certifi',
        'requests', 'urllib3', 'httpx', 'aiohttp',
        # System
        'psutil',
        'setuptools', 'pkg_resources',
        'distutils',
        # Testing
        'pytest', 'doctest',
        'test', '_testcapi', '_testinternalcapi',
        # IPython/Jupyter
        'IPython', 'jupyter', 'notebook', 'ipykernel',
        # Unused scipy submodules
        'scipy.io',
        # Misc
        'tkinter', '_tkinter',
        'smtplib',
        'xmlrpc', 'http.server',
        'pdb', 'profile', 'cProfile',
    ])

pyz = PYZ(
    analysis.pure,
    cipher=None,
)

exe = EXE(
    pyz,
    analysis.scripts,
    exclude_binaries=True,
    name='plotex.exe',
    debug=False,
    strip=True,
    upx=True,
    console=False,
    contents_directory='.',
    icon=icon)

# add necessary documentation, licence
data_glob = [
    'VERSION',
    'COPYING',
    'icons/*.png',
    'icons/*.ico',
    'icons/*.svg',
    'examples/*.vsz',
    'examples/*.dat',
    'examples/*.csv',
    'examples/*.py',
    'ui/*.ui',
    'ui/*.qss',
]

datas = analysis.datas
for pattern in data_glob:
    for fn in glob.glob(pattern):
        datas.append((fn, fn, 'DATA'))

# Note: previously this section appended ('embed.py', 'veusz/embed.py', ...)
# and ('__init__.py', 'veusz/__init__.py', ...) — but those source paths
# pointed at the project root, where neither file exists. They live in
# veusz/. PyInstaller already bundles the veusz package via the Analysis
# entrypoint, so no manual copy is needed.

# exclude unnecessary binaries
exclude_binaries = {
    # Qt modules not needed for scientific plotting
    'Qt6Pdf.dll',
    'Qt6PdfWidgets.dll',
    'Qt6OpenGL.dll',
    'Qt6OpenGLWidgets.dll',
    'Qt6Quick.dll',
    'Qt6Qml.dll',
    'Qt6QmlModels.dll',
    'Qt6VirtualKeyboard.dll',
    'Qt6WebChannel.dll',
    'Qt6WebEngineCore.dll',
    'Qt6WebEngineWidgets.dll',
    'Qt6Multimedia.dll',
    'Qt6MultimediaWidgets.dll',
    'Qt6Positioning.dll',
    'Qt6DBus.dll',
    'Qt6Designer.dll',
    'Qt6Test.dll',
    # Software OpenGL renderer (20 MB!)
    'opengl32sw.dll',
    # SSL (not needed for local plotting app)
    'libcrypto-1_1.dll',
    'libcrypto-3.dll',
    'libcrypto-3-x64.dll',
    'libssl-1_1.dll',
    'libssl-3.dll',
    'libssl-3-x64.dll',
    # Qt plugins not needed
    'qoffscreen.dll',
    'qminimal.dll',
    'qtuiotouchplugin.dll',
    'qtga.dll',
    'qwbmp.dll',
    'qicns.dll',
}
analysis.binaries[:] = [
    b for b in analysis.binaries
    if os.path.basename(b[0]) not in exclude_binaries
]

coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.zipfiles,
    datas,
    strip=True,
    upx=True,
    upx_exclude=['vcruntime140.dll', 'python311.dll',
                  'MSVCP140.dll', 'MSVCP140_1.dll', 'MSVCP140_2.dll'],
    name='plotex_main'
)
