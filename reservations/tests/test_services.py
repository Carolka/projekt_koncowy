from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils import timezone

from catalog.models import Egzemplarz, Ksiazka
from reservations.models import Rezerwacja
from reservations.services import (
    AlreadyReserved,
    NoAvailableCopy,
    ReservationNotCancellable,
    expire_reservations,
    reserve_book,
    cancel_reservation,
)


class ExpireReservationsTests(TestCase):
    def setUp(self):
        self.now = timezone.now()

        self.user = get_user_model().objects.create_user(
            username="czytelnik",
            password="TestoweHaslo123!",
        )

        self.book = Ksiazka.objects.create(
            tytul="Ksiazka testowa",
        )

        self.copy = Egzemplarz.objects.create(
            ksiazka=self.book,
            numer_inwentarzowy="TEST-001",
            dostepny=False,
        )

        self.reservation = Rezerwacja.objects.create(
            uzytkownik=self.user,
            egzemplarz=self.copy,
            utworzona_at=self.now - timedelta(hours=48),
            termin_odbioru=self.now,
        )

    def test_expires_at_pickup_deadline(self):
        # wywolanie funkcji i zapisanie ile rekordow zmieniono
        count = expire_reservations(now=self.now)

        # pobranie świeżych danych
        self.reservation.refresh_from_db()
        self.copy.refresh_from_db()

        # sprawdzamy dla testowych danych czy wartosci sie zmienily
        # jedna wygaszona rezerwacja
        self.assertEqual(count, 1)

        # status czy status rezerwacji został ustawiony na WYGASLA
        self.assertEqual(
            self.reservation.status,
            Rezerwacja.Status.WYGASLA,
        )

        # dostepny ustawiony na True
        self.assertTrue(self.copy.dostepny)

    def test_expires_after_pickup_deadline(self):
        count = expire_reservations(
            now=self.now + timedelta(seconds=1),
        )

        self.reservation.refresh_from_db()
        self.copy.refresh_from_db()

        self.assertEqual(count, 1)
        self.assertEqual(
            self.reservation.status,
            Rezerwacja.Status.WYGASLA,
        )
        self.assertTrue(self.copy.dostepny)

    def test_does_not_expire_before_pickup_deadline(self):
        count = expire_reservations(
            now=self.now - timedelta(seconds=1),
        )

        self.reservation.refresh_from_db()
        self.copy.refresh_from_db()

        self.assertEqual(count, 0)
        self.assertEqual(
            self.reservation.status,
            Rezerwacja.Status.OCZEKUJACA,
        )

        self.assertFalse(self.copy.dostepny)

    # sprawdzamy czy wielokrotne uruchamianie funkcji expire_reservations coś psuje
    def test_repeated_expiration_does_not_change_anything(self):
        first_count = expire_reservations(now=self.now)
        second_count = expire_reservations(now=self.now)

        self.reservation.refresh_from_db()
        self.copy.refresh_from_db()

        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 0)
        self.assertEqual(
            self.reservation.status,
            Rezerwacja.Status.WYGASLA,
        )
        self.assertTrue(self.copy.dostepny)

    # sprawdzamy czy expire_reservations pomija wycofane z udostępnienia ksiazki
    def test_expiration_does_not_reactivate_withdrawn_copy(self):
        self.copy.aktywny = False
        self.copy.save(update_fields=["aktywny"])

        expire_reservations(now=self.now)
        self.copy.refresh_from_db()

        # dostepny do wypozyczenia
        self.assertTrue(self.copy.dostepny)
        # aktywny w zbiorze (nie wycofany)
        self.assertFalse(self.copy.aktywny)

    # czy odebrana przez czytelnika ksiazka pozostaje zajęta nawet po terminie zwrotu
    def test_expiration_ignores_collected_reservations(self):
        self.reservation.status = Rezerwacja.Status.ODEBRANA
        self.reservation.odebrana_at = self.reservation.utworzona_at + timedelta(
            hours=1
        )
        self.reservation.termin_zwrotu = self.reservation.odebrana_at + timedelta(
            days=14
        )

        self.reservation.save()

        count = expire_reservations(
            now=self.now + timedelta(days=20),
        )

        self.reservation.refresh_from_db()
        self.copy.refresh_from_db()

        self.assertEqual(count, 0)
        self.assertEqual(
            self.reservation.status,
            Rezerwacja.Status.ODEBRANA,
        )

        # nadal ma byc niedostepny - bo zostal odebrany ale nie zwrocony
        self.assertFalse(self.copy.dostepny)


class ReserveBookTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.user = get_user_model().objects.create_user(
            username="czytelnik", password="TestoweHaslo123!"
        )
        self.book = Ksiazka.objects.create(
            tytul="Ksiazka testowa",
        )
        self.egzemplarz = Egzemplarz.objects.create(
            ksiazka=self.book,
            numer_inwentarzowy="TEST-001",
        )

    def test_creates_reservation_for_48_hours(self):
        # reserve_book nie przyjmuje godziny - kontrolujemy jej wartosc z pomocą patch
        with patch("reservations.services.timezone.now", return_value=self.now):
            rezerwacja = reserve_book(self.user, self.book.pk)

        rezerwacja.refresh_from_db()
        self.egzemplarz.refresh_from_db()

        self.assertEqual(rezerwacja.uzytkownik, self.user)
        self.assertEqual(rezerwacja.egzemplarz, self.egzemplarz)
        self.assertEqual(rezerwacja.status, Rezerwacja.Status.OCZEKUJACA)
        self.assertEqual(rezerwacja.utworzona_at, self.now)
        self.assertEqual(
            rezerwacja.termin_odbioru,
            self.now + timedelta(hours=48),
        )
        self.assertFalse(self.egzemplarz.dostepny)

    def test_rejects_anonymous_user(self):
        with self.assertRaises(PermissionDenied):
            reserve_book(AnonymousUser(), self.book.pk)

        self.assertFalse(Rezerwacja.objects.exists())

    def test_rejects_inactive_user(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        with self.assertRaises(PermissionDenied):
            reserve_book(self.user, self.book.pk)

        # nie powstaje rezerwacja - mamy błąd - tylko exists
        self.assertFalse(Rezerwacja.objects.exists())

    def test_rejects_reservation_when_no_copy_is_available(self):
        self.egzemplarz.dostepny = False
        self.egzemplarz.save(update_fields=["dostepny"])

        with self.assertRaises(NoAvailableCopy):
            reserve_book(self.user, self.book.pk)

        self.assertFalse(Rezerwacja.objects.exists())

    def test_rejects_withdrawn_copy(self):
        self.egzemplarz.aktywny = False
        self.egzemplarz.save(update_fields=["aktywny"])

        with self.assertRaises(NoAvailableCopy):
            reserve_book(self.user, self.book.pk)
        self.assertFalse(Rezerwacja.objects.exists())

    def test_rejects_second_reservation_of_the_same_book(self):
        # użytkownik nie może rezerwować kolejnego egzemplarza tej samej książki

        reserve_book(self.user, self.book.pk)

        drugi_egzemplarz = Egzemplarz.objects.create(
            ksiazka=self.book,
            numer_inwentarzowy="TEST-002",
        )
        with self.assertRaises(AlreadyReserved):
            reserve_book(self.user, self.book.pk)

        drugi_egzemplarz.refresh_from_db()

        self.assertEqual(Rezerwacja.objects.count(), 1)
        self.assertTrue(drugi_egzemplarz.dostepny)

    def test_reuses_copy_after_pickup_deadline(self):
        self.egzemplarz.dostepny = False
        self.egzemplarz.save(update_fields=["dostepny"])

        stara_rezerwacja = Rezerwacja.objects.create(
            uzytkownik=self.user,
            egzemplarz=self.egzemplarz,
            utworzona_at=self.now - timedelta(hours=48),
            termin_odbioru=self.now,
        )

        with patch("reservations.services.timezone.now", return_value=self.now):
            nowa_rezerwacja = reserve_book(self.user, self.book.pk)

        stara_rezerwacja.refresh_from_db()
        self.egzemplarz.refresh_from_db()

        self.assertEqual(
            stara_rezerwacja.status,
            Rezerwacja.Status.WYGASLA,
        )
        self.assertNotEqual(nowa_rezerwacja.pk, stara_rezerwacja.pk)
        self.assertEqual(nowa_rezerwacja.egzemplarz, self.egzemplarz)
        self.assertFalse(self.egzemplarz.dostepny)


class CancelReservationTests(TestCase):
    def setUp(self):
        self.now = timezone.now()

        self.user = get_user_model().objects.create_user(
            username="czytelnik",
            password="TestoweHaslo123!",
        )

        self.book = Ksiazka.objects.create(tytul="Ksiazka testowa")

        # dwa egzemplarze z nadanymi z góry id
        self.egzemplarz = Egzemplarz.objects.create(
            pk=200,
            ksiazka=self.book,
            numer_inwentarzowy="TEST-200",
            dostepny=False,
        )

        self.inny_egzemplarz = Egzemplarz.objects.create(
            pk=100,
            ksiazka=self.book,
            numer_inwentarzowy="TEST-100",
            dostepny=False,
        )

        self.reservation = Rezerwacja.objects.create(
            pk=100,
            uzytkownik=self.user,
            egzemplarz=self.egzemplarz,
            status=Rezerwacja.Status.OCZEKUJACA,
            utworzona_at=self.now,
            termin_odbioru=self.now + timedelta(hours=48),
        )

    def test_cancellation_releases_only_the_reserved_copy(self):
        with patch("reservations.services.timezone.now", return_value=self.now):
            wynik = cancel_reservation(
                reservation_id=self.reservation.pk,
                user=self.user,
            )
        self.reservation.refresh_from_db()
        self.egzemplarz.refresh_from_db()
        self.inny_egzemplarz.refresh_from_db()

        self.assertEqual(wynik.pk, self.reservation.pk)
        self.assertEqual(
            self.reservation.status,
            Rezerwacja.Status.ANULOWANA,
        )
        self.assertEqual(self.reservation.anulowana_at, self.now)
        self.assertTrue(self.egzemplarz.dostepny)
        self.assertFalse(self.inny_egzemplarz.dostepny)

    def test_rejects_anonymous_or_inactive_user(self):

        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        przypadki = [
            ("niezalogowany", AnonymousUser()),
            ("nieaktywny", self.user),
        ]
        for nazwa, user in przypadki:
            with self.subTest(przypadek=nazwa):
                with self.assertRaises(PermissionDenied):
                    cancel_reservation(
                        reservation_id=self.reservation.pk,
                        user=user,
                    )
                self.reservation.refresh_from_db()
                self.egzemplarz.refresh_from_db()

                # sprawdzamy czy rezerwacja jest nadal nie zmieniona
                self.assertEqual(
                    self.reservation.status,
                    Rezerwacja.Status.OCZEKUJACA,
                )
                self.assertFalse(self.egzemplarz.dostepny)

    def test_rejects_cancellation_by_another_user(self):
        inny_user = get_user_model().objects.create_user(
            username="inny_czytelnik",
            password="TestoweHaslo123!",
        )
        with self.assertRaises(PermissionDenied):
            cancel_reservation(self.reservation.pk, inny_user)

        self.reservation.refresh_from_db()
        self.egzemplarz.refresh_from_db()
        self.assertEqual(
            self.reservation.status,
            Rezerwacja.Status.OCZEKUJACA,
        )
        self.assertFalse(self.egzemplarz.dostepny)

    def test_user_with_permission_can_cancel_another_users_reservation(self):
        bibliotekarka = get_user_model().objects.create_user(
            username="bibliotekarka",
            password="TestoweHaslo123!",
            is_staff=True,
        )
        uprawnienie = Permission.objects.get(
            content_type__app_label="reservations",
            content_type__model="rezerwacja",
            codename="cancel_reservation",
        )
        bibliotekarka.user_permissions.add(uprawnienie)

        with patch("reservations.services.timezone.now", return_value=self.now):
            cancel_reservation(self.reservation.pk, bibliotekarka)

        self.reservation.refresh_from_db()
        self.egzemplarz.refresh_from_db()

        self.assertEqual(
            self.reservation.status,
            Rezerwacja.Status.ANULOWANA,
        )

        self.assertEqual(self.reservation.anulowana_at, self.now)
        self.assertTrue(self.egzemplarz.dostepny)

    def test_cancellation_at_or_after_deadline_expires_reservation(self):
        # dla dwoch warunkow [at, after]
        for opoznienie in [timedelta(0), timedelta(hours=1)]:
            with self.subTest(opoznienie=opoznienie):
                self.reservation.status = Rezerwacja.Status.OCZEKUJACA
                self.reservation.anulowana_at = None
                self.reservation.save(
                    update_fields=["status", "anulowana_at"],
                )

                self.egzemplarz.dostepny = False
                self.egzemplarz.save(update_fields=["dostepny"])

                czas = self.reservation.termin_odbioru + opoznienie

                with patch(
                    "reservations.services.timezone.now",
                    return_value=czas,
                ):
                    wynik = cancel_reservation(
                        self.reservation.pk,
                        self.user,
                    )

                self.reservation.refresh_from_db()
                self.egzemplarz.refresh_from_db()
                self.assertEqual(
                    wynik.status,
                    Rezerwacja.Status.WYGASLA,
                )
                self.assertEqual(
                    self.reservation.status,
                    Rezerwacja.Status.WYGASLA,
                )
                self.assertIsNone(self.reservation.anulowana_at)
                self.assertTrue(self.egzemplarz.dostepny)

    def test_rejects_collected_or_completed_reservations(self):
        for status in [
            Rezerwacja.Status.ODEBRANA,
            Rezerwacja.Status.ZAKONCZONA,
        ]:
            with self.subTest(status=status):
                # ustawiamy True/False - wynik porównania
                czy_zakonczona = status == Rezerwacja.Status.ZAKONCZONA

                self.reservation.status = status
                self.reservation.odebrana_at = self.now
                self.reservation.termin_zwrotu = self.now + timedelta(days=14)
                self.reservation.zwrocona_at = (
                    self.now + timedelta(days=1) if czy_zakonczona else None
                )
                self.reservation.save()

                self.egzemplarz.dostepny = czy_zakonczona
                self.egzemplarz.save(update_fields=["dostepny"])

                with self.assertRaises(ReservationNotCancellable):
                    cancel_reservation(self.reservation.pk, self.user)

                self.reservation.refresh_from_db()
                self.egzemplarz.refresh_from_db()

                self.assertEqual(self.reservation.status, status)
                self.assertIsNone(self.reservation.anulowana_at)
                self.assertEqual(self.egzemplarz.dostepny, czy_zakonczona)

    def test_repeated_cancellation_does_not_release_new_reservation(self):
        with patch("reservations.services.timezone.now", return_value=self.now):
            cancel_reservation(self.reservation.pk, self.user)

        inny_user = get_user_model().objects.create_user(
            username="nowy_czytelnik",
            password="TestoweHaslo123!",
        )

        with patch("reservations.services.timezone.now", return_value=self.now):
            nowa_rezerwacja = reserve_book(inny_user, self.book.pk)

        self.assertEqual(
            nowa_rezerwacja.egzemplarz_id,
            self.reservation.egzemplarz_id,
        )

        with patch(
            "reservations.services.timezone.now",
            return_value=self.now + timedelta(minutes=5),
        ):
            cancel_reservation(self.reservation.pk, self.user)

        self.reservation.refresh_from_db()
        nowa_rezerwacja.refresh_from_db()
        self.egzemplarz.refresh_from_db()

        self.assertEqual(
            self.reservation.status,
            Rezerwacja.Status.ANULOWANA,
        )
        self.assertEqual(self.reservation.anulowana_at, self.now)

        self.assertEqual(
            nowa_rezerwacja.status,
            Rezerwacja.Status.OCZEKUJACA,
        )
        self.assertFalse(self.egzemplarz.dostepny)

    def test_cancellation_does_not_reactivate_withdrawn_copy(self):
        self.egzemplarz.aktywny = False
        self.egzemplarz.save(update_fields=["aktywny"])

        with patch("reservations.services.timezone.now", return_value=self.now):
            cancel_reservation(self.reservation.pk, self.user)

        self.reservation.refresh_from_db()
        self.egzemplarz.refresh_from_db()

        self.assertEqual(
            self.reservation.status,
            Rezerwacja.Status.ANULOWANA,
        )
        self.assertTrue(self.egzemplarz.dostepny)
        self.assertFalse(self.egzemplarz.aktywny)
