"""Absolute-import entry point for the Windows executable."""

import sys

if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--verify-bundle':
        try:
            from notecatcher.verification import verify_bundle
            verify_bundle(sys.argv[2])
        except Exception as error:
            import json
            from pathlib import Path
            report = Path(sys.argv[2])
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps({'passed': False, 'error':
                              f'{type(error).__name__}: {error}'}), encoding='utf-8')
            raise SystemExit(1)
    else:
        from notecatcher.main import main
        main()
