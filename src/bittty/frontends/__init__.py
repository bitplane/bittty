"""Frontend scaffolding: the Display base and reference frontends.

Kept in its own package so the backend (`Terminal`) never imports frontend code —
the "backend is never subclassed by a frontend" rule, enforced structurally.
"""

from .display import Display

__all__ = ["Display"]
