# tools/base.py
"""
Base Tool Class

All tools must inherit from this abstract base class.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Abstract base class for all tools."""

    name: str
    description: str

    @abstractmethod
    async def aexecute(self, *args, **kwargs) -> Any:
        """Execute the tool asynchronously."""
        pass

    def __str__(self):
        return f"{self.name} - {self.description}"
