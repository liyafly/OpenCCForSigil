"""User-facing and machine-readable plugin errors."""


class PluginError(Exception):
    """Base class for expected plugin failures."""

    code = "PLUGIN_ERROR"


class DependencyError(PluginError):
    code = "DEPENDENCY_ERROR"


class DataIntegrityError(PluginError):
    code = "DATA_INTEGRITY_ERROR"


class ParseError(PluginError):
    code = "PARSE_ERROR"


class RuleValidationError(PluginError):
    code = "RULE_VALIDATION_ERROR"


class RuleConflictError(PluginError):
    code = "RULE_CONFLICT_ERROR"


class ConversionError(PluginError):
    code = "CONVERSION_ERROR"


class VerificationError(PluginError):
    code = "VERIFICATION_ERROR"


class StorageError(PluginError):
    code = "STORAGE_ERROR"


class UserCancelled(PluginError):
    code = "USER_CANCELLED"
