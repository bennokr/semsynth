"""Runtime helpers for resolving SemSynth dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import logging
from types import ModuleType
from typing import Any, Dict, Optional


@dataclass(slots=True)
class DependencyRegistry:
    """Resolve and cache SemSynth modules and attributes.

    The registry loads modules on demand and raises explicit runtime errors when
    optional dependencies are missing. This removes silent fallbacks in favour
    of actionable messaging.
    """

    _cache: Dict[str, ModuleType] = field(default_factory=dict)

    def require_module(self, module_name: str, *, hint: Optional[str] = None) -> ModuleType:
        """Load ``module_name`` and memoize the result.

        Args:
            module_name: Fully-qualified module path.
            hint: Optional installation guidance appended to error messages.

        Returns:
            The imported module.

        Raises:
            RuntimeError: If the module cannot be imported.
        """

        if module_name in self._cache:
            return self._cache[module_name]
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            message = hint or f"Install dependency providing '{module_name}'."
            logging.error("Missing dependency %s: %s", module_name, message)
            raise RuntimeError(message) from exc
        self._cache[module_name] = module
        return module

    def require_attr(
        self,
        module_name: str,
        attribute: str,
        *,
        hint: Optional[str] = None,
    ) -> Any:
        """Return ``attribute`` from ``module_name``.

        Args:
            module_name: Fully-qualified module path.
            attribute: Expected attribute name within the module.
            hint: Optional installation guidance appended to error messages.

        Returns:
            The resolved attribute.

        Raises:
            RuntimeError: If the attribute is absent.
        """

        module = self.require_module(module_name, hint=hint)
        try:
            return getattr(module, attribute)
        except AttributeError as exc:
            message = f"Module '{module_name}' lacks attribute '{attribute}'."
            logging.error(message)
            raise RuntimeError(message) from exc


DEPENDENCIES = DependencyRegistry()
"""Singleton dependency registry used across SemSynth."""


__all__ = ["DependencyRegistry", "DEPENDENCIES"]
