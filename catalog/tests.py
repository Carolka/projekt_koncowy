from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.utils import timezone
from catalog.forms import BookSearchForm
from catalog.models import Gatunek, Autor, Egzemplarz, Ksiazka
from reservations.models import Rezerwacja


# Create your tests here.
class BookSearchFormTests(TestCase):
    def setUp(self):
        self.gatunek = Gatunek.objects.create(nazwa="Fantasy")

    def test_empty_form_is_valid(self):
        form = BookSearchForm(data={})

        self.assertTrue(form.is_valid(), form.errors)

    def test_form_accepts_search_text_genre_and_availability(self):
        form = BookSearchForm(
            data={
                "q": "Diuna",
                "gatunek": str(self.gatunek.pk),
                "dostepne": "tak",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["q"], "Diuna")
        self.assertEqual(form.cleaned_data["gatunek"], self.gatunek)
        self.assertEqual(form.cleaned_data["dostepne"], "tak")

    def test_form_rejects_invalid_genre_and_availability(self):
        form = BookSearchForm(
            data={
                "gatunek": "nieistniejący",
                "dostepne": "nie",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("gatunek", form.errors)
        self.assertIn("dostepne", form.errors)


class BookListViewTests(TestCase):
    def setUp(self):
        self.autor = Autor.objects.create(
            imie="Frank",
            nazwisko="Herbert",
        )
        self.gatunek = Gatunek.objects.create(nazwa="Science fiction")
        self.ksiazka = Ksiazka.objects.create(
            tytul="Diuna",
            isbn="9780441013593",
        )
        self.ksiazka.autorzy.add(self.autor)
        self.ksiazka.gatunki.add(self.gatunek)

        Egzemplarz.objects.create(
            ksiazka=self.ksiazka,
            numer_inwentarzowy="TEST-001",
            aktywny=True,
            dostepny=True,
        )

    def test_get_displays_books(self):
        response = self.client.get(reverse("catalog:book_list"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "catalog/book_list.html")
        self.assertContains(response, "Diuna")
        self.assertContains(response, self.ksiazka.isbn)

    def test_search_finds_book_by_title_author_or_isbn(self):
        frazy = ["Diuna", "Frank", "Herbert", self.ksiazka.isbn]

        for fraza in frazy:
            with self.subTest(fraza=fraza):
                response = self.client.get(
                    reverse("catalog:book_list"),
                    {"q": fraza},
                )

                self.assertEqual(
                    list(response.context["page_obj"].object_list),
                    [self.ksiazka],
                )

    def test_search_only_uses_selected_field(self):
        druga_ksiazka = Ksiazka.objects.create(tytul="Herbert")

        for pole, oczekiwana in [("tytul", druga_ksiazka), ("autor", self.ksiazka)]:
            with self.subTest(pole=pole):
                response = self.client.get(
                    reverse("catalog:book_list"),
                    {"q": "Herbert", "pole": pole},
                )
                self.assertEqual(list(response.context["page_obj"]), [oczekiwana])

    def test_genre_filter_returns_books_of_selected_genre(self):
        response = self.client.get(
            reverse("catalog:book_list"),
            {"gatunek": str(self.gatunek.pk)},
        )
        self.assertEqual(
            list(response.context["page_obj"].object_list),
            [self.ksiazka],
        )

    def test_available_filter_excludes_unavailable_and_withdrawn_copies(self):
        niedostepna = Ksiazka.objects.create(
            tytul="Niedostępna",
            isbn="9781234567890",
        )
        Egzemplarz.objects.create(
            ksiazka=niedostepna,
            numer_inwentarzowy="TEST-002",
            aktywny=True,
            dostepny=False,
        )
        wycofana = Ksiazka.objects.create(
            tytul="Wycofana",
            isbn="9781234567891",
        )
        Egzemplarz.objects.create(
            ksiazka=wycofana,
            numer_inwentarzowy="TEST-003",
            aktywny=False,
            dostepny=True,
        )
        response = self.client.get(
            reverse("catalog:book_list"),
            {"dostepne": "tak"},
        )
        self.assertEqual(
            list(response.context["page_obj"].object_list),
            [self.ksiazka],
        )

    def test_list_displays_twenty_books_per_page(self):
        for numer in range(20):
            Ksiazka.objects.create(tytul=f"Dodatkowa książka{numer}")

        response = self.client.get(
            reverse("catalog:book_list"),
            {"page": "2"},
        )

        page_obj = response.context["page_obj"]

        self.assertEqual(page_obj.paginator.per_page, 20)
        self.assertEqual(len(page_obj.object_list), 1)
        self.assertTrue(page_obj.has_previous())

    def test_available_filter_expires_overdue_reservation_before_filtering(self):
        teraz = timezone.now()
        ksiazka = Ksiazka.objects.create(tytul="Przetrzymana rezerwacja")
        egzemplarz = Egzemplarz.objects.create(
            ksiazka=ksiazka,
            numer_inwentarzowy="LIST-OVERDUE-001",
            aktywny=True,
            dostepny=False,
        )
        uzytkownik = get_user_model().objects.create_user(
            username="czytelnik_testowy",
            password="TestoweHaslo123!",
        )
        rezerwacja = Rezerwacja.objects.create(
            uzytkownik=uzytkownik,
            egzemplarz=egzemplarz,
            status=Rezerwacja.Status.OCZEKUJACA,
            utworzona_at=teraz - timedelta(hours=50),
            termin_odbioru=teraz - timedelta(hours=2),
        )

        with patch("reservations.services.timezone.now", return_value=teraz):
            response = self.client.get(
                reverse("catalog:book_list"),
                {"dostepne": "tak"},
            )
        rezerwacja.refresh_from_db()
        egzemplarz.refresh_from_db()
        pokazane_id = [
            ksiazka.pk for ksiazka in response.context["page_obj"].object_list
        ]

        self.assertEqual(rezerwacja.status, Rezerwacja.Status.WYGASLA)
        self.assertTrue(egzemplarz.dostepny)
        self.assertIn(ksiazka.pk, pokazane_id)


class BookDetailViewTests(TestCase):
    def setUp(self):
        self.autor = Autor.objects.create(
            imie="Frank",
            nazwisko="Herbert",
        )
        self.gatunek = Gatunek.objects.create(nazwa="Science fiction")
        self.ksiazka = Ksiazka.objects.create(
            tytul="Diuna",
            opis="Opis książki.",
            isbn="9780441013593",
            rok_wydania=1965,
        )
        self.ksiazka.autorzy.add(self.autor)
        self.ksiazka.gatunki.add(self.gatunek)

        Egzemplarz.objects.create(
            ksiazka=self.ksiazka,
            numer_inwentarzowy="DETAIL-001",
            aktywny=True,
            dostepny=True,
        )

        Egzemplarz.objects.create(
            ksiazka=self.ksiazka,
            numer_inwentarzowy="DETAIL-002",
            aktywny=True,
            dostepny=False,
        )
        Egzemplarz.objects.create(
            ksiazka=self.ksiazka,
            numer_inwentarzowy="DETAIL-003",
            aktywny=False,
            dostepny=True,
        )

    def test_detail_page_displays_book_and_availability(self):
        response = self.client.get(
            reverse("catalog:book_detail", args=[self.ksiazka.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "catalog/book_detail.html")
        self.assertContains(response, "Diuna")
        self.assertContains(response, "Frank Herbert")
        self.assertContains(response, "Science fiction")
        self.assertContains(response, self.ksiazka.isbn)
        self.assertEqual(
            response.context["liczba_aktywnych_egzemplarzy"],
            2,
        )
        self.assertEqual(
            response.context["liczba_dostepnych_egzemplarzy"],
            1,
        )

    def test_detail_page_returns_404_for_unknown_book(self):
        response = self.client.get(reverse("catalog:book_detail", args=[999999]))
        self.assertEqual(response.status_code, 404)

    def test_librarian_has_staff_navigation_and_cannot_reserve_from_book_detail(self):
        bibliotekarka = get_user_model().objects.create_user(
            username="bibliotekarka_katalogu", is_staff=True,
        )
        bibliotekarka.groups.add(Group.objects.create(name="Bibliotekarki"))
        bibliotekarka.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="reservations", codename="view_rezerwacja",
            )
        )
        self.client.force_login(bibliotekarka)

        for adres in [
            reverse("catalog:book_list"),
            reverse("catalog:book_detail", args=[self.ksiazka.pk]),
        ]:
            with self.subTest(adres=adres):
                response = self.client.get(adres)
                self.assertContains(
                    response, reverse("admin:reservations_rezerwacja_changelist")
                )
                self.assertNotContains(response, "Moje rezerwacje")

        self.assertNotContains(response, reverse("reservations:reserve_book", args=[self.ksiazka.pk]))
        self.assertContains(response, "zaloguj się na konto czytelnika")

    def test_detail_expires_overdue_reservation_before_showing_availability(self):
        teraz = timezone.now()
        egzemplarz = Egzemplarz.objects.get(
            numer_inwentarzowy="DETAIL-001",
        )
        egzemplarz.dostepny = False
        egzemplarz.save(update_fields=["dostepny"])

        uzytkownik = get_user_model().objects.create_user(
            username="czytelnik_testowy",
            password="TestoweHaslo123!",
        )

        rezerwacja = Rezerwacja.objects.create(
            uzytkownik=uzytkownik,
            egzemplarz=egzemplarz,
            status=Rezerwacja.Status.OCZEKUJACA,
            utworzona_at=teraz - timedelta(hours=50),
            termin_odbioru=teraz - timedelta(hours=2),
        )

        with patch("reservations.services.timezone.now", return_value=teraz):
            response = self.client.get(
                reverse("catalog:book_detail", args=[self.ksiazka.pk])
            )

        rezerwacja.refresh_from_db()
        egzemplarz.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(rezerwacja.status, Rezerwacja.Status.WYGASLA)
        self.assertTrue(egzemplarz.dostepny)
        self.assertEqual(
            response.context["liczba_dostepnych_egzemplarzy"],
            1,
        )
