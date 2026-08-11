"""Minimal package health primitive used by foundation checks."""


def health_status() -> str:
    """Return a deterministic health value for local verification."""
    return "ok"
