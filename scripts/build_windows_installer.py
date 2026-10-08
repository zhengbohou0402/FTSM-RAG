"""
Build the Windows installer used for GitHub Releases.

The release flow is:
  1. Build the React frontend.
  2. Build the Python backend with PyInstaller.
  3. Copy the PyInstaller onedir output into Tauri resources.
  4. Build the Tauri NSIS setup executable.

Run from the repository root:
    python scripts/build_windows_installer.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP_DIR = ROOT / "desktop"
TAURI_DIR = DESKTOP_DIR / "src-tauri"
PYINSTALLER_APP_DIR = ROOT / "dist" / "FTSM-RAG"
TAURI_BACKEND_DIR = TAURI_DIR / "python-backend"
TAURI_CONF = TAURI_DIR / "tauri.conf.json"
NSIS_DIR = TAURI_DIR / "target" / "release" / "bundle" / "nsis"

REQUIRED_BACKEND_PATHS = (
    "FTSM-RAG.exe",
    "_internal",
    "_internal/web",
    "_internal/config",
    "_internal/prompts",
)


def run(command: list[str], cwd: Path) -> None:
    print(f"> {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def executable(name: str) -> str:
    found = shutil.which(name) or shutil.which(f"{name}.cmd") or shutil.which(f"{name}.exe")
    if not found:
        raise RuntimeError(f"Required executable not found on PATH: {name}")
    return found


def pyinstaller_command() -> list[str]:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        return [executable("pyinstaller")]
    return [sys.executable, "-m", "PyInstaller"]


def load_product_name_and_version() -> tuple[str, str]:
    config = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    return config["productName"], config["version"]


def default_output_path() -> Path:
    product, version = load_product_name_and_version()
    return ROOT / "dist" / f"{product}-{version}-windows-x64-setup.exe"


def validate_backend_dir(app_dir: Path) -> list[str]:
    missing = [rel for rel in REQUIRED_BACKEND_PATHS if not (app_dir / rel).exists()]
    internal_dir = app_dir / "_internal"
    if internal_dir.exists() and not any(internal_dir.glob("python*.dll")):
        missing.append("_internal/python*.dll")
    return missing


def assert_safe_resource_target(path: Path) -> Path:
    target = path.resolve()
    tauri_root = TAURI_DIR.resolve()
    if target == tauri_root or tauri_root not in target.parents:
        raise RuntimeError(f"Refusing to remove unexpected path: {target}")
    return target


def copy_backend_to_tauri_resources(app_dir: Path, destination: Path) -> None:
    app_dir = app_dir.resolve()
    destination = assert_safe_resource_target(destination)

    missing = validate_backend_dir(app_dir)
    if missing:
        print("Cannot build installer. Missing required PyInstaller files:", file=sys.stderr)
        for item in missing:
            print(f"  - {item}", file=sys.stderr)
        print(
            "Run: python -m PyInstaller --clean --noconfirm ftsm_rag.spec",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(app_dir, destination)


def newest_installer() -> Path:
    installers = sorted(NSIS_DIR.glob("*.exe"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not installers:
        raise RuntimeError(f"No NSIS installer found in {NSIS_DIR}")
    return installers[0]


def copy_installer_to_dist(output: Path) -> Path:
    installer = newest_installer()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if installer.resolve() != output:
        shutil.copy2(installer, output)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the FTSM-RAG Windows setup.exe installer.")
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Reuse the existing desktop/dist folder instead of running npm run build.",
    )
    parser.add_argument(
        "--skip-pyinstaller",
        action="store_true",
        help="Reuse the existing dist/FTSM-RAG PyInstaller output.",
    )
    parser.add_argument(
        "--skip-tauri",
        action="store_true",
        help="Only refresh Tauri resources; do not run npx tauri build.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=default_output_path(),
        help="Where to copy the final setup.exe for GitHub Releases.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.skip_frontend:
        run([executable("npm"), "run", "build"], DESKTOP_DIR)

    if not args.skip_pyinstaller:
        run(pyinstaller_command() + ["--clean", "--noconfirm", "ftsm_rag.spec"], ROOT)

    copy_backend_to_tauri_resources(PYINSTALLER_APP_DIR, TAURI_BACKEND_DIR)

    if args.skip_tauri:
        print(f"Refreshed Tauri backend resources: {TAURI_BACKEND_DIR}")
        return 0

    run([executable("npx"), "tauri", "build", "--bundles", "nsis"], DESKTOP_DIR)
    output = copy_installer_to_dist(args.output)

    print(f"Wrote installer: {output}")
    print("Upload this setup.exe to GitHub Releases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
