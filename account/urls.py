from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("signup/owner/", views.owner_signup_view, name="owner_signup"),
    path("owner/application/", views.owner_application_status_view, name="owner_application_status"),
    path("staff/owner-applications/", views.owner_applications_admin_view, name="owner_applications_admin"),
    path("staff/owner-applications/<int:application_id>/approve/", views.approve_owner_application_view, name="approve_owner_application"),
    path("logout/", views.logout_view, name="logout"),
    path("switch-ui/", views.switch_ui_view, name="switch_ui"),
    path("settings/", views.settings_view, name="settings"),
]
