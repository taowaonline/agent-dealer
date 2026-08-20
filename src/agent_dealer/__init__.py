"""agent_dealer：跨模型 Agent 共享目录协作运行时。"""

__version__ = "0.3.0"

from .errors import MMACError  # noqa: F401
from .store import TaskStore  # noqa: F401
from .validator import ValidationReport, validate_task  # noqa: F401
