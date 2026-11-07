from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_POST

from account.decorators import customer_ui_required, owner_ui_required
from restaurants.models import Restaurant

from . import services


def _owner_restaurant(request):
    # Owners only ever reach their own store; no store means nothing to manage.
    restaurant = Restaurant.objects.filter(owner=request.user).first()
    if restaurant is None:
        raise Http404("No store")
    return restaurant


def _state(restaurant, status=200, **extra):
    return JsonResponse({**services.snapshot(restaurant), **extra}, status=status)


def _action(request, run):
    """Run a queue action for the owner's store and answer with the fresh state."""
    restaurant = _owner_restaurant(request)
    try:
        message = run(restaurant)
    except services.QueueError as exc:
        return _state(restaurant, status=409, error=str(exc))
    return _state(restaurant, message=message)


@owner_ui_required
@require_GET
def queue_data_view(request):
    return _state(_owner_restaurant(request))


@owner_ui_required
@require_POST
def queue_add_view(request):
    def run(restaurant):
        entry = services.add_entry(
            restaurant,
            name=request.POST.get("name", ""),
            party_size=request.POST.get("party") or 2,
        )
        return f"{entry.code} added to the queue."

    return _action(request, run)


@owner_ui_required
@require_POST
def queue_call_next_view(request):
    return _action(request, lambda r: f"{services.call_next(r).code} is now being served.")


@owner_ui_required
@require_POST
def queue_call_again_view(request):
    return _action(request, lambda r: f"Calling {services.call_again(r).code} again.")


def _after(entry, following, verb):
    tail = f"{following.code} is now being served." if following else "No queues are waiting."
    return f"{entry.code} {verb}. {tail}"


@owner_ui_required
@require_POST
def queue_complete_view(request):
    return _action(request, lambda r: _after(*services.complete(r), "completed"))


@owner_ui_required
@require_POST
def queue_skip_view(request):
    return _action(request, lambda r: _after(*services.skip(r), "skipped"))


@owner_ui_required
@require_POST
def queue_recall_view(request, entry_id):
    def run(restaurant):
        entry = services.recall(restaurant, entry_id)
        if entry.status == entry.Status.SERVING:
            return f"{entry.code} is now being served."
        return f"{entry.code} will be called after the current queue."

    return _action(request, run)


@owner_ui_required
@require_POST
def queue_pause_view(request):
    def run(restaurant):
        paused = services.set_paused(restaurant, request.POST.get("paused") == "1")
        return "New queues are paused." if paused else "New queues are open."

    return _action(request, run)


# Customer side ---------------------------------------------------------------


@customer_ui_required
@require_POST
def join_queue_view(request, slug):
    restaurant = get_object_or_404(Restaurant.objects.published(), slug=slug)
    try:
        entry = services.join_queue(request.user, restaurant, request.POST.get("party"))
    except services.QueueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"You're in line at {restaurant.name}: {entry.code}.")
    return redirect("my_queues")


@customer_ui_required
@require_GET
def my_queue_data_view(request):
    return JsonResponse({"queues": services.guest_queues(request.user)})


@customer_ui_required
@require_POST
def leave_queue_view(request, entry_id):
    try:
        services.leave_queue(request.user, entry_id)
    except services.QueueError as exc:
        return JsonResponse({"error": str(exc), "queues": services.guest_queues(request.user)}, status=409)
    return JsonResponse({"queues": services.guest_queues(request.user)})
