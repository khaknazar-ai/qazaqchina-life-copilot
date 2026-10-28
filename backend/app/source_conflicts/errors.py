class ConflictError(Exception):
    """Base error for conflict review operations."""


class ConflictNotFoundError(ConflictError):
    pass


class ConflictPermissionError(ConflictError):
    pass


class ConflictValidationError(ConflictError, ValueError):
    pass


class ConflictRevisionError(ConflictError):
    pass


class ConflictIntegrityError(ConflictError):
    pass
