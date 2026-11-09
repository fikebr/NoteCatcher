# NoteCatcher agent guidance

## Project

NoteCatcher is a Windows desktop clipboard-to-Markdown utility built with Python
3.13+, PySide6 and uv. Read README.md and
docs/NoteCatcher_Technical_Specification.md for the current behavior and roadmap.
Implementation lives in src/notecatcher/ and tests live in tests/.

## Version updates — required

- For every completed user-requested change set that edits project files, bump
  `project.version` in pyproject.toml before finishing. This includes code, UI,
  configuration, documentation, and project tooling changes.
- Bump once per logical request, not once per edited file or intermediate fix.
  Questions, inspections, and running checks alone do not require a version bump.
- Use a patch bump for fixes, small enhancements, and documentation/tooling changes
  (for example, 0.1.0 → 0.1.1). Use a minor bump for substantial new functionality;
  reserve major bumps for intentionally incompatible releases.
- Keep pyproject.toml as the version source of truth. About reads installed package
  metadata; do not hard-code another version in application code.
- Run `uv sync` after changing the version so uv.lock and local installed metadata
  match. Rebuild packaged executables when preparing a release.
- Mention the resulting version in the final change report.

## Implementation expectations

- Preserve unsaved drafts on storage failures. Clear recovery durably before clearing
  the editor. Never overwrite existing notes or delete unrelated user files.
- The explicit cancel shortcut (Esc by default) clears the draft and hides without
  saving or confirmation. File → Discard draft requires confirmation. Closing the
  editor preserves its draft in the tray.
- Keep clipboard reads explicit: capture or paste only. Do not monitor the clipboard
  passively or modify its contents. Do not load external assets from pasted HTML.
- Use native Windows hotkeys; do not reintroduce an AutoHotkey dependency.
- Keep logs limited to event names and exception types. Never log note content,
  clipboard data, paths, exception messages, or tracebacks.
- Validate TOML settings and update config.example.toml and README.md when settings
  or user-visible behavior change. Preserve the user's notes directory in config.toml.
- Keep the shared icon and About metadata available in future packaged builds.

## Verification

- Run checks appropriate to the change with `uv run pytest` and
  `uv run ruff check .`. Add meaningful regression coverage for behavior changes.
- For Windows IPC, hotkey and file-persistence integration checks, use the real
  Windows APIs. Tests must not read or modify the user's actual clipboard or inject
  keyboard input into their applications.
- Dropbox can lock temporary files. When needed, place pytest's temporary files
  outside the repository with a fresh directory under `$env:TEMP`:
  `uv run pytest --basetemp "$env:TEMP/NoteCatcher-tests-<unique-id>"`.
- Report what passed and any unverified behavior. Do not claim an executable was
  built or tested until it actually was.
