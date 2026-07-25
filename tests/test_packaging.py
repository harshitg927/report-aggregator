"""Guards that the package is self-contained (mappings ship inside it) and that
the ``python -m report_aggregator`` subprocess contract works.

These protect the FOSSology consumption path: an installed wheel /
``pip install --target`` layout must find its mapping files without a repo
checkout, and a wrapper must be able to drive the tool via ``-m`` and parse its
``--json`` output.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import report_aggregator
from report_aggregator.engine.mapping import get_mappings_dir, load_mapping
from report_aggregator.formats import SUPPORTED_FORMATS

_PKG_DIR = Path(report_aggregator.__file__).resolve().parent


def test_mappings_dir_is_inside_the_package():
    mappings = get_mappings_dir()
    assert mappings.exists()
    # Must live under the installed package, not at a repo root above src/.
    assert _PKG_DIR in mappings.resolve().parents or mappings.resolve() == _PKG_DIR / "mappings"


def test_all_supported_formats_have_a_bundled_mapping():
    stems = {p.stem for p in get_mappings_dir().glob("*.toml")}
    for fmt in SUPPORTED_FORMATS:
        assert fmt in stems, f"missing bundled mapping for {fmt}"
        # And it actually loads.
        assert load_mapping(fmt).format_name == fmt


def test_module_cli_merge_json(spdx2fckeditor_path, spdx2zlib_path, tmp_path):
    out = tmp_path / "merged.spdx"
    src_root = _PKG_DIR.parent  # the directory containing the report_aggregator package
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "report_aggregator",
            "merge",
            str(spdx2fckeditor_path),
            str(spdx2zlib_path),
            "-o",
            str(out),
            "--json",
        ],
        cwd=tmp_path,  # run from an unrelated cwd
        env={"PYTHONPATH": str(src_root), "PATH": ""},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)  # stdout must be clean JSON
    assert payload["format"] == "spdx2tv"
    assert payload["output_path"] == str(out)
    assert Path(payload["provenance_path"]).exists()
    assert out.exists()
