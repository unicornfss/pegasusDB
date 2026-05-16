from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views

from . import views
from . import views_admin
from . import views_admin as app_admin
from . import views_engineer as engv
from . import views_inspector as inspv
from . import views_instructor as instv
from . import views_instructor
from . import views_public
from . import views_telegram

from .views_public import (
    delegate_exam_start,      # start (enter details / match register)
    delegate_exam_rules,      # rules screen
    delegate_exam_run,        # run the exam (Q&A screen)
    delegate_exam_review,     # review answers before submit
    delegate_exam_finish,     # results
)

from . import views_certificates

from .views_admin import meta_settings_list, meta_settings_edit


urlpatterns = [
    # ---------- Core / Home ----------
    path("", views.home, name="home"),
    path("switch-role/<str:role>/", views.switch_role, name="switch_role"),

    # Post-login routers
    # path("app/after-login/", instv.post_login, name="post_login"),
    path("post-login/", views_instructor.post_login, name="post_login"),

    # ---------- Instructor area ----------
    # Landing page -> My bookings
    path("app/instructor/", instv.instructor_dashboard, name="instructor_dashboard"),
    path("app/instructor/bookings/", instv.instructor_bookings, name="instructor_bookings"),
    path("app/instructor/practice-bookings/new/<uuid:business_id>/", instv.instructor_dummy_booking_new, name="instructor_dummy_booking_new"),
    path("app/instructor/booking/<uuid:pk>/", instv.instructor_booking_detail, name="instructor_booking_detail"),
    path("app/instructor/booking/<uuid:pk>/delete-dummy/", instv.instructor_delete_dummy_booking, name="instructor_delete_dummy_booking"),
    path("app/instructor/day/<int:pk>/registers/", instv.instructor_day_registers, name="instructor_day_registers"),
    path("app/instructor/register/<int:pk>/edit/", instv.instructor_delegate_edit, name="instructor_delegate_edit"),
    path("app/instructor/day/<int:day_pk>/registers/new/", instv.instructor_delegate_new, name="instructor_delegate_new"),
    path("app/profile/", views.user_profile, name="user_profile"),
    path("app/preferences/night-mode/", views.toggle_night_mode, name="toggle_night_mode"),
    path("app/instructor/day/<int:pk>/registers/send-pdf/", views_instructor.instructor_day_registers_pdf, name="instructor_day_registers_pdf"),
    path("app/instructor/day/<int:pk>/registers/poll/", views_instructor.instructor_day_registers_poll, name="instructor_day_registers_poll"),
    path("app/instructor/booking/<uuid:pk>/upload-receipt/", instv.instructor_upload_receipt, name="instructor_upload_receipt"),
    path("app/instructor/booking/<uuid:pk>/receipts/", instv.instructor_list_receipts, name="instructor_list_receipts",),
    path("app/instructor/booking/<uuid:pk>/delete-receipt/", instv.instructor_delete_receipt, name="instructor_delete_receipt",),
    path("instructor/booking/<uuid:pk>/fee/", views_instructor.booking_fee, name="booking-fee"),
    path("instructor/booking/<uuid:pk>/course-summary.pdf", views_instructor.instructor_course_summary_pdf, name="instructor_course_summary_pdf"),
    path("instructor/booking/ref/<slug:ref>/course-summary.pdf", views_instructor.instructor_course_summary_by_ref_pdf, name="instructor_course_summary_by_ref_pdf"),
    path("instructor/booking/<uuid:pk>/certificates/", instv.instructor_booking_certificates_pdf, name="instructor_booking_certificates"),
    path("app/instructor/home/", instv.instructor_dashboard, name="instructor_home"),

    
    # Instructor: delete a delegate row
    path("app/instructor/register/<int:pk>/delete/", instv.instructor_delegate_delete, name="instructor_delegate_delete"),

    # Instructor: export day's register to PDF
    path("app/instructor/day/<int:pk>/registers/pdf/", instv.instructor_day_registers_pdf, name="instructor_day_registers_pdf"),

    # ---------- Public delegate register ----------
    path("register/", views.public_delegate_register, name="public_delegate_register"),
    path("register/success/", views.public_delegate_register_success, name="public_delegate_register_success"),
    path("register/instructors/", views.public_delegate_instructors_api, name="public_delegate_instructors_api"),

    # ---------- Public/API helpers ----------
    path("public/attendance/<int:booking_day_id>/", views.public_attendance, name="public_attendance"),
    path("api/locations/", views.api_locations_by_business, name="api_locations_by_business"),

    # ---------- Admin dashboard ----------
    path("app/admin/", views_admin.admin_dashboard, name="app_admin_dashboard"),
    path("app/admin/courses/<uuid:pk>/", app_admin.course_form, name="admin_course_edit"),
    path("app/admin/exams/<int:pk>/", app_admin.exam_form, name="admin_exam_edit"),
    path("delegates/search/", views_admin.admin_delegate_search, name="admin_delegate_search"),
    path("app-admin/dashboard/", views_admin.admin_dashboard, name="admin_dashboard"),
    path("app-admin/api/courses-today/", views_admin.api_courses_today, name="api_courses_today"),
    path("app-admin/api/courses-awaiting-closure/", views_admin.api_courses_awaiting_closure, name="api_courses_awaiting_closure"),
    path("app-admin/api/courses-in-7-days/", views_admin.api_courses_in_7_days, name="api_courses_in_7_days"),
    path("api/outstanding-invoices/", views_admin.api_outstanding_invoices, name="api_outstanding_invoices"),

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
    path("app/admin/personnel/", app_admin.admin_personnel_list, name="admin_personnel_list"),
    path("app/admin/personnel/new/", app_admin.admin_personnel_new, name="admin_personnel_new"),
    path("app/admin/personnel/<uuid:pk>/", app_admin.admin_personnel_edit, name="admin_personnel_edit"),
    path("app/admin/personnel/<uuid:pk>/delete/", app_admin.admin_personnel_delete, name="admin_personnel_delete"),

    # Telegram linking
    path("telegram/link-token/", views_telegram.telegram_link_token, name="telegram_link_token"),
]