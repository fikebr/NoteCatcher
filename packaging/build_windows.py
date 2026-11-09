"""Build a versioned portable Windows folder and ZIP from installed metadata."""

from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image
from PySide6.QtWidgets import QApplication

from notecatcher.about import APP_NAME, APP_VERSION
from notecatcher.icons import app_icon


def main():
    if sys.platform != 'win32':
        raise SystemExit('Build the Windows executable on Windows.')
    root = Path(__file__).resolve().parents[1]
    release_name = f'{APP_NAME}-{APP_VERSION}-windows-x64'
    release_dir = root / 'dist' / release_name
    if release_dir.exists():
        raise SystemExit(f'Build output already exists: {release_dir}. Move it aside before rebuilding.')
    app = QApplication([])
    app.setApplicationName(APP_NAME)
    with tempfile.TemporaryDirectory(prefix='notecatcher-build-') as temporary:
        workspace = Path(temporary)
        png = workspace / 'icon.png'
        ico = workspace / 'NoteCatcher.ico'
        if not app_icon().pixmap(256, 256).save(str(png)):
            raise RuntimeError('Could not render the app icon.')
        with Image.open(png) as image:
            image.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)])
        # Do not let unrelated applications on PATH supply DLLs. Qt uses the
        # Windows ICU API; a third-party Poppler/Conda ICU has different exports.
        environment = os.environ.copy()
        windows = Path(os.environ['SystemRoot'])
        environment['PATH'] = os.pathsep.join([
            str(Path(sys.executable).parent), sys.base_prefix,
            str(windows / 'System32'), str(windows),
        ])
        subprocess.run([
            sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onedir', '--windowed',
            '--noupx', '--name', APP_NAME, '--icon', str(ico),
            '--additional-hooks-dir', str(root / 'packaging/hooks'),
            '--distpath', str(workspace / 'dist'), '--workpath', str(workspace / 'work'),
            '--specpath', str(workspace), str(root / 'packaging/launcher.py'),
        ], cwd=root, env=environment, check=True)
        # Verify before publishing a distributable. This uses synthetic content
        # and isolated state, without reading the user's clipboard or notes.
        subprocess.run([
            str(workspace / 'dist' / APP_NAME / f'{APP_NAME}.exe'),
            '--verify-bundle', str(workspace / 'verification.json'),
        ], cwd=workspace, env=environment, check=True, timeout=45)
        root.joinpath('dist').mkdir(exist_ok=True)
        shutil.copytree(workspace / 'dist' / APP_NAME, release_dir)
        shutil.copy2(workspace / 'verification.json', release_dir / 'BUILD-VERIFICATION.json')
    shutil.copy2(root / 'config.example.toml', release_dir / 'config.example.toml')
    shutil.copy2(root / 'README.md', release_dir / 'README.md')
    (release_dir / 'START-HERE.txt').write_text(
        f'{APP_NAME} {APP_VERSION}\n\n'
        'Double-click NoteCatcher.exe. Find its icon near the Windows clock.\n'
        'Copy content and press Ctrl+Alt+N; Ctrl+Enter saves; Esc discards.\n'
        'Keep the entire folder together, including _internal.\n\n'
        'To choose a permanent notes folder, copy config.example.toml to config.toml\n'
        'beside NoteCatcher.exe, edit notes_dir, then exit and restart the app.\n'
        'Without config.toml, notes default to Documents/NoteCatcher.\n'
        'Recovery and logs remain in your Windows local application-data folder.\n'
        'Python and AutoHotkey do not need to be installed.\n', encoding='utf-8')
    archive = shutil.make_archive(str(root / 'dist' / release_name), 'zip',
                                  root_dir=release_dir.parent, base_dir=release_dir.name)
    print(f'Executable: {release_dir / (APP_NAME + ".exe")}')
    print(f'Portable ZIP: {archive}')


if __name__ == '__main__':
    main()
