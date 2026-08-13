from .base import Adapter, AdapterResult  # noqa: F401
from .command import CommandAdapter  # noqa: F401
from .manual import ManualAdapter  # noqa: F401

REGISTRY = {
    "manual": ManualAdapter,
    "command": CommandAdapter,
}
