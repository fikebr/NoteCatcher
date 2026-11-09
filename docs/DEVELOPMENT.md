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

This hook prepares resources for a future build; a complete standalone executable
has not been built or verified yet. Packaged releases must be rebuilt after source
or metadata changes. Config discovery beside the executable, portable state
storage, a suitable entry-point launcher, and packaged Windows workflow checks
remain packaging work.
