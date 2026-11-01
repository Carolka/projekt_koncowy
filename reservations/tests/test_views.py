from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
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


class CancelReservationViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="czytelnik_anulowanie",
            password="MocneHaslo#427",
        )
        self.ksiazka = Ksiazka.objects.create(tytul="Diuna")
        self.teraz = timezone.now()

        self.egzemplarz = Egzemplarz.objects.create(
            ksiazka=self.ksiazka,
            numer_inwentarzowy="CANCEL-001",
            aktywny=True,
            dostepny=False,
        )

        self.rezerwacja = Rezerwacja.objects.create(
            uzytkownik=self.user,
            egzemplarz=self.egzemplarz,
            status=Rezerwacja.Status.OCZEKUJACA,
            utworzona_at=self.teraz,
            termin_odbioru=self.teraz + timedelta(hours=48),
        )
        self.adres_anulowania = reverse(
            "reservations:cancel_reservation",
            args=[self.rezerwacja.pk],
        )

    def test_reader_can_cancel_own_pending_reservation(self):
        self.client.force_login(self.user)

        with patch("reservations.services.timezone.now", return_value=self.teraz):
            response = self.client.post(self.adres_anulowania)

        self.assertRedirects(
            response,
            reverse("catalog:book_detail", args=[self.ksiazka.pk]),
            fetch_redirect_response=False,
        )

        self.rezerwacja.refresh_from_db()
        self.egzemplarz.refresh_from_db()

        self.assertEqual(
            self.rezerwacja.status,
            Rezerwacja.Status.ANULOWANA,
        )

        self.assertEqual(self.rezerwacja.anulowana_at, self.teraz)
        self.assertTrue(self.egzemplarz.dostepny)
        self.assertEqual(Rezerwacja.objects.count(), 1)

    def test_anonymous_reader_is_redirected_to_login(self):
        response = self.client.post(self.adres_anulowania)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("login")))

        self.rezerwacja.refresh_from_db()
        self.egzemplarz.refresh_from_db()

        self.assertEqual(
            self.rezerwacja.status,
            Rezerwacja.Status.OCZEKUJACA,
        )

        self.assertFalse(self.egzemplarz.dostepny)

    def test_reader_cannot_cancel_another_users_reservation(self):
        other_user = get_user_model().objects.create_user(
            username="inny_czytelnik",
            password="MocneHaslo#427",
        )
        self.client.force_login(other_user)

        response = self.client.post(self.adres_anulowania)
        self.assertEqual(response.status_code, 403)
        self.rezerwacja.refresh_from_db()
        self.egzemplarz.refresh_from_db()

        self.assertEqual(
            self.rezerwacja.status,
            Rezerwacja.Status.OCZEKUJACA,
        )
        self.assertFalse(self.egzemplarz.dostepny)

    def test_get_request_does_not_cancel_reservation(self):
        self.client.force_login(self.user)
        response = self.client.get(self.adres_anulowania)
        self.assertEqual(response.status_code, 405)
        self.rezerwacja.refresh_from_db()
        self.assertEqual(
            self.rezerwacja.status,
            Rezerwacja.Status.OCZEKUJACA,
        )


class MyReservationsViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="czytelnik_panelu",
            password="MocneHaslo#427",
        )
        self.other_user = get_user_model().objects.create_user(
            username="inny_czytelnik_panelu",
            password="MocneHaslo#427",
        )
        self.ksiazka = Ksiazka.objects.create(tytul="Diuna")
        self.teraz = timezone.now()
        self.adres_panelu = reverse("reservations:my_reservations")

    def _utworz_rezerwacje(
        self,
        *,
        uzytkownik,
        numer,
        status,
        utworzona_at,
        termin_odbioru,
        odebrana_at=None,
        termin_zwrotu=None,
        anulowana_at=None,
        zwrocona_at=None,
    ):
        egzemplarz = Egzemplarz.objects.create(
            ksiazka=self.ksiazka,
            numer_inwentarzowy=numer,
            aktywny=True,
            dostepny=False,
        )
        return Rezerwacja.objects.create(
            uzytkownik=uzytkownik,
            egzemplarz=egzemplarz,
            status=status,
            utworzona_at=utworzona_at,
            termin_odbioru=termin_odbioru,
            odebrana_at=odebrana_at,
            termin_zwrotu=termin_zwrotu,
            anulowana_at=anulowana_at,
            zwrocona_at=zwrocona_at,
        )

    def test_anonymous_reader_is_redirected_to_login(self):
        response = self.client.get(self.adres_panelu)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("login")))

    def test_reader_sees_own_reservations_in_current_and_history_sections(self):
        oczekujaca = self._utworz_rezerwacje(
            uzytkownik=self.user,
            numer="PANEL-001",
            status=Rezerwacja.Status.OCZEKUJACA,
            utworzona_at=self.teraz - timedelta(hours=1),
            termin_odbioru=self.teraz + timedelta(hours=48),
        )
        odebrana = self._utworz_rezerwacje(
            uzytkownik=self.user,
            numer="PANEL-002",
            status=Rezerwacja.Status.ODEBRANA,
            utworzona_at=self.teraz - timedelta(days=2),
            termin_odbioru=self.teraz + timedelta(days=1),
            odebrana_at=self.teraz - timedelta(hours=1),
            termin_zwrotu=self.teraz + timedelta(days=13),
        )
        przeterminowana_oczekujaca = self._utworz_rezerwacje(
            uzytkownik=self.user,
            numer="PANEL-003",
            status=Rezerwacja.Status.OCZEKUJACA,
            utworzona_at=self.teraz - timedelta(days=2),
            termin_odbioru=self.teraz - timedelta(hours=1),
        )
        anulowana = self._utworz_rezerwacje(
            uzytkownik=self.user,
            numer="PANEL-004",
            status=Rezerwacja.Status.ANULOWANA,
            utworzona_at=self.teraz - timedelta(days=3),
            termin_odbioru=self.teraz - timedelta(days=2),
            anulowana_at=self.teraz - timedelta(days=2, hours=12),
        )
        wygasla = self._utworz_rezerwacje(
            uzytkownik=self.user,
            numer="PANEL-005",
            status=Rezerwacja.Status.WYGASLA,
            utworzona_at=self.teraz - timedelta(days=3),
            termin_odbioru=self.teraz - timedelta(days=2),
        )
        zakonczona = self._utworz_rezerwacje(
            uzytkownik=self.user,
            numer="PANEL-006",
            status=Rezerwacja.Status.ZAKONCZONA,
            utworzona_at=self.teraz - timedelta(days=20),
            termin_odbioru=self.teraz - timedelta(days=19),
            odebrana_at=self.teraz - timedelta(days=18),
            termin_zwrotu=self.teraz - timedelta(days=4),
            zwrocona_at=self.teraz - timedelta(days=3),
        )
        rezerwacja_innego_uzytkownika = self._utworz_rezerwacje(
            uzytkownik=self.other_user,
            numer="PANEL-007",
            status=Rezerwacja.Status.OCZEKUJACA,
            utworzona_at=self.teraz - timedelta(hours=1),
            termin_odbioru=self.teraz + timedelta(days=2),
        )

        self.client.force_login(self.user)
        response = self.client.get(self.adres_panelu)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "reservations/my_reservations.html")

        biezace_ids = set(
            response.context["biezace_rezerwacje"].values_list("pk", flat=True)
        )

        historyczne_ids = set(
            response.context["historyczne_rezerwacje"].values_list("pk", flat=True)
        )

        self.assertSetEqual(
            biezace_ids,
            {oczekujaca.pk, odebrana.pk},
        )

        self.assertSetEqual(
            historyczne_ids,
            {
                przeterminowana_oczekujaca.pk,
                anulowana.pk,
                wygasla.pk,
                zakonczona.pk,
            },
        )

        self.assertNotIn(
            rezerwacja_innego_uzytkownika.pk,
            biezace_ids | historyczne_ids,
        )

        self.assertContains(response, "Wygasła")

    def test_post_request_to_panel_returns_method_not_allowed(self):
        self.client.force_login(self.user)
        response = self.client.post(self.adres_panelu)
        self.assertEqual(response.status_code, 405)


