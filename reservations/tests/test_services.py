from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils import timezone

from catalog.models import Egzemplarz, Ksiazka
from reservations.models import Rezerwacja
from reservations.services import (
    AlreadyReserved,
    NoAvailableCopy,
    expire_reservations,
    reserve_book,
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
