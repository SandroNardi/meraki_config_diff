import logging
import os
from typing import Optional,TypedDict


class LoggerConfig(TypedDict):
    enable_logging: bool
    console_logging: bool
    file_logging: bool
    log_file_path: str
    level: int

# In-memory log storage for UI consumption
log_entries: list[str] = []  # List to store log messages for UI display


class ListHandler(logging.Handler):
    """Custom logging handler that appends formatted log messages to a shared list."""

    def emit(self, record: logging.LogRecord) -> None:
        """Format and append the log record to the in-memory log_entries list."""
        log_entry = self.format(record)
        log_entries.append(log_entry)


# Internal singleton logger instance and configuration state
_LOGGER: Optional[logging.Logger] = None
_CONFIG: LoggerConfig = {
    "enable_logging": True,
    "console_logging": False,
    "file_logging": False,
    "log_file_path": "app.log",
    "level": logging.INFO,
}


def _close_and_remove_handlers(logger: logging.Logger) -> None:
    """
    Remove and close all handlers from the logger to avoid file lock issues on Windows.
    """
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass


def setup_logger(
    enable_logging: bool = True,
    console_logging: bool = False,
    file_logging: bool = False,
    *,
    log_file_path: str = "app.log",
    level: int = logging.INFO,
) -> logging.Logger:
    """
    Create or reconfigure a process-wide singleton logger named 'app_logger'.

    Args:
        enable_logging (bool): Enable or disable logging globally.
        console_logging (bool): Enable logging output to console.
        file_logging (bool): Enable logging output to a file.
        log_file_path (str): Path to the log file.
        level (int): Logging level (e.g., logging.INFO).

    Returns:
        logging.Logger: Configured singleton logger instance.

    Notes:
        - Safe to call multiple times; reconfigures logger if settings change.
        - Closes old file handlers before reconfiguring to prevent Windows file locks.
        - Appends to the log file by default.
    """
    global _LOGGER, _CONFIG

    new_config : LoggerConfig = {
        "enable_logging": enable_logging,
        "console_logging": console_logging,
        "file_logging": file_logging,
        "log_file_path": log_file_path,
        "level": level,
    }

    if _LOGGER is not None and _CONFIG == new_config:
        return _LOGGER

    logger = logging.getLogger("app_logger")
    logger.propagate = False
    logger.setLevel(level if enable_logging else logging.CRITICAL + 1)

    _close_and_remove_handlers(logger)

    if not enable_logging:
        _LOGGER = logger
        _CONFIG = new_config
        return logger

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(filename)s - %(message)s"
    )

    # Attach in-memory list handler for UI log consumption
    list_handler = ListHandler()
    list_handler.setFormatter(formatter)
    logger.addHandler(list_handler)

    if console_logging:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    if file_logging:
        log_path = os.path.abspath(log_file_path)
        if os.path.dirname(log_path):
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
        file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    _LOGGER = logger
    _CONFIG = new_config
    return logger


def get_logger() -> logging.Logger:
    """
    Return the shared app logger, creating it with the current configuration if needed.

    Returns:
        logging.Logger: The singleton app logger instance.
    """
    return setup_logger(
        enable_logging=bool(_CONFIG["enable_logging"]),
        console_logging=bool(_CONFIG["console_logging"]),
        file_logging=bool(_CONFIG["file_logging"]),
        log_file_path=str(_CONFIG["log_file_path"]),
        level=int(_CONFIG["level"]),
    )