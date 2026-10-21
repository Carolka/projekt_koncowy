from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase


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
