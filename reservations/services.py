from django.db import transaction
from django.utils import timezone

from catalog.models import Egzemplarz, Ksiazka
from reservations.models import Rezerwacja


def expire_reservations(now=None):
    """Wygasza nieodebrane rezerwacje i zwraca ich liczbę."""
    now = now if now is not None else timezone.now()

    book_ids = list(
        Rezerwacja.objects.filter(
            status=Rezerwacja.Status.OCZEKUJACA,
            termin_odbioru__lte=now,
        )
        .order_by()
        .values_list("egzemplarz__ksiazka_id", flat=True)
        .distinct()
    )

    if not book_ids:
        return 0

    with transaction.atomic():
        # blokujemy książki, egzemplarze i rezerwacje
        list(Ksiazka.objects.select_for_update().filter(pk__in=book_ids).order_by("pk"))

        copy_ids = list(
            Egzemplarz.objects.select_for_update()
            .filter(ksiazka_id__in=book_ids)
            .order_by("pk")
            .values_list("pk", flat=True)
        )

        expired = list(
            Rezerwacja.objects.select_for_update()
            .filter(
                egzemplarz_id__in=copy_ids,
                status=Rezerwacja.Status.OCZEKUJACA,
                termin_odbioru__lte=now,
            )
            .order_by("pk")
            .values_list("pk", "egzemplarz_id")
        )

        if not expired:
            return 0

        # pobranie id przeterminowanych rezerwacji i ich egzemplarzy
        reservation_ids = [reservation_id for reservation_id, _ in expired]
        expired_copy_ids = [copy_id for _, copy_id in expired]

        # zmiana statusu rezerwacji na WYGASLA
        Rezerwacja.objects.filter(pk__in=reservation_ids).update(
            status=Rezerwacja.Status.WYGASLA,
        )

        # udostępnienie egzemplarza ponownie do wypożyczania
        Egzemplarz.objects.filter(pk__in=expired_copy_ids).update(
            dostepny=True,
        )

        return len(expired)
