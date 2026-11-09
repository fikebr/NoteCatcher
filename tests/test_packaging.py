from pathlib import Path
import sys

from notecatcher.config import default_config_path


def test_frozen_config_found_beside_exe_from_other_directory(tmp_path, monkeypatch):
    distribution = tmp_path / 'portable'
    distribution.mkdir()
    config = distribution / 'config.toml'
    config.write_text('[storage]\nnotes_dir = "~/Notes"')
    other = tmp_path / 'other'
    other.mkdir()
    (other / 'config.toml').write_text('not the selected config')
    monkeypatch.chdir(other)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(distribution / 'NoteCatcher.exe'))
    assert default_config_path() == config


def test_source_config_still_uses_working_directory(tmp_path, monkeypatch):
    config = tmp_path / 'config.toml'
    config.write_text('[storage]')
    monkeypatch.chdir(tmp_path)
    monkeypatch.delattr(sys, 'frozen', raising=False)
    assert default_config_path() == Path.cwd() / 'config.toml'
