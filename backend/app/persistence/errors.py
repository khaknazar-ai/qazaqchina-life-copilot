class PersistenceError(Exception):
    """Base error for local persistence failures."""


class RecordNotFoundError(PersistenceError):
    """Raised when a requested local record cannot be found."""


class PersistenceConfigurationError(PersistenceError):
    """Raised when persistence is requested with invalid configuration."""


class PersistenceSerializationError(PersistenceError):
    """Raised when a record cannot be serialized or deserialized safely."""
