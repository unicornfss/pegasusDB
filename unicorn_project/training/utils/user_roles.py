from __future__ import annotations

ROLE_PRIORITY = ("admin", "instructor", "engineer", "inspector")

ROLE_LABELS = {
    "admin": "Admin",
    "instructor": "Instructor",
    "engineer": "Engineer",
    "inspector": "Inspector",
}

ROLE_DASHBOARDS = {
    "admin": "app_admin_dashboard",
    "instructor": "instructor_dashboard",
    "engineer": "engineer_dashboard",
    "inspector": "inspector_dashboard",
}


def user_has_role(user, role: str) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False

    role = (role or "").lower()
    if role == "admin":
        return user.is_superuser or user.groups.filter(name__iexact="admin").exists()
    if role in {"instructor", "engineer", "inspector"}:
        return user.groups.filter(name__iexact=role).exists()
    return False


def available_roles_for_user(user) -> list[str]:
    return [role for role in ROLE_PRIORITY if user_has_role(user, role)]


def automatic_role(user) -> str | None:
    for role in ROLE_PRIORITY:
        if user_has_role(user, role):
            return role
    return None


def role_choice_label(role: str) -> str:
    return ROLE_LABELS.get(role, role.replace("_", " ").title())


def resolve_active_role(user, session, personnel=None) -> str | None:
    """
    Pick the active role for this request:
    1. Valid in-session role (from role switcher)
    2. Saved profile default dashboard
    3. Automatic priority (admin, then instructor, …)
    """
    available = set(available_roles_for_user(user))
    if not available:
        return None

    session_role = session.get("active_role")
    if session_role in available:
        return session_role

    if personnel is None:
        personnel = getattr(user, "personnel", None)
    preferred = (getattr(personnel, "default_dashboard_role", None) or "").strip()
    if preferred in available:
        return preferred

    return automatic_role(user)


def dashboard_url_name_for_role(role: str | None) -> str | None:
    if not role:
        return None
    return ROLE_DASHBOARDS.get(role)


def set_active_role(session, role: str) -> None:
    session["active_role"] = role
