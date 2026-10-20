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


class ReservationNotCancellable(Exception):
    """Rezerwacji nie można anulować w jej obecnym stanie."""


class ReservationNotCollectable(Exception):
    """Rezerwacji nie można odebrać w jej obecnym stanie."""


class ReservationNotReturnable(Exception):
    """Rezerwacji nie można zwrócić w jej obecnym stanie."""


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


def cancel_reservation(reservation_id, user):
    """Anuluje oczekującą rezerwację przed terminem odbioru."""

    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied("Anulowanie wymaga zalogowanego, aktywnego konta.")

    with transaction.atomic():
        powiazania = Rezerwacja.objects.values(
            "egzemplarz_id",
            "egzemplarz__ksiazka_id",
        ).get(pk=reservation_id)

        Ksiazka.objects.select_for_update().get(
            pk=powiazania["egzemplarz__ksiazka_id"],
        )

        egzemplarz = Egzemplarz.objects.select_for_update().get(
            pk=powiazania["egzemplarz_id"],
        )

        rezerwacja = Rezerwacja.objects.select_for_update().get(
            pk=reservation_id,
        )

        # sprawdzamy czy użytkownik chce anulować swoją rezerwację lub czy ma uprawnienia
        if rezerwacja.uzytkownik_id != user.pk and not user.has_perm(
            "reservations.cancel_reservation"
        ):
            raise PermissionDenied(
                "Nie masz odpowiednich uprawnień do anulowania tej rezerwacji."
            )

        # Ponowne anulowanie nie zmienia dat ani dostępności egzemplarza.
        if rezerwacja.status == Rezerwacja.Status.ANULOWANA:
            return rezerwacja

        if rezerwacja.status != Rezerwacja.Status.OCZEKUJACA:
            raise ReservationNotCancellable(
                "Anulować można tylko rezerwację oczekującą na odbiór."
            )

        now = timezone.now()

        if rezerwacja.termin_odbioru <= now:
            raise ReservationNotCancellable(
                "Termin odbioru minął. Rezerwacji nie można już anulować."
            )

        rezerwacja.status = Rezerwacja.Status.ANULOWANA
        rezerwacja.anulowana_at = now
        rezerwacja.save(update_fields=["status", "anulowana_at"])
        # udostępnienie egzemplarza do wypożyczania
        egzemplarz.dostepny = True
        egzemplarz.save(update_fields=["dostepny"])

        return rezerwacja


def collect_reservation(reservation_id, user):
    """Potwierdza odbiór książki przed terminem i ustala termin zwrotu."""
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied(
            "Potwierdzenie odbioru wymaga zalogowanego, aktywnego konta."
        )

    if not user.has_perm("reservations.collect_reservation"):
        raise PermissionDenied("Nie masz uprawnień do potwierdzania odbioru książek.")

    with transaction.atomic():
        powiazania = Rezerwacja.objects.values(
            "egzemplarz_id",
            "egzemplarz__ksiazka_id",
        ).get(pk=reservation_id)

        Ksiazka.objects.select_for_update().get(
            pk=powiazania["egzemplarz__ksiazka_id"],
        )

        egzemplarz = Egzemplarz.objects.select_for_update().get(
            pk=powiazania["egzemplarz_id"],
        )

        rezerwacja = Rezerwacja.objects.select_for_update().get(
            pk=reservation_id,
        )

        # jeśli odbiór został już potwierdzony zakańczamy bez zmiany daty odbioru i terminu zwrotu
        if rezerwacja.status == Rezerwacja.Status.ODEBRANA:
            return rezerwacja

        # Rezerwacji wygasłej nie można odebrać.
        if rezerwacja.status == Rezerwacja.Status.WYGASLA:
            raise ReservationNotCollectable(
                "Termin odbioru minął. Utwórz nową rezerwację."
            )

        if rezerwacja.status != Rezerwacja.Status.OCZEKUJACA:
            raise ReservationNotCollectable(
                "Odebrać można tylko książkę z rezerwacją oczekującą."
            )

        now = timezone.now()

        if rezerwacja.termin_odbioru <= now:
            raise ReservationNotCollectable(
                "Termin odbioru minął. Utwórz nową rezerwację."
            )

        rezerwacja.status = Rezerwacja.Status.ODEBRANA
        rezerwacja.odebrana_at = now
        rezerwacja.termin_zwrotu = now + timedelta(days=14)
        rezerwacja.save(
            update_fields=["status", "odebrana_at", "termin_zwrotu"],
        )

        egzemplarz.dostepny = False
        egzemplarz.save(update_fields=["dostepny"])

        return rezerwacja


def return_reservation(reservation_id, user):
    """Potwierdza zwrot odebranego egzemplarza."""
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied(
            "Potwierdzenie zwrotu wymaga zalogowanego, aktywnego konta."
        )

    if not user.has_perm("reservations.return_reservation"):
        raise PermissionDenied("Nie masz uprawnień do potwierdzania zwrotu książek.")

    with transaction.atomic():
        powiazania = Rezerwacja.objects.values(
            "egzemplarz_id",
            "egzemplarz__ksiazka_id",
        ).get(pk=reservation_id)

        Ksiazka.objects.select_for_update().get(
            pk=powiazania["egzemplarz__ksiazka_id"],
        )

        egzemplarz = Egzemplarz.objects.select_for_update().get(
            pk=powiazania["egzemplarz_id"],
        )

        rezerwacja = Rezerwacja.objects.select_for_update().get(
            pk=reservation_id,
        )

        # jeśli jest już zakończona — nie zmieniamy ponownie jej daty zwrotu
        # ani dostępności egzemplarza, który mógł już zostać zarezerwowany.
        if rezerwacja.status == Rezerwacja.Status.ZAKONCZONA:
            return rezerwacja

        if rezerwacja.status != Rezerwacja.Status.ODEBRANA:
            raise ReservationNotReturnable("Zwrócić można tylko odebraną książkę.")

        now = timezone.now()

        rezerwacja.status = Rezerwacja.Status.ZAKONCZONA
        rezerwacja.zwrocona_at = now
        rezerwacja.save(
            update_fields=["status", "zwrocona_at"],
        )

        egzemplarz.dostepny = True
        egzemplarz.save(update_fields=["dostepny"])

        return rezerwacja
