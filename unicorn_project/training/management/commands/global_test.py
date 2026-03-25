from dataclasses import dataclass
from django.contrib.auth.models import Group, User
from django.core.management import BaseCommand, CommandError, call_command
from django.db import IntegrityError
from django.test import Client
from django.urls import reverse

from ...models import Personnel


@dataclass
class Probe:
    label: str
    route_name: str
    role: str
    expected_codes: tuple[int, ...] = (200,)


class Command(BaseCommand):
    help = (
        "Run global diagnostics (Django checks, migration drift check, and "
        "role-based URL smoke tests)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--allow-warnings",
            action="store_true",
            help="Do not fail command when only warnings are found.",
        )
        parser.add_argument(
            "--skip-migration-check",
            action="store_true",
            help="Skip makemigrations --check --dry-run.",
        )
        parser.add_argument(
            "--verbosity-level",
            type=int,
            default=1,
            help="Command verbosity passed to internal checks (0-2 recommended).",
        )

    def handle(self, *args, **options):
        allow_warnings = options["allow_warnings"]
        skip_migration_check = options["skip_migration_check"]
        verbosity = options["verbosity_level"]

        failures = []
        warnings = []

        self.stdout.write(self.style.MIGRATE_HEADING("Global diagnostics starting..."))

        self._run_django_check(failures, warnings, verbosity)

        if not skip_migration_check:
            self._run_migration_drift_check(failures, warnings, verbosity)
        else:
            warnings.append("Skipped migration drift check (--skip-migration-check).")

        smoke_result = self._run_smoke_tests()
        failures.extend(smoke_result["failures"])
        warnings.extend(smoke_result["warnings"])

        self._print_summary(failures, warnings)

        if failures:
            raise CommandError(f"Global diagnostics failed with {len(failures)} issue(s).")
        if warnings and not allow_warnings:
            raise CommandError(
                f"Global diagnostics passed with warnings ({len(warnings)}). "
                "Re-run with --allow-warnings to ignore warnings in CI."
            )

        self.stdout.write(self.style.SUCCESS("Global diagnostics passed."))

    def _run_django_check(self, failures, warnings, verbosity):
        self.stdout.write("1) Running django check...")
        try:
            call_command("check", verbosity=verbosity)
        except Exception as exc:
            failures.append(f"django check failed: {exc}")

    def _run_migration_drift_check(self, failures, warnings, verbosity):
        self.stdout.write("2) Running migration drift check...")
        try:
            call_command("makemigrations", "--check", "--dry-run", verbosity=verbosity)
        except SystemExit as exc:
            code = int(getattr(exc, "code", 1) or 1)
            if code != 0:
                failures.append("Model changes detected without migrations (makemigrations --check failed).")
        except Exception as exc:
            text = str(exc)
            if "No changes detected" in text:
                return
            failures.append(f"Migration drift check failed: {exc}")

    def _run_smoke_tests(self):
        self.stdout.write("3) Running URL smoke tests...")

        failures = []
        warnings = []

        clients = {
            "anon": Client(HTTP_HOST="localhost"),
            "instructor": Client(HTTP_HOST="localhost"),
            "admin": Client(HTTP_HOST="localhost"),
            "engineer": Client(HTTP_HOST="localhost"),
            "inspector": Client(HTTP_HOST="localhost"),
        }

        instructor_user = self._ensure_user_with_role("diag.instructor", "instructor", staff=False)
        admin_user = self._ensure_user_with_role("diag.admin", "admin", staff=True)
        engineer_user = self._ensure_user_with_role("diag.engineer", "engineer", staff=False)
        inspector_user = self._ensure_user_with_role("diag.inspector", "inspector", staff=False)

        if instructor_user:
            clients["instructor"].force_login(instructor_user)
        else:
            warnings.append("Could not create/login instructor diagnostic user.")

        if admin_user:
            clients["admin"].force_login(admin_user)
        else:
            warnings.append("Could not create/login admin diagnostic user.")

        if engineer_user:
            clients["engineer"].force_login(engineer_user)
        else:
            warnings.append("Could not create/login engineer diagnostic user.")

        if inspector_user:
            clients["inspector"].force_login(inspector_user)
        else:
            warnings.append("Could not create/login inspector diagnostic user.")

        probes = [
            Probe("Home", "home", "anon", (200, 302)),
            Probe("Login", "login", "anon", (200, 302)),
            Probe("Public Register", "public_delegate_register", "anon", (200,)),
            Probe("Public Feedback", "public_feedback_form", "anon", (200,)),
            Probe("Public Exam Start", "delegate_exam_start", "anon", (200, 400)),
            Probe("Privacy", "privacy_notices", "anon", (200,)),
            Probe("Instructor Dashboard", "instructor_dashboard", "instructor", (200, 302)),
            Probe("Instructor Bookings", "instructor_bookings", "instructor", (200, 302)),
            Probe("User Profile", "user_profile", "instructor", (200, 302)),
            Probe("Admin Dashboard", "app_admin_dashboard", "admin", (200, 302)),
            Probe("Admin Bookings", "admin_booking_list", "admin", (200, 302)),
            Probe("Admin Businesses", "admin_business_list", "admin", (200, 302)),
            Probe("Engineer Dashboard", "engineer_dashboard", "engineer", (200, 302)),
            Probe("Inspector Dashboard", "inspector_dashboard", "inspector", (200, 302)),
            Probe("No Roles", "no_roles", "anon", (200, 302)),
        ]

        for probe in probes:
            client = clients[probe.role]
            try:
                path = reverse(probe.route_name)
            except Exception as exc:
                failures.append(f"{probe.label}: reverse('{probe.route_name}') failed: {exc}")
                continue

            try:
                response = client.get(path, follow=False)
            except Exception as exc:
                failures.append(f"{probe.label}: request crashed: {exc}")
                continue

            status = int(response.status_code)
            if status >= 500:
                failures.append(f"{probe.label}: {path} returned {status}")
                continue

            if status not in probe.expected_codes:
                warnings.append(
                    f"{probe.label}: {path} returned {status} (expected one of {probe.expected_codes})"
                )

            self.stdout.write(f"   - [{probe.role}] {probe.label}: {status}")

        return {"failures": failures, "warnings": warnings}

    def _ensure_user_with_role(self, username, group_name, staff=False):
        try:
            group, _ = Group.objects.get_or_create(name=group_name)
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@diag.local",
                    "is_staff": staff,
                    "is_active": True,
                },
            )
            if created:
                user.set_password("diagnostic-temp-password")
                user.save(update_fields=["password"])

            if user.is_staff != staff:
                user.is_staff = staff
                user.save(update_fields=["is_staff"])

            user.groups.add(group)

            if group_name in {"instructor", "admin"}:
                self._ensure_personnel(user, username)

            return user
        except IntegrityError:
            return None
        except Exception:
            return None

    def _ensure_personnel(self, user, username):
        personnel = getattr(user, "personnel", None)
        if personnel:
            changed_fields = []
            if personnel.must_change_password:
                personnel.must_change_password = False
                changed_fields.append("must_change_password")
            if not personnel.can_login:
                personnel.can_login = True
                changed_fields.append("can_login")
            if changed_fields:
                personnel.save(update_fields=changed_fields)
            return

        Personnel.objects.create(
            user=user,
            name=f"Diagnostic {username}",
            email=f"{username}@diag.local",
            must_change_password=False,
            can_login=True,
            is_active=True,
        )

    def _print_summary(self, failures, warnings):
        self.stdout.write("\n--- Global diagnostics summary ---")

        if failures:
            self.stdout.write(self.style.ERROR(f"Failures: {len(failures)}"))
            for item in failures:
                self.stdout.write(self.style.ERROR(f" - {item}"))
        else:
            self.stdout.write(self.style.SUCCESS("Failures: 0"))

        if warnings:
            self.stdout.write(self.style.WARNING(f"Warnings: {len(warnings)}"))
            for item in warnings:
                self.stdout.write(self.style.WARNING(f" - {item}"))
        else:
            self.stdout.write(self.style.SUCCESS("Warnings: 0"))
