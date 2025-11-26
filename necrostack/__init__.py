"""NecroStack - Minimal async-first event-driven micro-framework for Python 3.11+."""

from necrostack.core.event import Event
from necrostack.core.organ import Organ
# from necrostack.core.spine import Spine  # Will be implemented in task 5

__all__ = ["Event", "Organ"]  # "Spine" will be added in task 5
__version__ = "0.1.0"
