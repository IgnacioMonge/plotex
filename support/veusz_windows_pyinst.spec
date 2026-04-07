# -*- mode: python -*-

# Plotex PyInstaller spec — optimized for size and startup speed

import glob
import os.path

icon = os.path.abspath('icons\\plotex.ico')

analysis = Analysis(
    ['..\\veusz\\veusz_main.py'],
    hiddenimports=['yaml', 'openpyxl', 'xlrd', 'odf', 'odf.opendocument', 'odf.table', 'odf.text'],
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

# add API files
datas += [
    ('embed.py', 'veusz/embed.py', 'DATA'),
    ('__init__.py', 'veusz/__init__.py', 'DATA'),
]

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
