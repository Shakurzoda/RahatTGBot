import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

_LOGGER_CONFIGURED = False


def _configure_logging(log_file: Optional[str] = "bot.log") -> None:
    global _LOGGER_CONFIGURED
    if _LOGGER_CONFIGURED:
        return

    # Базовая конфигурация: логируем и в файл, и в консоль
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s]: %(message)s",
    )

    if log_file:
        handler = RotatingFileHandler(
            log_file,
            maxBytes=1_000_000,   # ~1 МБ
            backupCount=3,        # до 3 архивов
            encoding="utf-8",
        )
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s]: %(message)s"
        )
        handler.setFormatter(formatter)
        logging.getLogger().addHandler(handler)

    _LOGGER_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """
    Возвращает настроенный логгер.
    Первый вызов настраивает логирование (консоль + файл bot.log).
    """
    _configure_logging()
    return logging.getLogger(name)
