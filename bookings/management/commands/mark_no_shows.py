from django.core.management.base import BaseCommand

from bookings import services


class Command(BaseCommand):
    help = (
        "Mark confirmed bookings as no-show once the restaurant's grace period has "
        "passed. Safe to run repeatedly, for example from cron."
    )

    def handle(self, *args, **options):
        count = services.mark_no_shows()
        self.stdout.write(self.style.SUCCESS(f"{count} booking(s) marked as no-show."))
