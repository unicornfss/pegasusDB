"""
App version for Pegasus.

MAJOR.MINOR are set manually when a meaningful release milestone is reached.
PATCH is automatically derived from commits since the last version tag.

Workflow when bumping to a new version (e.g. 0.3):
  1. Change MAJOR/MINOR below.
  2. Commit the change.
  3. Tag that commit: git tag v0.3
  4. PATCH will now count from 0 again on subsequent commits.

Examples:
  v0.2.0   — at the v0.2 tag
  v0.2.7   — seven commits after the v0.2 tag
  v0.3.0   — at the v0.3 tag (patch resets)
"""
import subprocess
from pathlib import Path

MAJOR = 0
MINOR = 2

_ROOT = Path(__file__).resolve().parent.parent  # manage.py lives here


def _git_patch_count() -> int:
    tag = f"v{MAJOR}.{MINOR}"
    try:
        # Count commits since the version tag (0 if HEAD IS the tag)
        result = subprocess.run(
            ["git", "rev-list", "--count", f"{tag}..HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
            cwd=_ROOT,
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except Exception:
        pass
    # Tag doesn't exist yet — fall back to total commit count
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
            cwd=_ROOT,
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except Exception:
        pass
    return 0


def get_version() -> str:
    return f"v{MAJOR}.{MINOR}.{_git_patch_count()}"


APP_VERSION: str = get_version()
