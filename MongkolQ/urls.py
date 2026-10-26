from django.contrib import admin
from django.urls import path
from account import views as view_account

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', view_account.welcome_view, name='welcome'),
    path('login/', view_account.login_view, name='login'),
    path('signup/', view_account.signup_view, name='signup'),
    path('welcome/', view_account.welcome_view, name='welcome'),
    path('home/', view_account.home_view, name='home'),
    path('restaurants/', view_account.restaurants_view, name='restaurants'),
    path('restaurants/<slug:slug>/', view_account.restaurant_detail_view, name='restaurant_detail'),
    path('book/<slug:slug>/', view_account.booking_view, name='booking'),
    path('my-queues/', view_account.my_queues_view, name='my_queues'),
    path('settings/', view_account.settings_view, name='settings'),
    path('cancel-booking/<int:booking_id>/', view_account.cancel_booking_view, name='cancel_booking'),
]
