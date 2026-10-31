from django.test import TestCase
from django.urls import reverse
from catalog.forms import BookSearchForm
from catalog.models import Gatunek, Autor, Egzemplarz, Ksiazka


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
