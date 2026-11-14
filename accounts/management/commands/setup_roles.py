from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Tworzy grupę Bibliotekarki i przypisuje jej uprawnienia."

    def handle(self, *args, **options):
        uprawnienia_grupy = {
            "catalog": [
                "add_autor",
                "change_autor",
                "delete_autor",
                "view_autor",
                "add_gatunek",
                "change_gatunek",
                "delete_gatunek",
                "view_gatunek",
                "add_ksiazka",
                "change_ksiazka",
                "delete_ksiazka",
                "view_ksiazka",
                "add_egzemplarz",
                "change_egzemplarz",
                "delete_egzemplarz",
                "view_egzemplarz",
            ],
            "reservations": [
                "view_rezerwacja",
                "cancel_reservation",
                "collect_reservation",
                "return_reservation",
            ],
        }

        znalezione_uprawnienia = []
        brakujace_uprawnienia = []

        for app_label, kody_uprawnien in uprawnienia_grupy.items():
            uprawnienia_aplikacji = Permission.objects.filter(
                content_type__app_label=app_label,
                codename__in=kody_uprawnien,
            )

            znalezione_kody = {
                uprawnienie.codename for uprawnienie in uprawnienia_aplikacji
            }

            for kod in kody_uprawnien:
                if kod not in znalezione_kody:
                    brakujace_uprawnienia.append(f"{app_label}.{kod}")

            znalezione_uprawnienia.extend(uprawnienia_aplikacji)

        if brakujace_uprawnienia:
            brakujace = ", ".join(brakujace_uprawnienia)
            raise CommandError(
                f"Nie znaleziono uprawnień: {brakujace}. Najpierw uruchom migracje."
            )

        grupa, utworzono = Group.objects.get_or_create(
            name="Bibliotekarki",
        )

        grupa.permissions.set(znalezione_uprawnienia)

        if utworzono:
            komunikat = "Utworzono grupę Bibliotekarki."
        else:
            komunikat = "Zaktualizowano uprawnienia grupy Bibliotekarki."

        self.stdout.write(
            self.style.SUCCESS(
                f"{komunikat} Liczba uprawnień: " f"{len(znalezione_uprawnienia)}."
            )
        )
