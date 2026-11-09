"""Validated TOML settings. Unknown keys fail rather than silently doing nothing."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import re
import tomllib


@dataclass(frozen=True)
class Settings:
    notes_dir: Path = field(default_factory=lambda: Path.home() / 'Documents' / 'NoteCatcher')
    assets_dir: str = 'assets'
    filename_pattern: str = '%Y-%m-%d_%H%M%S'
    save_shortcut: str = 'Ctrl+Return'
    after_save: str = 'hide'
    restore_focus: bool = True
    recovery_debounce_ms: int = 500
    log_level: str = 'INFO'
    cancel_shortcut: str = 'Esc'
    capture_shortcut: str = 'Ctrl+Alt+N'


def validate_storage(assets_dir, filename_pattern):
    if (not isinstance(assets_dir, str) or
            not re.fullmatch(r'[\w -]{1,64}', assets_dir) or
            assets_dir.endswith(' ') or assets_dir.upper() in
            {'CON', 'PRN', 'AUX', 'NUL', *[f'COM{i}' for i in range(10)],
             *[f'LPT{i}' for i in range(10)]}):
        raise ValueError('storage.assets_dir must be one safe folder name (letters, numbers, spaces, - or _).')
    if not isinstance(filename_pattern, str) or not filename_pattern:
        raise ValueError('storage.filename_pattern must be a nonempty string.')
    remainder = re.sub(r'%[YymdHMSf]', '', filename_pattern)
    if '%' in remainder:
        raise ValueError('storage.filename_pattern supports only %Y, %y, %m, %d, %H, %M, %S and %f.')
    name = datetime.now().strftime(filename_pattern)
    if (len(name) > 120 or not re.fullmatch(r'[\w .-]+', name) or
            name.endswith((' ', '.')) or name in {'.', '..'} or
            name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                *[f'COM{i}' for i in range(10)], *[f'LPT{i}' for i in range(10)]}):
        raise ValueError('storage.filename_pattern must produce a safe filename without path separators.')


def load_settings(path: Path, required=False):
    if not path.exists():
        if required:
            raise ValueError(f'Config file does not exist: {path}')
        return Settings()
    try:
        with path.open('rb') as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        raise ValueError('Config is not valid TOML. Check quoting, section names, and value types.') from error
    schema = {'storage': {'notes_dir', 'assets_dir', 'filename_pattern', 'image_format'},
              'hotkeys': {'save', 'cancel', 'capture'}, 'behavior': {'after_save', 'restore_focus'},
              'recovery': {'debounce_ms'}, 'logging': {'level'}}
    for section, values in data.items():
        if section not in schema:
            raise ValueError(f'Unknown config section: {section}')
        if not isinstance(values, dict):
            raise ValueError(f'Config section {section} must be a TOML table.')
        for key in values:
            if key not in schema[section]:
                raise ValueError(f'Unknown config option: {section}.{key}')
    defaults = Settings()
    storage = data.get('storage', {})
    notes = storage.get('notes_dir', str(defaults.notes_dir))
    if not isinstance(notes, str) or not notes.strip() or '\0' in notes:
        raise ValueError('storage.notes_dir must be a nonempty directory path.')
    assets = storage.get('assets_dir', defaults.assets_dir)
    pattern = storage.get('filename_pattern', defaults.filename_pattern)
    validate_storage(assets, pattern)
    if storage.get('image_format', 'png') != 'png':
        raise ValueError('storage.image_format currently supports only "png".')
    save = data.get('hotkeys', {}).get('save', defaults.save_shortcut)
    if not isinstance(save, str) or not save.strip():
        raise ValueError('hotkeys.save must be a keyboard shortcut string.')
    from PySide6.QtGui import QKeySequence
    sequence = QKeySequence.fromString(save, QKeySequence.SequenceFormat.PortableText)
    if sequence.isEmpty() or sequence.count() != 1 or sequence[0].key() in (0, 0x1ffffff):
        raise ValueError('hotkeys.save must be one valid Qt shortcut, for example Ctrl+Return.')
    cancel = data.get('hotkeys', {}).get('cancel', defaults.cancel_shortcut)
    if not isinstance(cancel, str) or not cancel.strip():
        raise ValueError('hotkeys.cancel must be a keyboard shortcut string.')
    cancel_sequence = QKeySequence.fromString(cancel, QKeySequence.SequenceFormat.PortableText)
    if (cancel_sequence.isEmpty() or cancel_sequence.count() != 1 or
            cancel_sequence[0].key() in (0, 0x1ffffff)):
        raise ValueError('hotkeys.cancel must be one valid Qt shortcut, for example Esc.')
    if cancel_sequence == sequence:
        raise ValueError('hotkeys.cancel and hotkeys.save must use different shortcuts.')
    capture = data.get('hotkeys', {}).get('capture', defaults.capture_shortcut)
    from .hotkeys import parse_capture_shortcut
    parse_capture_shortcut(capture)
    behavior = data.get('behavior', {})
    after = behavior.get('after_save', defaults.after_save)
    if after not in ('hide', 'stay_open'):
        raise ValueError('behavior.after_save must be "hide" or "stay_open".')
    restore = behavior.get('restore_focus', defaults.restore_focus)
    if type(restore) is not bool:
        raise ValueError('behavior.restore_focus must be true or false.')
    debounce = data.get('recovery', {}).get('debounce_ms', defaults.recovery_debounce_ms)
    if type(debounce) is not int or not 100 <= debounce <= 5000:
        raise ValueError('recovery.debounce_ms must be an integer from 100 to 5000.')
    level = data.get('logging', {}).get('level', defaults.log_level)
    if level not in ('DEBUG', 'INFO', 'WARNING', 'ERROR'):
        raise ValueError('logging.level must be DEBUG, INFO, WARNING or ERROR.')
    return Settings(Path(notes).expanduser(), assets, pattern, save, after, restore, debounce, level,
                    cancel, capture)
