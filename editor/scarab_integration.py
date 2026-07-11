"""Small wrapper for running Scarab catalog generation.

Scarab is FiendishDrWu's standalone catalog generator. The editor treats it as
an optional backend: run it on demand, then point the catalog loader at the
generated folder on the next launch.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
import subprocess

import catalog_source

MINIMUM_SCARAB = "v1.7.4"
DEFAULT_OUTPUT = "jj-catalog"
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class ScarabResult:
    ok: bool
    output_dir: str | None = None
    message: str = ""
    stdout: str = ""
    stderr: str = ""


def _clean_output_name(value: str) -> str:
    out = (value or "").strip().strip('"')
    if not out:
        return DEFAULT_OUTPUT
    if os.path.isabs(out):
        raise ValueError("Scarab output must be a relative folder name.")
    parts = out.replace("\\", "/").split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("Scarab output cannot contain empty, '.', or '..' path parts.")
    return out


def output_dir_for(scarab_exe: str, output_name: str) -> str:
    exe_dir = os.path.dirname(os.path.abspath(scarab_exe))
    return os.path.abspath(os.path.join(exe_dir, _clean_output_name(output_name)))


def _version_tuple(value: str) -> tuple[int, int, int] | None:
    match = re.search(r"\d+(?:\.\d+){1,2}", value or "")
    if not match:
        return None
    parts = [int(part) for part in match.group(0).split(".")]
    return tuple((parts + [0, 0])[:3])


def run_scarab(
    scarab_exe: str,
    mw5_dir: str,
    output_name: str,
    catalog_input_dir: str,
    *,
    build_report: bool = False,
    timeout: int = 180,
) -> ScarabResult:
    """Run Scarab and validate the generated catalog folder."""
    scarab_exe = os.path.abspath((scarab_exe or "").strip().strip('"'))
    mw5_dir = os.path.abspath((mw5_dir or "").strip().strip('"'))
    catalog_input_dir = os.path.abspath((catalog_input_dir or "").strip().strip('"'))

    if not os.path.isfile(scarab_exe):
        return ScarabResult(False, message="Scarab executable was not found.")
    if not os.path.isdir(mw5_dir):
        return ScarabResult(False, message="MW5 game folder was not found.")
    if not catalog_source.is_valid(catalog_input_dir):
        return ScarabResult(False, message="Built-in catalog bundle is not available.")

    try:
        version_proc = subprocess.run(
            [scarab_exe, "--version"],
            cwd=os.path.dirname(scarab_exe),
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ScarabResult(False, message=f"Could not verify the Scarab version: {exc}")

    version_text = (version_proc.stdout or version_proc.stderr or "").strip()
    reported_version = _version_tuple(version_text)
    minimum_version = _version_tuple(MINIMUM_SCARAB)
    assert minimum_version is not None
    if (version_proc.returncode != 0 or reported_version is None
            or reported_version < minimum_version):
        reported_text = ".".join(str(part) for part in reported_version) if reported_version else "unknown"
        return ScarabResult(
            False,
            message=(f"Scarab {MINIMUM_SCARAB} or newer is required; the selected "
                     f"executable reports {reported_text}."),
        )

    try:
        output_name = _clean_output_name(output_name)
    except ValueError as exc:
        return ScarabResult(False, message=str(exc))

    output_dir = output_dir_for(scarab_exe, output_name)
    cmd = [
        scarab_exe,
        "--mw5-dir", mw5_dir,
        "--catalog-input-dir", catalog_input_dir,
        "--output", output_name,
    ]
    if build_report:
        cmd.append("--build-report")

    try:
        proc = subprocess.run(
            cmd,
            cwd=os.path.dirname(scarab_exe),
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=_CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return ScarabResult(False, output_dir, "Scarab timed out.", "", "")
    except OSError as exc:
        return ScarabResult(False, output_dir, f"Could not run Scarab: {exc}", "", "")

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    if proc.returncode != 0:
        msg = f"Scarab exited with code {proc.returncode}."
        detail = (stderr or stdout).strip()
        if detail:
            msg += "\n\n" + detail[-1200:]
        return ScarabResult(False, output_dir, msg, stdout, stderr)

    if not catalog_source.is_valid(output_dir):
        return ScarabResult(
            False,
            output_dir,
            "Scarab ran, but the output folder does not contain a complete catalog set.",
            stdout,
            stderr,
        )

    return ScarabResult(True, output_dir, "Scarab catalog generated successfully.", stdout, stderr)
