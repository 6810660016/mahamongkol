from django.urls import path

from . import views

# Owner pages live in `dashboard`; /owner/queue/… are the JSON endpoints behind them.
# queue/… is the customer side (join from a restaurant page, live status on My Q).
urlpatterns = [
    path("owner/queue/data/", views.queue_data_view, name="owner_queue_data"),
    path("owner/queue/add/", views.queue_add_view, name="owner_queue_add"),
    path("owner/queue/call-next/", views.queue_call_next_view, name="owner_queue_call_next"),
    path("owner/queue/call-again/", views.queue_call_again_view, name="owner_queue_call_again"),
    path("owner/queue/complete/", views.queue_complete_view, name="owner_queue_complete"),
    path("owner/queue/skip/", views.queue_skip_view, name="owner_queue_skip"),
    path("owner/queue/<int:entry_id>/recall/", views.queue_recall_view, name="owner_queue_recall"),
    path("owner/queue/pause/", views.queue_pause_view, name="owner_queue_pause"),
    path("queue/join/<slug:slug>/", views.join_queue_view, name="queue_join"),
    path("queue/mine/", views.my_queue_data_view, name="my_queue_data"),
    path("queue/<int:entry_id>/leave/", views.leave_queue_view, name="queue_leave"),
]
