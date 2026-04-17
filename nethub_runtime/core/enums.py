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


class ToolType(str, Enum):
    SHELL = "shell"
    PYTHON = "python"
    HTTP = "http"


class AgentClass(str, Enum):
    INFORMATION = "information"
    EXECUTION = "execution"
    ANALYSIS = "analysis"
    ORCHESTRATION = "orchestration"


class AgentLayer(str, Enum):
    KNOWLEDGE = "knowledge"
    EXECUTION = "execution"
    ANALYSIS = "analysis"
    WORKFLOW = "workflow"


class WorkflowComponentType(str, Enum):
    AGENT = "agent"
    TOOL = "tool"
    ANALYZER = "analyzer"
    IO = "io"
    WORKFLOW = "workflow"
