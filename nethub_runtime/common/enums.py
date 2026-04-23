from enum import Enum


class OSType(str, Enum):
    LINUX = "linux"
    WINDOWS = "windows"
    MACOS = "macos"
    UNKNOWN = "unknown"


class InstallTarget(str, Enum):
    PACKAGE = "package"
    TOOL = "tool"
    MODEL = "model"


class ExecutionStatus(str, Enum):
    READY = "ready"
    MISSING_DEPENDENCIES = "missing_dependencies"
    INSTALLING = "installing"
    FAILED = "failed"
    COMPLETED = "completed"
