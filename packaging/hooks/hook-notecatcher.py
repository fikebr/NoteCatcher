"""Keep project metadata and the shared icon in PyInstaller builds."""

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

datas = copy_metadata('notecatcher') + collect_data_files('notecatcher', includes=['assets/*.svg'])
