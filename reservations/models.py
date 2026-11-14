from django.db import models
from django.conf import settings
from django.utils import timezone


# Create your models here.
class Rezerwacja(models.Model):
    class Status(models.TextChoices):
        OCZEKUJACA = "OCZEKUJACA", "Oczekująca na odbiór"
        ODEBRANA = "ODEBRANA", "Odebrana"
        ANULOWANA = "ANULOWANA", "Anulowana"
        WYGASLA = "WYGASLA", "Wygasła"
        ZAKONCZONA = "ZAKONCZONA", "Zakończona"

    uzytkownik = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="rezerwacje",
        verbose_name="użytkownik",
    )
    egzemplarz = models.ForeignKey(
        "catalog.Egzemplarz",
        on_delete=models.PROTECT,
        related_name="rezerwacje",
        verbose_name="egzemplarz",
    )
    status = models.CharField(
        "status",
        max_length=20,
        choices=Status.choices,
        default=Status.OCZEKUJACA,
    )
    utworzona_at = models.DateTimeField(
        "data utworzenia",
        default=timezone.now,
        editable=False,
    )
    termin_odbioru = models.DateTimeField("termin odbioru")
    odebrana_at = models.DateTimeField(
        "data odbioru",
        blank=True,
        null=True,
    )
    termin_zwrotu = models.DateTimeField(
        "termin zwrotu",
        blank=True,
        null=True,
    )
    anulowana_at = models.DateTimeField(
        "data anulowania",
        blank=True,
        null=True,
    )
    zwrocona_at = models.DateTimeField(
        "data zwrotu",
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "rezerwacja"
        verbose_name_plural = "rezerwacje"
        ordering = ["-utworzona_at", "-pk"]

        permissions = [
            ("cancel_reservation", "Może anulować rezerwacje użytkowników"),
            ("collect_reservation", "Może potwierdzać odbiór książek"),
            ("return_reservation", "Może potwierdzać zwrot książek"),
        ]

        indexes = [
            models.Index(
                fields=["status", "termin_odbioru"],
                name="rez_status_odbior_idx",
            ),
            models.Index(
                fields=["status", "termin_zwrotu"],
                name="rez_status_zwrot_idx",
            ),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["egzemplarz"],
                condition=models.Q(
                    status__in=["OCZEKUJACA", "ODEBRANA"],
                ),
                name="jedna_aktywna_rez_na_egz",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    termin_odbioru__gt=models.F("utworzona_at"),
                ),
                name="odbior_po_utworzeniu",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        odebrana_at__isnull=True,
                        termin_zwrotu__isnull=True,
                    )
                    | models.Q(
                        odebrana_at__isnull=False,
                        termin_zwrotu__isnull=False,
                        termin_zwrotu__gt=models.F("odebrana_at"),
                    )
                ),
                name="poprawny_termin_zwrotu",
            ),
        ]

    def __str__(self):
        return (
            f"Rezerwacja #{self.pk} – "
            f"{self.egzemplarz} = {self.get_status_display()}"
        )

    @property
    def po_terminie(self):
        return (
            self.status == self.Status.ODEBRANA
            and self.termin_zwrotu is not None
            and self.termin_zwrotu <= timezone.now()
        )
