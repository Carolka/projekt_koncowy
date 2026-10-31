from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.management import call_command
from django.test import TestCase
from accounts.forms import RegistrationForm


# Create your tests here.
class SetupRolesCommandTests(TestCase):
    def test_creates_librarian_group_with_expected_permissions(self):
        call_command("setup_roles")

        grupa = Group.objects.get(name="Bibliotekarki")
        rzeczywiste_uprawnienia = {
            f"{app_label}.{codename}"
            for app_label, codename in grupa.permissions.values_list(
                "content_type__app_label",
                "codename",
            )
        }

        oczekiwane_uprawnienia = {
            "catalog.add_autor",
            "catalog.change_autor",
            "catalog.delete_autor",
            "catalog.view_autor",
            "catalog.add_gatunek",
            "catalog.change_gatunek",
            "catalog.delete_gatunek",
            "catalog.view_gatunek",
            "catalog.add_ksiazka",
            "catalog.change_ksiazka",
            "catalog.delete_ksiazka",
            "catalog.view_ksiazka",
            "catalog.add_egzemplarz",
            "catalog.change_egzemplarz",
            "catalog.delete_egzemplarz",
            "catalog.view_egzemplarz",
            "reservations.view_rezerwacja",
            "reservations.cancel_reservation",
            "reservations.collect_reservation",
            "reservations.return_reservation",
        }

        self.assertSetEqual(rzeczywiste_uprawnienia, oczekiwane_uprawnienia)

    def test_running_command_twice_does_not_create_duplicate_group(self):
        call_command("setup_roles")
        call_command("setup_roles")

        self.assertEqual(
            Group.objects.filter(name="Bibliotekarki").count(),
            1,
        )


class RegistrationFormTests(TestCase):
    def test_accepts_valid_username_and_passwords(self):
        form = RegistrationForm(
            data={
                "username": "czytelnik_test",
                "password1": "MocneHaslo#427",
                "password2": "MocneHaslo#427",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)

        user = form.save()
        self.assertEqual(user.username, "czytelnik_test")
        self.assertTrue(user.check_password("MocneHaslo#427"))

    def test_rejects_different_passwords(self):
        form = RegistrationForm(
            data={
                "username": "czytelnik_test",
                "password1": "MocneHaslo#427",
                "password2": "InneHaslo#438",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)

    def test_rejects_weak_password(self):
        form = RegistrationForm(
            data={
                "username": "czytelnik_test",
                "password1": "1234",
                "password2": "1234",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)


class RegisterViewTests(TestCase):
    def test_get_display_registration_form(self):
        response = self.client.get(reverse("accounts:register"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/register.html")
        self.assertIsInstance(response.context["form"], RegistrationForm)

    def test_valid_post_creates_user_and_redirects_to_login(self):
        response = self.client.post(
            reverse("accounts:register"),
            data={
                "username": "czytelnik_widok",
                "password1": "MocneHaslo#427",
                "password2": "MocneHaslo#427",
            },
        )

        self.assertRedirects(
            response,
            reverse("login"),
            fetch_redirect_response=False,
        )

        user = get_user_model().objects.get(username="czytelnik_widok")
        self.assertTrue(user.check_password("MocneHaslo#427"))

    def test_invalid_post_does_not_create_user(self):
        response = self.client.post(
            reverse("accounts:register"),
            data={
                "username": "czytelnik_blad",
                "password1": "MocneHaslo#427",
                "password2": "InneHaslo#438",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("password2", response.context["form"].errors)
        self.assertFalse(
            get_user_model().objects.filter(username="czytelnik_blad").exists()
        )


class LoginViewTests(TestCase):
    def setUp(self):
        self.haslo = "MocneHaslo#427"
        self.user = get_user_model().objects.create_user(
            username="czytelnik_logowanie",
            password=self.haslo,
        )

    def test_get_display_login_form(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/login.html")

    def test_valid_login_authenticates_user(self):
        adres_po_zalogowaniu = reverse("accounts:register")

        response = self.client.post(
            reverse("login"),
            data={
                "username": self.user.username,
                "password": self.haslo,
                "next": adres_po_zalogowaniu,
            },
        )
        self.assertRedirects(
            response,
            adres_po_zalogowaniu,
            fetch_redirect_response=False,
        )
        self.assertIn("_auth_user_id", self.client.session)

    def test_invalid_login_does_not_authenticate_user(self):
        response = self.client.post(
            reverse("login"),
            data={
                "username": self.user.username,
                "password": "NiepoprawneHaslo#123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertNotIn("_auth_user_id", self.client.session)
