# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for RoadSight
#
# Build with:
#   pyinstaller RoadSight.spec --clean --noconfirm
#
# Output: dist/RoadSight.app  (macOS)  or  dist/RoadSight/  (Windows/Linux)

from PyInstaller.utils.hooks import collect_all, collect_data_files

# ── Data files bundled into the read-only part of the app ─────────────────────
datas = [
    ('src/background.jpeg',        '.'),
    ('models',                     'models'),
    ('dataset',                    'dataset'),
    ('userguide',                  'userguide'),
    ('exiftool.exe',               '.'),
    ('exiftool_files',             'exiftool_files'),
]

# ultralytics ships YAML configs, default weights metadata, etc.
ul_datas, ul_binaries, ul_hidden = collect_all('ultralytics')
datas += ul_datas

# imageio_ffmpeg bundles its own ffmpeg binary — include it so the app
# works without a system ffmpeg install.
ff_datas, ff_binaries, ff_hidden = collect_all('imageio_ffmpeg')
datas += ff_datas

# ── Hidden imports PyInstaller won't detect automatically ─────────────────────
hiddenimports = [
    # Our own modules
    'detect',
    'detection_settings',
    'gps_from_gpx',
    'gps_from_mov',
    'video_convert',
    'roadsight_paths',
    'train',
    'retrain_window',
    # PySide6 multimedia (loaded at runtime via Qt plugin system)
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
    # Common ultralytics / torch transitive imports
    'pkg_resources.py2_warn',
    'PIL._tkinter_finder',

    'matplotlib',
    'matplotlib.pyplot',
    'matplotlib.backends.backend_agg',
] + ul_hidden + ff_hidden

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    ['src/app.py'],
    pathex=['src'],
    binaries=ul_binaries + ff_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'IPython',
        'jupyter',
        'notebook',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RoadSight',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,           # no terminal window (windowed GUI app)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RoadSight',
)

# macOS .app bundle
app = BUNDLE(
    coll,
    name='RoadSight.app',
    icon=None,
    bundle_identifier='com.roadsight.app',
    info_plist={
        'CFBundleName': 'RoadSight',
        'CFBundleDisplayName': 'RoadSight',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '11.0',
        # Allow access to user's Documents folder (needed to write results)
        'NSDocumentsFolderUsageDescription': 'RoadSight saves detection results to your Documents folder.',
    },
)
