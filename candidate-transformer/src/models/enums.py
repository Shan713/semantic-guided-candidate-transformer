from enum import Enum


class SourceType(str, Enum):
    RECRUITER_CSV = "recruiter_csv"
    ATS_JSON = "ats_json"
    RESUME_PDF = "resume_pdf"
    GITHUB = "github"


class ProjectionMode(str, Enum):
    DEFAULT = "default"
    CUSTOM = "custom"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class MergeStrategy(str, Enum):
    UNION = "union"
    SEMANTIC_UNION = "semantic_union"
    CHRONOLOGICAL_MERGE = "chronological_merge"
    HIGHEST_CONFIDENCE_RECENT = "highest_confidence_recent"
    KEEP_ALL_WITH_CONFIDENCE = "keep_all_with_confidence"


class MissingValueStrategy(str, Enum):
    NULL = "null"
    OMIT = "omit"
    ERROR = "error"


class SemanticResolutionStage(str, Enum):
    EXACT_ALIAS_MATCH = "exact_alias_match"
    CANONICAL_MATCH = "canonical_match"
    PARENT_CATEGORY_RESOLUTION = "parent_category_resolution"
    ENTITY_LINKING = "entity_linking"
    DETERMINISTIC_FUZZY_MATCH = "deterministic_fuzzy_match"
    UNKNOWN_VALUE = "unknown_value"


class ResolverType(str, Enum):
    ONTOLOGY_LOADER = "ontology_loader"
    SKILL_CANONICALIZER = "skill_canonicalizer"
    COMPANY_ALIAS_RESOLVER = "company_alias_resolver"
    JOB_TITLE_RESOLVER = "job_title_resolver"
    DEGREE_RESOLVER = "degree_resolver"
    COUNTRY_RESOLVER = "country_resolver"
    SEMANTIC_RESOLUTION_ENGINE = "semantic_resolution_engine"


class FieldType(str, Enum):
    CANDIDATE_ID = "candidate_id"
    FULL_NAME = "full_name"
    EMAILS = "emails"
    PHONES = "phones"
    LOCATION = "location"
    LINKS = "links"
    HEADLINE = "headline"
    YEARS_EXPERIENCE = "years_experience"
    SKILLS = "skills"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    PROVENANCE = "provenance"
    OVERALL_CONFIDENCE = "overall_confidence"


class EntityDomain(str, Enum):
    SKILL = "skill"
    COMPANY = "company"
    JOB_TITLE = "job_title"
    DEGREE = "degree"
    COUNTRY = "country"
