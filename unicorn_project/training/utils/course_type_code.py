"""Generate unique CourseType.code values from course names."""

from __future__ import annotations

import re

from ..models import CourseType

# Connector words stay lowercase in the acronym (e.g. EFAaW).
_SMALL_WORDS = frozenset({
    "a", "an", "and", "at", "by", "for", "in", "of", "on", "the", "to", "with",
})

_MAX_CODE_LEN = 20


def initials_from_course_name(name: str) -> str:
    """
    Build a short code from the first letter of each word, preserving the
    letter case used in the course name. Connector words (at, and, the, …)
    always contribute a lowercase letter. Example: "Emergency First Aid at Work" -> "EFAaW"
    """
    if not (name or "").strip():
        return ""

    parts: list[str] = []
    for raw in re.split(r"[\s\-/]+", name.strip()):
        word = re.sub(r"[^\w]", "", raw)
        if not word or not re.search(r"[A-Za-z]", word):
            continue
        first = next(c for c in word if c.isalpha())
        if word.lower() in _SMALL_WORDS:
            parts.append(first.lower())
        else:
            parts.append(first)
    return "".join(parts)


def unique_course_code(name: str, *, exclude_pk=None) -> str:
    """
    Return a unique CourseType.code for ``name``, appending a digit suffix if needed.
    """
    base = initials_from_course_name(name) or "COURSE"
    base = base[:_MAX_CODE_LEN]

    qs = CourseType.objects.all()
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)

    candidate = base
    suffix = 2
    while qs.filter(code__iexact=candidate).exists():
        suffix_str = str(suffix)
        trimmed = base[: _MAX_CODE_LEN - len(suffix_str)]
        candidate = f"{trimmed}{suffix_str}"
        suffix += 1
        if suffix > 9999:
            raise ValueError(f"Could not generate a unique code for {name!r}")

    return candidate
