from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from catalog.models import Egzemplarz, Ksiazka
from reservations.models import Rezerwacja


class ReserveBookViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="czytelnik_rezerwacja",
            password="MocneHaslo#427",
        )
        self.ksiazka = Ksiazka.objects.create(tytul="Diuna")
        self.egzemplarz = Egzemplarz.objects.create(
            ksiazka=self.ksiazka,
            numer_inwentarzowy="RESERVE-001",
            aktywny=True,
            dostepny=True,
        )
        self.teraz = timezone.now()
        self.adres_rezerwacji = reverse(
            "reservations:reserve_book",
            args=[self.ksiazka.pk],
        )

    def test_logged_in_reader_can_reserve_available_copy(self):
        self.client.force_login(self.user)

        with patch("reservations.services.timezone.now", return_value=self.teraz):
            response = self.client.post(self.adres_rezerwacji)

        self.assertRedirects(
            response,
            reverse("catalog:book_detail", args=[self.ksiazka.pk]),
            fetch_redirect_response=False,
        )

        rezerwacja = Rezerwacja.objects.get()

        self.assertEqual(rezerwacja.uzytkownik, self.user)
        self.assertEqual(rezerwacja.egzemplarz, self.egzemplarz)
        self.assertEqual(rezerwacja.status, Rezerwacja.Status.OCZEKUJACA)
        self.assertEqual(
            rezerwacja.termin_odbioru,
            self.teraz + timedelta(hours=48),
        )

        self.egzemplarz.refresh_from_db()
        self.assertFalse(self.egzemplarz.dostepny)

    def test_anonymous_reader_is_redirected_to_login(self):
        response = self.client.post(self.adres_rezerwacji)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("login")))
        self.assertEqual(Rezerwacja.objects.count(), 0)

    def test_reader_cannot_reserve_same_book_twice(self):
        self.client.force_login(self.user)

        with patch("reservations.services.timezone.now", return_value=self.teraz):
            self.client.post(self.adres_rezerwacji)

        drugi_egzemplarz = Egzemplarz.objects.create(
            ksiazka=self.ksiazka,
            numer_inwentarzowy="RESERVE-002",
            aktywny=True,
            dostepny=True,
        )

        with patch("reservations.services.timezone.now", return_value=self.teraz):
            response = self.client.post(self.adres_rezerwacji)

            self.assertRedirects(
                response,
                reverse("catalog:book_detail", args=[self.ksiazka.pk]),
                fetch_redirect_response=False,
            )
            self.assertEqual(Rezerwacja.objects.count(), 1)

            drugi_egzemplarz.refresh_from_db()
            self.assertTrue(drugi_egzemplarz.dostepny)

    def test_get_request_does_not_create_reservation(self):
        self.client.force_login(self.user)

        response = self.client.get(self.adres_rezerwacji)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(Rezerwacja.objects.count(), 0)
