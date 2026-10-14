from django.db import models


# Create your models here.
class Autor(models.Model):
    imie = models.CharField("imię", max_length=100)
    nazwisko = models.CharField("nazwisko", max_length=150)

    class Meta:
        verbose_name = "autor"
        verbose_name_plural = "autorzy"
        ordering = ["nazwisko", "imie"]

    def __str__(self):
        return f"{self.imie} {self.nazwisko}"


class Gatunek(models.Model):
    nazwa = models.CharField("nazwa", max_length=100, unique=True)

    class Meta:
        verbose_name = "gatunek"
        verbose_name_plural = "gatunki"
        ordering = ["nazwa"]

    def __str__(self):
        return self.nazwa


class Ksiazka(models.Model):
    tytul = models.CharField("tytuł", max_length=255)
    opis = models.TextField("opis", blank=True)
    isbn = models.CharField("ISBN", max_length=13, unique=True, blank=True, null=True)
    rok_wydania = models.PositiveSmallIntegerField("rok wydania", blank=True, null=True)
    autorzy = models.ManyToManyField(
        Autor, related_name="ksiazki", verbose_name="autorzy"
    )
    gatunki = models.ManyToManyField(
        Gatunek, related_name="ksiazki", verbose_name="gatunki", blank=True
    )

    class Meta:
        verbose_name = "książka"
        verbose_name_plural = "książki"
        ordering = ["tytul", "pk"]

    def __str__(self):
        return self.tytul

    def save(self, *args, **kwargs):
        if self.isbn is not None:
            self.isbn = self.isbn.strip() or None

        super().save(*args, **kwargs)


class Egzemplarz(models.Model):
    ksiazka = models.ForeignKey(
        Ksiazka,
        on_delete=models.PROTECT,
        related_name="egzemplarze",
        verbose_name="książka",
    )
    numer_inwentarzowy = models.CharField(
        "numer inwentarzowy", max_length=50, unique=True
    )
    aktywny = models.BooleanField(
        "aktywny",
        default=True,
        help_text="Odznacz, aby wycofać egzemplarz z udostępniania.",
    )

    dostepny = models.BooleanField("dostępny", default=True, editable=False)

    class Meta:
        verbose_name = "egzemplarz"
        verbose_name_plural = "egzemplarze"
        ordering = ["numer_inwentarzowy"]

    def __str__(self):
        return f"{self.numer_inwentarzowy} - {self.ksiazka.tytul}"
