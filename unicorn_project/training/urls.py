from django.urls import path
from . import views
from . import views_admin as app_admin   # <- alias your app’s admin views

urlpatterns = [
    # Home + role switch
    path('', views.home, name='home'),
    path('switch-role/<str:role>/', views.switch_role, name='switch_role'),

    # Instructor side
    path('app/instructor/', views.instructor_dashboard, name='instructor_dashboard'),
    path('app/instructor/bookings/', views.instructor_bookings, name='instructor_bookings'),
    path('app/instructor/booking/<uuid:pk>/', views.instructor_booking_detail, name='instructor_booking_detail'),
    path('app/instructor/profile/', views.instructor_profile, name='instructor_profile'),

    # Public + API
    path('public/attendance/<uuid:booking_day_id>/', views.public_attendance, name='public_attendance'),
    path('api/locations/', views.api_locations_by_business, name='api_locations_by_business'),

    # Admin area (your custom UI)
    path('app/admin/', app_admin.dashboard, name='app_admin_dashboard'),

    # Businesses
    path('app/admin/businesses/',                 app_admin.business_list,  name='admin_business_list'),
    path('app/admin/businesses/new/',             app_admin.business_form,  name='admin_business_new'),
    path('app/admin/businesses/<uuid:pk>/',       app_admin.business_form,  name='admin_business_edit'),

    # Training Locations
    path('app/admin/businesses/<uuid:business_id>/locations/new/', app_admin.location_new, name='admin_location_new'),
    path('app/admin/locations/<uuid:pk>/',        app_admin.location_edit,  name='admin_location_edit'),

    # Course Types
    path('app/admin/courses/',                    app_admin.course_list,    name='admin_course_list'),
    path('app/admin/courses/new/',                app_admin.course_form,    name='admin_course_new'),
    path('app/admin/courses/<uuid:pk>/',          app_admin.course_form,    name='admin_course_edit'),
    path('app/admin/course-types/',               app_admin.course_list,    name='admin_course_type_list'),

    # Personnel (Instructors)
    path('app/admin/instructors/',                app_admin.instructor_list,        name='admin_instructor_list'),
    path('app/admin/instructors/new/',            app_admin.admin_instructor_new,   name='admin_instructor_new'),
    path('app/admin/instructors/<uuid:pk>/',      app_admin.admin_instructor_edit,  name='admin_instructor_edit'),

    # Bookings
    path('app/admin/bookings/',                   app_admin.booking_list,   name='admin_booking_list'),
    path('app/admin/bookings/new/',               app_admin.booking_form,   name='admin_booking_new'),
    path('app/admin/bookings/<uuid:pk>/',         app_admin.booking_form,   name='admin_booking_edit'),

    # Users (custom simple UI)
    path('app/admin/users/',                      app_admin.admin_user_list, name='admin_user_list'),
    path('app/admin/users/new/',                  app_admin.admin_user_new,  name='admin_user_new'),
    path('app/admin/users/<int:pk>/',             app_admin.admin_user_edit, name='admin_user_edit'),
]
