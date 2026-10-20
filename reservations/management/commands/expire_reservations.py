from django.core.management.base import BaseCommand

from reservations.services import expire_reservations


class Command(BaseCommand):
    help = "Wygasza rezerwacje, których termin odbioru minął."

    def handle(self, *args, **options):
        liczba = expire_reservations()
        self.stdout.write(
            self.style.SUCCESS(f"Liczba wygaszonych rezerwacji: {liczba}")
        )
