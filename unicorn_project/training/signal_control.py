# unicorn_project/training/signal_control.py

"""
Simple global flag to temporarily disable Django signals
to prevent infinite loops or unwanted syncing.
"""

_disabled = False


def disable():
    """Disable sync signals temporarily."""
    global _disabled
    _disabled = True


def enable():
    """Re-enable sync signals."""
    global _disabled
    _disabled = False


def is_disabled():
    """Check whether signals are currently disabled."""
    return _disabled
