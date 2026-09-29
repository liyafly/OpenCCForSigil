"""User-facing and machine-readable plugin errors."""


class PluginError(Exception):
    """Base class for expected plugin failures."""

    code = "PLUGIN_ERROR"


class DependencyError(PluginError):
    code = "DEPENDENCY_ERROR"


class BookContainerSupportError(PluginError):
    code = "BOOK_API_UNAVAILABLE"


class DataIntegrityError(PluginError):
    code = "DATA_INTEGRITY_ERROR"


class ParseError(PluginError):
    code = "PARSE_ERROR"


class RuleValidationError(PluginError):
    code = "RULE_VALIDATION_ERROR"


class RuleConflictError(PluginError):
    code = "RULE_CONFLICT_ERROR"

    def __init__(self, conflict_groups=()):
        self.conflict_groups = tuple(
            tuple((str(rule_id), str(ruleset_id)) for rule_id, ruleset_id in group)
            for group in conflict_groups
        )
        details = "; ".join(
            ", ".join(f"{rule_id} ({ruleset_id})" for rule_id, ruleset_id in group)
            for group in self.conflict_groups
        )
        message = "blocking rule conflicts"
        if details:
            message += ": " + details
        super().__init__(message)


class StorageError(PluginError):
    code = "STORAGE_ERROR"


class UserCancelled(PluginError):
    code = "USER_CANCELLED"
