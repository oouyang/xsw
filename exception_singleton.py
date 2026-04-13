# exception_singleton.py
"""
Global singleton for exception notifier.
Avoids circular imports between main_optimized <-> background_jobs.
"""

_exception_notifier = None


def set_notifier(notifier):
    """Set the global exception notifier (called by main_optimized during startup)."""
    global _exception_notifier
    _exception_notifier = notifier


def get_notifier():
    """Get the global exception notifier (called by background_jobs, etc)."""
    return _exception_notifier
