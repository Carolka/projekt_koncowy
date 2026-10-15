from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from catalog.models import Egzemplarz, Ksiazka
from reservations.models import Rezerwacja
from reservations.services import expire_reservations


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
