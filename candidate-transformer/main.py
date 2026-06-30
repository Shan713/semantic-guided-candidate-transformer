from src.core.logging import configure_logging, get_logger
from src.core.pipeline_context import build_initial_pipeline_context


def main() -> None:
    """Bootstrap foundation components without running business logic."""
    configure_logging()
    logger = get_logger("sgct.main")
    context = build_initial_pipeline_context()
    logger.info(
        "SGCT foundation initialized",
        extra={"execution_id": context.execution_id}
    )


if __name__ == "__main__":
    main()
