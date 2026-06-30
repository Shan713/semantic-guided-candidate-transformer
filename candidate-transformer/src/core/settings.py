from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from src.core.constants import CONFIG_DIR, LOG_DIR, ONTOLOGY_DIR, PROJECT_SHORT_NAME


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    env: str = "development"
    log_level: str = "INFO"
    log_dir: Path = LOG_DIR
    config_dir: Path = CONFIG_DIR
    ontology_dir: Path = ONTOLOGY_DIR
    execution_id_prefix: str = PROJECT_SHORT_NAME.lower()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
