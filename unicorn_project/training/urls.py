# unicorn_project/training/urls.py
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
    path("app/instructor/booking/<uuid:pk>/", instv.instructor_booking_detail, name="instructor_booking_detail"),
    path("app/instructor/day/<int:pk>/registers/", instv.instructor_day_registers, name="instructor_day_registers"),
    path("app/instructor/register/<int:pk>/edit/", instv.instructor_delegate_edit, name="instructor_delegate_edit"),
    path("app/instructor/day/<int:day_pk>/registers/new/", instv.instructor_delegate_new, name="instructor_delegate_new"),
    path("app/profile/", views.user_profile, name="user_profile"),
    path("app/instructor/day/<int:pk>/registers/send-pdf/", views_instructor.instructor_day_registers_pdf, name="instructor_send_register_pdf"),
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
    path("app/instructor/booking/<uuid:pk>/invoice/preview/", views_instructor.invoice_preview, name="instructor_invoice_preview"),
    path("accident-reports/", views.accident_report_list, name="accident_report_list"),
    path("app/admin/personnel/<uuid:pk>/resend-password/", app_admin.admin_personnel_resend_password, name="admin_personnel_resend_password"),
    path("app/instructor/booking/<uuid:booking_id>/ics/", views_instructor.download_booking_ics, name="download_booking_ics"),
    path("app/instructor/resources/", instv.instructor_resources, name="instructor_resources"),



    # Bookings (admin)
    path("app/admin/bookings/", app_admin.booking_list, name="admin_booking_list"),
    path("app/admin/bookings/new/", app_admin.booking_form, name="admin_booking_new"),
    path("app/admin/bookings/<uuid:pk>/", app_admin.booking_form, name="admin_booking_edit"),
    path("admin/bookings/<uuid:pk>/invoice-pdf/", views_admin.admin_invoice_pdf, name="admin_invoice_pdf"),
    path("app/admin/bookings/<uuid:pk>/certificates/", app_admin.admin_booking_certificates_selected, name="admin_booking_certificates_selected"),
    path("app/admin/registers/<int:reg_pk>/certificate-name/", app_admin.admin_certificate_name_edit, name="admin_certificate_name_edit"),


    path("app/admin/bookings/<uuid:pk>/delete/", app_admin.booking_delete, name="admin_booking_delete"),
    path("app/admin/bookings/<uuid:pk>/cancel/", app_admin.booking_cancel, name="admin_booking_cancel"),
    path("app/admin/bookings/<uuid:pk>/reinstate/", app_admin.booking_reinstate, name="admin_booking_reinstate"),
    path("app/admin/bookings/<uuid:pk>/unlock/", app_admin.booking_unlock, name="admin_booking_unlock"),
    path('admin/invoice/<uuid:pk>/pdf/', views_admin.admin_invoice_pdf, name='admin_invoice_pdf'),


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
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),

    path(
        "accounts/logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),

    path(
        "accounts/password_change/",
        auth_views.PasswordChangeView.as_view(
            template_name="registration/password_change_form.html",
            success_url="/accounts/password_change/done/",
        ),
        name="password_change",
    ),

    path(
        "accounts/password_change/done/",
        views_admin.password_change_done_and_clear,
        name="password_change_done",
    ),


    # ---------- Assessments ----------
    # (matrix is embedded in booking detail; these are save/export endpoints)
    path("app/instructor/booking/<uuid:pk>/assessment/save/", instv.instructor_assessment_save, name="instructor_assessment_save"),
    path("app/instructor/booking/<uuid:pk>/assessment/pdf/", instv.instructor_assessment_pdf, name="instructor_assessment_pdf"),
    path("app/instructor/booking/<uuid:pk>/assessments/autosave/", views_instructor.instructor_assessment_autosave,name="instructor_assessment_autosave"),
    path("app/instructor/booking/<uuid:pk>/assessments/outcome/", views_instructor.instructor_assessment_outcome_autosave, name="instructor_assessment_outcome_autosave"),

    # ---------- Public Feedback (QR-driven form) ----------
    path("feedback/", views.public_feedback_form, name="public_feedback_form"),
    path("feedback/thanks/", views.public_feedback_thanks, name="public_feedback_thanks"),
    path("feedback/<uuid:pk>/pdf/", views.public_feedback_pdf, name="public_feedback_pdf"),
    path("feedback/instructors", views.public_feedback_instructors_api, name="public_feedback_instructors_api"),

    # ---------- Instructor: Feedback tab + detail + exports ----------
    path("app/instructor/booking/<uuid:booking_id>/feedback/", instv.instructor_feedback_tab, name="instructor_feedback_tab"),
    path("app/instructor/booking/<uuid:booking_id>/feedback/poll/", instv.instructor_feedback_poll, name="instructor_feedback_poll"),
    path("app/instructor/feedback/<uuid:pk>/", instv.instructor_feedback_view, name="instructor_feedback_view"),
    path("app/instructor/booking/<uuid:booking_id>/feedback/pdf/all/", instv.instructor_feedback_pdf_all, name="instructor_feedback_pdf_all"),
    path("app/instructor/booking/<uuid:booking_id>/feedback/pdf/summary/", instv.instructor_feedback_pdf_summary, name="instructor_feedback_pdf_summary"),


    path("diag/email/", instv.email_diagnostics, name="email_diagnostics"),

    path("exam/", views_public.delegate_exam_start, name="delegate_exam_start"),
    path("exam/rules/", views_public.delegate_exam_rules, name="delegate_exam_rules"),
    path("exam/run/", views_public.delegate_exam_run, name="delegate_exam_run"),
    path("exam/review/", views_public.delegate_exam_review, name="delegate_exam_review"),
    path("exam/finish/", views_public.delegate_exam_finish, name="delegate_exam_finish"),
    path("privacy/", views_public.privacy_notices, name="privacy_notices"),
    path("accident-report/", views.accident_report_public, name="accident_report_public"),
    path("accident-report/thanks/", views.accident_report_thanks, name="accident_report_thanks"),

    path("accident-reports/<uuid:pk>/", views.accident_report_detail, name="accident_report_detail"),
    path("accident-reports/export-pptx/", views.accident_report_export_pptx, name="accident_report_export_pptx"),
    path("accident-reports/delete/", views.accident_report_delete, name="accident_report_delete"),
    path("accident-reports/poll/", views.accident_report_poll, name="accident_report_poll"),
    path("accident-reports/anonymise", views.accident_report_anonymise, name="accident_report_anonymise"),
    
    path(
        "app/instructor/exams/attempt/<int:attempt_id>/review/",
        views_instructor.instructor_attempt_review,
        name="instructor_attempt_review",
    ),
    path(
        "app/instructor/exams/attempt/<int:attempt_id>/incorrect/",
        views_instructor.instructor_attempt_incorrect,
        name="instructor_attempt_incorrect",
    ),
    path(
    "app/instructor/exams/attempt/<int:attempt_id>/authorize-retake/",
    instv.instructor_attempt_authorize_retake,
    name="instructor_attempt_authorize_retake",
),
    

    path(
    "app/instructor/whoami/",
    instv.whoami,
    name="instructor_whoami",
),

    path("bookings/<uuid:booking_id>/certificates/preview/", views_certificates.booking_certificates_preview, name="booking_certificates_preview")  ,


        # Engineer
    path("app/engineer/", engv.engineer_dashboard, name="engineer_dashboard"),

    # Inspector
    path("app/inspector/", inspv.inspector_dashboard, name="inspector_dashboard"),

    path("app/no-roles/", views.no_roles_assigned, name="no_roles"),

    path(
        "api/instructor/<uuid:pk>/postcode/",
        views_admin.api_instructor_postcode,
        name="api_instructor_postcode",
    ),

    path("app/admin/meta-settings/", meta_settings_list, name="admin_meta_settings"),
    path("app/admin/meta-settings/<int:pk>/", meta_settings_edit, name="admin_meta_settings_edit"),

]



