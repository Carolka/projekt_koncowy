from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import PermissionDenied

from catalog.models import Egzemplarz, Ksiazka
from reservations.models import Rezerwacja


# własne wyjątki
class AlreadyReserved(Exception):
    """Użytkownik ma już bieżącą rezerwacje tej książki."""


class NoAvailableCopy(Exception):
    """Brak egzemplarza, który można zarezerwować."""


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


def reserve_book(user, book_id):
    """Rezerwuje dostępny egzemplarz i zwraca utworzoną rezerwację."""

    # użytkownik zalogowany i aktywny
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied("Rezerwacja tylko dla zalogowanych i aktywnych kont.")

    with transaction.atomic():
        # ksiazka, egzemplarze, rezerwacje
        ksiazka = Ksiazka.objects.select_for_update().get(pk=book_id)

        egzemplarze = list(
            Egzemplarz.objects.select_for_update()
            .filter(ksiazka=ksiazka)
            .order_by("pk")
        )

        now = timezone.now()

        # wygaszamy przeterminowane rezerwacje dla wybranej ksiazki
        wygasle_rezerwacje = list(
            Rezerwacja.objects.select_for_update()
            .filter(
                egzemplarz__ksiazka=ksiazka,
                status=Rezerwacja.Status.OCZEKUJACA,
                termin_odbioru__lte=now,
            )
            .order_by("pk")
            .values_list("pk", "egzemplarz_id")
        )

        if wygasle_rezerwacje:
            rezerwacja_ids = [rezerwacja_id for rezerwacja_id, _ in wygasle_rezerwacje]

            egzemplarz_ids = [egzemplarz_id for _, egzemplarz_id in wygasle_rezerwacje]

            Rezerwacja.objects.filter(pk__in=rezerwacja_ids).update(
                status=Rezerwacja.Status.WYGASLA,
            )

            Egzemplarz.objects.filter(pk__in=egzemplarz_ids).update(dostepny=True)

        # czy są jakieś aktualne rezerwacje książki
        biezace_rezerwacje = Rezerwacja.objects.filter(
            egzemplarz__ksiazka=ksiazka,
            status__in=[
                Rezerwacja.Status.OCZEKUJACA,
                Rezerwacja.Status.ODEBRANA,
            ],
        )

        # filtrujemy po uzytkowniku - sprawdzamy czy juz zarezerwowal ta ksiazke
        if biezace_rezerwacje.filter(uzytkownik=user).exists():
            raise AlreadyReserved("Masz już tę książkę zarezerwowaną lub odebraną.")

        # pobranie z aktywnych rezerwacji id egzemplarzy - do wykluczenia tych już zajetych
        zajete_egzemplarz_ids = biezace_rezerwacje.values_list(
            "egzemplarz_id", flat=True
        )

        # pobieramy wolny egzemplarz
        egzemplarz = (
            Egzemplarz.objects.filter(
                pk__in=[egzemplarz.pk for egzemplarz in egzemplarze],
                aktywny=True,
                dostepny=True,
            )
            .exclude(pk__in=zajete_egzemplarz_ids)
            .order_by("pk")
            .first()
        )

        if egzemplarz is None:
            raise NoAvailableCopy("Brak dostępnych egzemplarzy tej książki.")

        # tworzymy rezerwację
        rezerwacja = Rezerwacja.objects.create(
            uzytkownik=user,
            egzemplarz=egzemplarz,
            status=Rezerwacja.Status.OCZEKUJACA,
            utworzona_at=now,
            termin_odbioru=now + timedelta(hours=48),
        )
        egzemplarz.dostepny = False
        egzemplarz.save(update_fields=["dostepny"])

        return rezerwacja
