"""Bounded event-only logging: never record exception text, paths or note data."""

import logging
from logging.handlers import RotatingFileHandler

logger = logging.getLogger('notecatcher')
logger.addHandler(logging.NullHandler())
logger.propagate = False


def configure_logging(directory, level='INFO'):
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(directory / 'notecatcher.log', maxBytes=1_000_000,
                                  backupCount=3, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    for previous in list(logger.handlers):
        previous.close()
        logger.removeHandler(previous)
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.info('application_started')


def log_failure(event, error):
    # Do not use logger.exception: arbitrary exception text may contain pasted data.
    logger.error('%s exception_type=%s', event, type(error).__name__)


def error_detail(error):
    if isinstance(error, PermissionError):
        return 'Access was denied. Check folder permissions and whether a sync tool has locked a file.'
    if isinstance(error, OSError):
        return 'The storage operation failed. Check the folder, available disk space, and drive connection.'
    return 'The document or recovery data could not be processed. The draft has been retained.'
