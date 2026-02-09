# -*- coding: utf-8 -*-
"""
build.py - iperf_manager 배포 빌드 스크립트

Usage:
    python build.py              # agent + dashboard 둘 다 빌드
    python build.py agent        # agent만 빌드
    python build.py dashboard    # dashboard만 빌드
    python build.py --onefile    # onefile 모드만
    python build.py --onedir     # onedir 모드만 (기본: 둘 다)
    python build.py --no-zip     # zip 압축 생략
"""
import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASE_DIR = ROOT / 'release'

# Version from constants
sys.path.insert(0, str(ROOT))
from core.constants import AGENT_VERSION, DASHBOARD_VERSION

TARGETS = {
    'agent': {
        'spec': ROOT / 'agent.spec',
        'name': 'iperf3-agent',
        'version': AGENT_VERSION,
    },
    'dashboard': {
        'spec': ROOT / 'dashboard.spec',
        'name': 'iperf3-dashboard',
        'version': DASHBOARD_VERSION,
    },
}


def run_pyinstaller(spec: Path, extra_args: list[str] | None = None):
    """Run PyInstaller with the given spec file."""
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', str(spec)]
    if extra_args:
        cmd.extend(extra_args)
    print(f'  CMD: {" ".join(cmd)}')
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print(f'  [FAIL] PyInstaller exited with code {result.returncode}')
        return False
    return True


def make_zip(src_dir: Path, zip_path: Path):
    """Create a zip archive from src_dir."""
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(src_dir.rglob('*')):
            if f.is_file():
                arcname = f.relative_to(src_dir.parent)
                zf.write(f, arcname)
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f'  ZIP: {zip_path.name} ({size_mb:.1f} MB)')


def build_target(name: str, modes: list[str], do_zip: bool):
    """Build a single target (agent or dashboard)."""
    info = TARGETS[name]
    spec = info['spec']
    app_name = info['name']
    version = info['version']

    if not spec.exists():
        print(f'  [SKIP] {spec.name} not found')
        return False

    print(f'\n{"="*60}')
    print(f'  Building {app_name} v{version}')
    print(f'{"="*60}')

    success = True
    dist_base = ROOT / 'dist'
    build_base = ROOT / 'build'

    for mode in modes:
        print(f'\n  --- {mode} mode ---')

        if mode == 'onedir':
            ok = run_pyinstaller(spec)
            if not ok:
                success = False
                continue

            src = dist_base / app_name
            if not src.exists():
                print(f'  [FAIL] {src} not found after build')
                success = False
                continue

            dest = RELEASE_DIR / f'{app_name}_v{version}'
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
            print(f'  [OK] onedir -> {dest.relative_to(ROOT)}')

            if do_zip:
                zip_path = RELEASE_DIR / f'{app_name}_v{version}.zip'
                make_zip(dest, zip_path)

        elif mode == 'onefile':
            ok = run_pyinstaller(spec, ['--onefile'])
            if not ok:
                success = False
                continue

            # onefile produces exe directly in dist/
            exe_name = f'{app_name}.exe'
            src_exe = dist_base / exe_name
            if not src_exe.exists():
                print(f'  [FAIL] {src_exe} not found after build')
                success = False
                continue

            dest_exe = RELEASE_DIR / f'{app_name}_v{version}.exe'
            shutil.copy2(src_exe, dest_exe)
            print(f'  [OK] onefile -> {dest_exe.relative_to(ROOT)}')

    # Clean up PyInstaller temp
    for d in [build_base / app_name, dist_base / app_name]:
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)

    return success


def main():
    parser = argparse.ArgumentParser(description='iperf_manager build script')
    parser.add_argument('targets', nargs='*', default=[],
                        help='Build targets: agent, dashboard (default: both)')
    parser.add_argument('--onefile', action='store_true',
                        help='Build onefile only')
    parser.add_argument('--onedir', action='store_true',
                        help='Build onedir only')
    parser.add_argument('--no-zip', action='store_true',
                        help='Skip zip compression')
    args = parser.parse_args()

    # Determine targets
    targets = [t for t in args.targets if t]
    for t in targets:
        if t not in TARGETS:
            parser.error(f'unknown target: {t} (choose from {", ".join(TARGETS)})')
    if not targets:
        targets = ['agent', 'dashboard']

    # Determine modes
    if args.onefile and not args.onedir:
        modes = ['onefile']
    elif args.onedir and not args.onefile:
        modes = ['onedir']
    else:
        modes = ['onedir', 'onefile']

    do_zip = not args.no_zip

    # Prepare release directory
    RELEASE_DIR.mkdir(exist_ok=True)

    print(f'Targets: {", ".join(targets)}')
    print(f'Modes:   {", ".join(modes)}')
    print(f'ZIP:     {"Yes" if do_zip else "No"}')
    print(f'Output:  {RELEASE_DIR.relative_to(ROOT)}/')

    all_ok = True
    for target in targets:
        if not build_target(target, modes, do_zip):
            all_ok = False

    # Summary
    print(f'\n{"="*60}')
    print(f'  BUILD {"COMPLETE" if all_ok else "FAILED"}')
    print(f'{"="*60}')

    if RELEASE_DIR.exists():
        print(f'\n  Output files:')
        for f in sorted(RELEASE_DIR.iterdir()):
            if f.is_file():
                size = f.stat().st_size / (1024 * 1024)
                print(f'    {f.name}  ({size:.1f} MB)')
            elif f.is_dir():
                count = sum(1 for _ in f.rglob('*') if _.is_file())
                print(f'    {f.name}/  ({count} files)')

    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