class LibrarianReservationsViewTests(TestCase):
    def setUp(self):
        teraz = timezone.now()

        self.czytelnik = get_user_model().objects.create_user(
            username="czytelnik_panelu",
            password="TestoweHaslo123!",
        )
        self.bibliotekarka = get_user_model().objects.create_user(
            username="bibliotekarka_panelu",
            password="TestoweHaslo123!",
        )

        uprawnienia = Permission.objects.filter(
            content_type__app_label="reservations",
            codename__in=[
                "view_rezerwacja",
                "collect_reservation",
                "return_reservation",
            ],
        )
        self.bibliotekarka.user_permissions.add(*uprawnienia)

        ksiazka = Ksiazka.objects.create(tytul="Diuna")
        egzemplarz = Egzemplarz.objects.create(
            ksiazka=ksiazka,
            numer_inwentarzowy="LIBRARIAN-001",
            dostepny=False,
        )
        self.rezerwacja = Rezerwacja.objects.create(
            uzytkownik=self.czytelnik,
            egzemplarz=egzemplarz,
            status=Rezerwacja.Status.OCZEKUJACA,
            utworzona_at=teraz,
            termin_odbioru=teraz + timedelta(hours=24),
        )

        self.adres = reverse("reservations:librarian_reservations")

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.adres)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("login")))

    def test_user_without_permission_gets_forbidden(self):
        self.client.force_login(self.czytelnik)
        response = self.client.get(self.adres)
        self.assertEqual(response.status_code, 403)

    def test_view_only_librarian_does_not_see_action_buttons(self):
        podgladacz = get_user_model().objects.create_user(
            username="podgladacz_rezerwacji",
            password="TestoweHaslo123!",
        )
        uprawnienie_podgladu = Permission.objects.get(
            content_type__app_label="reservations",
            codename="view_rezerwacja",
        )
        podgladacz.user_permissions.add(uprawnienie_podgladu)
        self.client.force_login(podgladacz)

        response = self.client.get(self.adres)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Potwierdź odbiór")
        self.assertNotContains(response, "Potwierdź zwrot")

        odebrana_at = timezone.now() - timedelta(hours=1)
        self.rezerwacja.status = Rezerwacja.Status.ODEBRANA
        self.rezerwacja.odebrana_at = odebrana_at
        self.rezerwacja.termin_zwrotu = odebrana_at + timedelta(days=14)
        self.rezerwacja.save(
            update_fields=["status", "odebrana_at", "termin_zwrotu"],
        )

        response = self.client.get(self.adres)

        self.assertNotContains(response, "Potwierdź odbiór")
        self.assertNotContains(response, "Potwierdź zwrot")

    def test_librarian_can_see_reservations(self):
        self.client.force_login(self.bibliotekarka)
        response = self.client.get(self.adres)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "reservations/librarian_reservations.html",
        )
        self.assertContains(response, "Diuna")
        self.assertContains(response, "LIBRARIAN-001")
        self.assertContains(response, "Potwierdź odbiór")
        self.assertContains(
            response,
            reverse(
                "reservations:collect_reservation",
                args=[self.rezerwacja.pk],
            ),
        )
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_librarian_can_search_and_filter_reservations(self):
        self.client.force_login(self.bibliotekarka)

        response = self.client.get(
            self.adres,
            {
                "q": "LIBRARIAN-001",
                "status": Rezerwacja.Status.OCZEKUJACA,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertContains(response, "LIBRARIAN-001")

    def test_return_button_is_shown_only_for_collected_reservation(self):
        self.client.force_login(self.bibliotekarka)

        response = self.client.get(self.adres)
        self.assertNotContains(response, "Potwierdź zwrot")

        odebrana_at = timezone.now() - timedelta(hours=1)
        self.rezerwacja.status = Rezerwacja.Status.ODEBRANA
        self.rezerwacja.odebrana_at = odebrana_at
        self.rezerwacja.termin_zwrotu = odebrana_at + timedelta(days=14)
        self.rezerwacja.save(
            update_fields=["status", "odebrana_at", "termin_zwrotu"],
        )

        response = self.client.get(self.adres)

        self.assertContains(response, "Potwierdź zwrot")
        self.assertContains(
            response,
            reverse(
                "reservations:return_reservation",
                args=[self.rezerwacja.pk],
            ),
        )


class CollectReservationViewTests(TestCase):
    def setUp(self):
        self.teraz = timezone.now()

        self.czytelnik = get_user_model().objects.create_user(
            username="czytelnik_odbioru",
            password="TestoweHaslo123!",
        )
        self.bibliotekarka = get_user_model().objects.create_user(
            username="bibliotekarka_odbioru",
            password="TestoweHaslo123!",
        )
        uprawnienie = Permission.objects.get(
            content_type__app_label="reservations",
            codename="collect_reservation",
        )
        self.bibliotekarka.user_permissions.add(uprawnienie)

        ksiazka = Ksiazka.objects.create(tytul="Diuna")
        self.egzemplarz = Egzemplarz.objects.create(
            ksiazka=ksiazka,
            numer_inwentarzowy="COLLECT-VIEW-001",
            dostepny=False,
        )
        self.rezerwacja = Rezerwacja.objects.create(
            uzytkownik=self.czytelnik,
            egzemplarz=self.egzemplarz,
            status=Rezerwacja.Status.OCZEKUJACA,
            utworzona_at=self.teraz,
            termin_odbioru=self.teraz + timedelta(hours=48),
        )
        self.adres = reverse(
            "reservations:collect_reservation",
            args=[self.rezerwacja.pk],
        )

    def test_librarian_can_confirm_pickup(self):
        self.client.force_login(self.bibliotekarka)

        with patch(
            "reservations.services.timezone.now",
            return_value=self.teraz,
        ):
            response = self.client.post(self.adres)

        self.assertRedirects(
            response,
            reverse("reservations:librarian_reservations"),
            fetch_redirect_response=False,
        )

        self.rezerwacja.refresh_from_db()
        self.assertEqual(self.rezerwacja.status, Rezerwacja.Status.ODEBRANA)
        self.assertEqual(self.rezerwacja.odebrana_at, self.teraz)
        self.assertEqual(
            self.rezerwacja.termin_zwrotu,
            self.teraz + timedelta(days=14),
        )

    def test_reader_without_pickup_permission_gets_forbidden(self):
        self.client.force_login(self.czytelnik)
        response = self.client.post(self.adres)
        self.assertEqual(response.status_code, 403)

    def test_expired_reservation_cannot_be_collected(self):
        self.client.force_login(self.bibliotekarka)
        self.rezerwacja.utworzona_at = self.teraz - timedelta(hours=50)
        self.rezerwacja.termin_odbioru = self.teraz - timedelta(hours=2)
        self.rezerwacja.save(
            update_fields=["utworzona_at", "termin_odbioru"],
        )

        with patch(
            "reservations.services.timezone.now",
            return_value=self.teraz,
        ):
            response = self.client.post(self.adres)

        self.assertRedirects(
            response,
            reverse("reservations:librarian_reservations"),
            fetch_redirect_response=False,
        )

        self.rezerwacja.refresh_from_db()
        self.egzemplarz.refresh_from_db()
        self.assertEqual(self.rezerwacja.status, Rezerwacja.Status.WYGASLA)
        self.assertTrue(self.egzemplarz.dostepny)


class ReturnReservationViewTests(TestCase):
    def setUp(self):
        self.teraz = timezone.now()

        self.czytelnik = get_user_model().objects.create_user(
            username="czytelnik_zwrotu",
            password="TestoweHaslo123!",
        )
        self.bibliotekarka = get_user_model().objects.create_user(
            username="bibliotekarka_zwrotu",
            password="TestoweHaslo123!",
        )
        uprawnienie = Permission.objects.get(
            content_type__app_label="reservations",
            codename="return_reservation",
        )
        self.bibliotekarka.user_permissions.add(uprawnienie)

        ksiazka = Ksiazka.objects.create(tytul="Diuna")
        self.egzemplarz = Egzemplarz.objects.create(
            ksiazka=ksiazka,
            numer_inwentarzowy="RETURN-VIEW-001",
            dostepny=False,
        )
        self.rezerwacja = Rezerwacja.objects.create(
            uzytkownik=self.czytelnik,
            egzemplarz=self.egzemplarz,
            status=Rezerwacja.Status.ODEBRANA,
            utworzona_at=self.teraz - timedelta(days=2),
            termin_odbioru=self.teraz - timedelta(days=1),
            odebrana_at=self.teraz - timedelta(days=1),
            termin_zwrotu=self.teraz + timedelta(days=13),
        )

        self.adres = reverse(
            "reservations:return_reservation",
            args=[self.rezerwacja.pk],
        )

    def test_librarian_can_confirm_return(self):
        self.client.force_login(self.bibliotekarka)

        with patch(
            "reservations.services.timezone.now",
            return_value=self.teraz,
        ):
            response = self.client.post(self.adres)

        self.assertRedirects(
            response,
            reverse("reservations:librarian_reservations"),
            fetch_redirect_response=False,
        )
        self.rezerwacja.refresh_from_db()
        self.egzemplarz.refresh_from_db()

        self.assertEqual(
            self.rezerwacja.status,
            Rezerwacja.Status.ZAKONCZONA,
        )
        self.assertEqual(self.rezerwacja.zwrocona_at, self.teraz)
        self.assertTrue(self.egzemplarz.dostepny)

    def test_reader_without_return_permission_gets_forbidden(self):
        self.client.force_login(self.czytelnik)
        response = self.client.post(self.adres)
        self.assertEqual(response.status_code, 403)

    def test_pending_reservation_cannot_be_returned(self):
        self.client.force_login(self.bibliotekarka)
        self.rezerwacja.status = Rezerwacja.Status.OCZEKUJACA
        self.rezerwacja.save(update_fields=["status"])

        response = self.client.post(self.adres)

        self.assertRedirects(
            response,
            reverse("reservations:librarian_reservations"),
            fetch_redirect_response=False,
        )
        self.rezerwacja.refresh_from_db()
        self.egzemplarz.refresh_from_db()

        self.assertEqual(
            self.rezerwacja.status,
            Rezerwacja.Status.OCZEKUJACA,
        )
        self.assertFalse(self.egzemplarz.dostepny)
