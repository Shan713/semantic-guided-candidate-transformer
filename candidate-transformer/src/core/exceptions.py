class SGCTError(Exception):
    """Base exception for SGCT foundation."""


class ConfigurationError(SGCTError):
    """Raised when configuration is invalid or unavailable."""


class OntologyError(SGCTError):
    """Raised for ontology schema or loading issues."""


class ModelValidationError(SGCTError):
    """Raised when a model contract is violated."""
