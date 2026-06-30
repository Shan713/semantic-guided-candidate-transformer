import logging
from datetime import UTC, datetime
from pathlib import Path

from src.core.constants import DEFAULT_LOG_FORMAT
from src.core.settings import get_settings


class ExecutionIdFilter(logging.Filter):
    def __init__(self, execution_id: str) -> None:
        super().__init__()
        self.execution_id = execution_id

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "execution_id"):
            record.execution_id = self.execution_id
        return True


def _build_execution_id(prefix: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"{prefix}-{timestamp}"


def configure_logging() -> str:
    settings = get_settings()
    execution_id = _build_execution_id(settings.execution_id_prefix)

    Path(settings.log_dir).mkdir(parents=True, exist_ok=True)
    log_file = Path(settings.log_dir) / f"{execution_id}.log"

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format=DEFAULT_LOG_FORMAT,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
        force=True,
    )

    root_logger = logging.getLogger()
    root_logger.addFilter(ExecutionIdFilter(execution_id=execution_id))
    return execution_id


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
