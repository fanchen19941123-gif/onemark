from enum import Enum


class SyncRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"


class PlatformResultStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"


class TriggerSource(str, Enum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class ChangeType(str, Enum):
    ADDED = "added"
    UPDATED = "updated"
    REMOVED = "removed"
