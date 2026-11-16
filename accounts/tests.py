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

    def test_superuser_lands_in_admin_and_sees_admin_button_in_catalog(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save(update_fields=["is_staff", "is_superuser"])
        self.user.groups.add(Group.objects.create(name="Bibliotekarki"))
        katalog = reverse("catalog:book_list")
        admin = reverse("admin:index")

        response = self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": self.haslo, "next": katalog},
        )
        self.assertRedirects(response, admin)

        response = self.client.get(katalog)
        self.assertContains(
            response, f'<a class="site-nav-button" href="{admin}">Administracja</a>',
            html=True,
        )
        self.assertNotContains(response, "Moje rezerwacje")

    def test_librarian_is_redirected_to_reservations_even_with_catalog_next(self):
        call_command("setup_roles")
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.user.groups.add(Group.objects.get(name="Bibliotekarki"))

        response = self.client.post(
            reverse("login"),
            {
                "username": self.user.username,
                "password": self.haslo,
                "next": reverse("catalog:book_list"),
            },
        )

        self.assertRedirects(response, reverse("admin:reservations_rezerwacja_changelist"))

    def test_librarian_without_reservation_permission_is_redirected_to_admin_index(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.user.groups.add(Group.objects.create(name="Bibliotekarki"))

        response = self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": self.haslo},
        )

        self.assertRedirects(response, reverse("admin:index"))

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


class LogoutViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="czytelnik_wylogowanie",
            password="MocneHaslo#427",
        )

    def test_post_logout_clears_user_session(self):
        self.client.force_login(self.user)
        self.assertIn("_auth_user_id", self.client.session)

        adres_po_wylogowaniu = reverse("login")
        response = self.client.post(
            reverse("logout"),
            data={"next": adres_po_wylogowaniu},
        )
        self.assertRedirects(
            response,
            adres_po_wylogowaniu,
            fetch_redirect_response=False,
        )
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_get_request_does_not_log_out_user(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)
