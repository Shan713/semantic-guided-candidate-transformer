from pathlib import Path

PROJECT_NAME = "Semantic Guided Candidate Transformer"
PROJECT_SHORT_NAME = "SGCT"
PROJECT_VERSION = "0.1.0"

BASE_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = BASE_DIR / "src"
CONFIG_DIR = SRC_DIR / "config"
ONTOLOGY_DIR = SRC_DIR / "ontology"
LOG_DIR = BASE_DIR / "logs"

DEFAULT_TIMEZONE = "UTC"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FORMAT = (
    "%(asctime)s | %(levelname)s | %(name)s | "
    "execution_id=%(execution_id)s | %(message)s"
)
