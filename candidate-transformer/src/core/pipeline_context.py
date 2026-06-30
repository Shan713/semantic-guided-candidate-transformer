from datetime import UTC, datetime
from uuid import uuid4

from src.core.constants import PROJECT_VERSION
from src.core.settings import get_settings
from src.models.domain_models import PipelineContext, PipelineStats, RuntimeMetadata
from src.models.enums import ProjectionMode


def build_initial_pipeline_context() -> PipelineContext:
    settings = get_settings()
    execution_id = f"{settings.execution_id_prefix}-{uuid4().hex[:12]}"
    metadata = RuntimeMetadata(
        environment=settings.env,
        app_version=PROJECT_VERSION,
        config_version="1.0",
        ontology_versions={},
        host_info={},
    )
    return PipelineContext(
        execution_id=execution_id,
        started_at_utc=datetime.now(UTC),
        config_bundle={},
        ontology_registry_ref="src.ontology.ontology_registry.OntologyRegistry",
        logger_ref="root",
        runtime_metadata=metadata,
        pipeline_stats=PipelineStats(),
        semantic_config_loaded=False,
        projection_mode=ProjectionMode.DEFAULT,
    )
