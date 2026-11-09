# Development and packaging

See AGENTS.md for project conventions and the technical specification for the design.

Install dependencies with `uv sync`. Run checks with `uv run pytest` and
`uv run ruff check .`. If Dropbox locks temporary test files, use a fresh directory
outside the checkout:

```powershell
uv run pytest --basetemp "$env:TEMP/NoteCatcher-tests-<unique-id>"
```

About uses installed package metadata generated from `project.name`,
`project.version`, and `project.urls.Homepage` in pyproject.toml. Run `uv sync`
after editing these fields and restart the app.

When building with PyInstaller, include `--additional-hooks-dir packaging/hooks`.
The supplied hook collects the package metadata and shared SVG icon. About then
works without a loose pyproject.toml. Alternatively, `--copy-metadata notecatcher`
collects metadata, but the icon must still be collected separately.

Build the portable folder and ZIP on 64-bit Windows with:

```powershell
uv sync --group build
uv run --group build python packaging/build_windows.py
```

Outputs are `dist/NoteCatcher-<version>-windows-x64/NoteCatcher.exe` and a matching
ZIP containing the complete folder. The build script refuses to overwrite an
existing versioned output. Move that output aside before rebuilding it. Build
intermediates use a temporary directory outside Dropbox. The launcher has no
console window. An ICO is generated from the shared SVG for the executable.
The build restricts PATH to Python and Windows directories so unrelated tools
cannot contribute incompatible DLLs (in particular, third-party ICU libraries).
Before publishing the folder or ZIP, the build runs the isolated bundle check;
its JSON report is included as BUILD-VERIFICATION.json.

The frozen app finds config.toml beside the executable regardless of its working
directory. Only config.example.toml is distributed; personal config.toml is not
copied into release archives. Notes default to Documents/NoteCatcher; recovery and
logs retain the existing AppData locations. This is a portable application bundle,
not a mode that stores all user data beside the EXE.

An isolated bundle check is available:

```powershell
& "dist/NoteCatcher-<version>-windows-x64/NoteCatcher.exe" --verify-bundle "$env:TEMP/NoteCatcher-verification/report.json"
```

It writes a JSON report and synthetic notes/screenshots alongside the report. It
checks bundled metadata, icons, About, tray, Markdown images, recovery, local IPC,
native hotkey message dispatch, and failure preservation without reading the real
clipboard or using the user's normal notes or recovery files. It temporarily
registers Ctrl+Alt+Shift+F23 and releases it afterward. Physical keypress behavior
and testing on another Windows machine remain manual checks.

Rebuild the executable after source or metadata changes. Full storage portability,
login startup, code signing and an installer remain optional future work.

Version 0.1.4 was built and its ZIP verified after extraction outside the checkout
with Python removed from PATH on the development Windows machine. All isolated
bundle checks passed. This does not replace testing on another Windows machine.
