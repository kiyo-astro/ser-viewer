"""Replacement for the astropy hook shipped with pyinstaller-hooks-contrib.

The stock hook calls ``collect_submodules("astropy")``, which imports
``astropy.visualization.wcsaxes``.  That module runs
``pytest.importorskip("matplotlib")`` at import time, so on a clean build machine
without matplotlib the whole build aborts with a pytest ``Skipped`` exception.

Everything else here mirrors the stock hook: astropy loads data files, PLY
parser tables and package metadata at runtime, and none of those are found by
static analysis.  Only the submodule collection is narrowed to the sub-packages
SER Viewer actually uses, which also keeps the bundle smaller.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

hiddenimports = (
    collect_submodules("astropy.io")
    + collect_submodules("astropy.utils")
    + collect_submodules("astropy.units")
    + collect_submodules("astropy.constants")
    + collect_submodules("astropy.table")
    + ["astropy.config", "astropy.time", "numpy.lib.recfunctions"]
)

datas = collect_data_files("astropy")

# The unit parser reads *_parsetab.py / *_lextab.py as files, not as modules.
datas += [
    (source, target)
    for source, target in collect_data_files("astropy", include_py_files=True)
    if source.endswith(("_parsetab.py", "_lextab.py"))
]

# astropy 5+ reads its own version out of the installed package metadata.
datas += copy_metadata("astropy")
datas += copy_metadata("numpy")

excludedimports = [
    "astropy.visualization",
    "astropy.cosmology",
    "astropy.modeling",
    "matplotlib",
    "pandas",
    "pytest",
]
