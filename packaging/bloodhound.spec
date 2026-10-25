# PyInstaller recipe for a single-file, windowed Bloodhound executable.
#
#   pip install -r requirements-dev.txt
#   pyinstaller packaging/bloodhound.spec
#
# The result is dist/Bloodhound.exe on Windows (dist/Bloodhound elsewhere).

from pathlib import Path

ROOT = Path(SPECPATH).parent
ASSETS = ROOT / "bloodhound" / "assets"

a = Analysis(
    [str(ROOT / "bloodhound" / "__main__.py")],
    pathex=[str(ROOT)],
    datas=[(str(ASSETS), "bloodhound/assets")],
    excludes=["pytest", "PIL"],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Bloodhound",
    icon=str(ASSETS / "bloodhound.ico"),
    console=False,
    upx=False,
)
