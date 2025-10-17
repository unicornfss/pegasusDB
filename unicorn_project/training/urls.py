# unicorn_project/training/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views

from . import views
from . import views_admin as app_admin
from . import views_instructor as instv
from . import views_instructor


urlpatterns = [
    # ---------- Core / Home ----------
    path("", views.home, name="home"),
    path("switch-role/<str:role>/", views.switch_role, name="switch_role"),

    # Post-login routers
    path("app/after-login/", instv.post_login, name="post_login"),
    path("post-login/", views.post_login_router, name="post_login_router"),

    # ---------- Instructor area ----------
    # Landing page -> My bookings
    path("app/instructor/", instv.instructor_bookings, name="instructor_dashboard"),
    path("app/instructor/bookings/", instv.instructor_bookings, name="instructor_bookings"),
    path("app/instructor/booking/<uuid:pk>/", instv.instructor_booking_detail, name="instructor_booking_detail"),
    path("app/instructor/day/<int:pk>/registers/", instv.instructor_day_registers, name="instructor_day_registers"),
    path("app/instructor/register/<int:pk>/edit/", instv.instructor_delegate_edit, name="instructor_delegate_edit"),
    path("app/instructor/day/<int:day_pk>/registers/new/", instv.instructor_delegate_new, name="instructor_delegate_new"),
    path("app/instructor/profile/", views.instructor_profile, name="instructor_profile"),
    

    # Instructor: delete a delegate row
    path("app/instructor/register/<int:pk>/delete/", instv.instructor_delegate_delete, name="instructor_delegate_delete"),

    # Instructor: export day's register to PDF
    path("app/instructor/day/<int:pk>/registers/pdf/", instv.instructor_day_registers_pdf, name="instructor_day_registers_pdf"),

    # ---------- Public delegate register ----------
    path("register/", views.public_delegate_register, name="public_delegate_register"),
    path("register/instructors", views.public_delegate_instructors_api, name="public_delegate_instructors_api"),

    # ---------- Public/API helpers ----------
    path("public/attendance/<int:booking_day_id>/", views.public_attendance, name="public_attendance"),
    path("api/locations/", views.api_locations_by_business, name="api_locations_by_business"),

    # ---------- Admin dashboard ----------
    path("app/admin/", app_admin.dashboard, name="app_admin_dashboard"),

    # Businesses
    path("app/admin/businesses/", app_admin.business_list, name="admin_business_list"),
    path("app/admin/businesses/new/", app_admin.business_form, name="admin_business_new"),
    path("app/admin/businesses/<uuid:pk>/", app_admin.business_form, name="admin_business_edit"),
    path("app/admin/businesses/<uuid:pk>/delete/", app_admin.business_delete, name="admin_business_delete"),

    # Training Locations
    path("app/admin/businesses/<uuid:business_id>/locations/new/", app_admin.location_new, name="admin_location_new"),
    path("app/admin/locations/<uuid:pk>/", app_admin.location_edit, name="admin_location_edit"),
    path("app/admin/locations/<uuid:pk>/delete/", app_admin.location_delete, name="admin_location_delete"),


    # Course Types
    path("app/admin/courses/", app_admin.course_list, name="admin_course_list"),
    path("app/admin/courses/new/", app_admin.course_form, name="admin_course_new"),
    path("app/admin/courses/<uuid:pk>/", app_admin.course_form, name="admin_course_edit"),
    path("app/admin/courses/<uuid:pk>/delete/", app_admin.course_delete, name="admin_course_delete"),
    path("app/admin/course-types/", app_admin.course_list, name="admin_course_type_list"),  # alias

    # Instructors (admin)
    path("app/admin/instructors/", app_admin.admin_instructor_list, name="admin_instructor_list"),
    path("app/admin/instructors/new/", app_admin.admin_instructor_new, name="admin_instructor_new"),
    path("app/admin/instructors/<uuid:pk>/", app_admin.admin_instructor_edit, name="admin_instructor_edit"),
    path("app/admin/instructors/<uuid:pk>/delete/", app_admin.instructor_delete, name="admin_instructor_delete"),
    path("app/instructor/booking/<uuid:pk>/invoice/preview/", views_instructor.invoice_preview, name="instructor_invoice_preview"),

    # Bookings (admin)
    path("app/admin/bookings/", app_admin.booking_list, name="admin_booking_list"),
    path("app/admin/bookings/new/", app_admin.booking_form, name="admin_booking_new"),
    path("app/admin/bookings/<uuid:pk>/", app_admin.booking_form, name="admin_booking_edit"),
    path("app/admin/bookings/<uuid:pk>/delete/", app_admin.booking_delete, name="admin_booking_delete"),
    path("app/admin/bookings/<uuid:pk>/cancel/", app_admin.booking_cancel, name="admin_booking_cancel"),
    path("app/admin/bookings/<uuid:pk>/reinstate/", app_admin.booking_reinstate, name="admin_booking_reinstate"),
    path("app/admin/bookings/<uuid:pk>/unlock/", app_admin.booking_unlock, name="admin_booking_unlock"),

    # Users (admin) – ints
    path("app/admin/users/", app_admin.admin_user_list, name="admin_user_list"),
    path("app/admin/users/new/", app_admin.admin_user_new, name="admin_user_new"),
    path("app/admin/users/<int:pk>/", app_admin.admin_user_edit, name="admin_user_edit"),

    # Registers (admin)
    path("app/admin/booking-days/<int:pk>/registers/", app_admin.booking_day_registers, name="admin_booking_day_registers"),
    path("app/admin/registers/<int:pk>/delete/", app_admin.delegate_register_delete, name="admin_register_delete"),

    # ---------- Debug ----------
    path("debug/whoami/", instv.whoami, name="debug_whoami"),

    # ---------- Auth ----------
    path("accounts/login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),

    # ---------- Assessments ----------
    # (matrix is embedded in booking detail; these are save/export endpoints)
    path("app/instructor/booking/<uuid:pk>/assessment/save/", instv.instructor_assessment_save, name="instructor_assessment_save"),
    path("app/instructor/booking/<uuid:pk>/assessment/pdf/", instv.instructor_assessment_pdf, name="instructor_assessment_pdf"),

    # ---------- Public Feedback (QR-driven form) ----------
    path("feedback/", views.public_feedback_form, name="public_feedback_form"),
    path("feedback/thanks/", views.public_feedback_thanks, name="public_feedback_thanks"),
    path("feedback/<uuid:pk>/pdf/", views.public_feedback_pdf, name="public_feedback_pdf"),
    path("feedback/instructors", views.public_feedback_instructors_api, name="public_feedback_instructors_api"),

    # ---------- Instructor: Feedback tab + detail + exports ----------
    path("app/instructor/booking/<uuid:booking_id>/feedback/", instv.instructor_feedback_tab, name="instructor_feedback_tab"),
    path("app/instructor/feedback/<uuid:pk>/", instv.instructor_feedback_view, name="instructor_feedback_view"),
    path("app/instructor/booking/<uuid:booking_id>/feedback/pdf/all/", instv.instructor_feedback_pdf_all, name="instructor_feedback_pdf_all"),
    path("app/instructor/booking/<uuid:booking_id>/feedback/pdf/summary/", instv.instructor_feedback_pdf_summary, name="instructor_feedback_pdf_summary"),

    
]
