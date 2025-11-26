"""Backend implementations for NecroStack."""

from necrostack.backends.base import Backend
from necrostack.backends.memory import InMemoryBackend

__all__ = ["Backend", "InMemoryBackend"]

# Conditionally export RedisBackend if redis is installed
try:
    from necrostack.backends.redis import RedisBackend
    __all__.append("RedisBackend")
except ImportError:
    pass
