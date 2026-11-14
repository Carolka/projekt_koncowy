from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from faker import Faker
from secrets import token_urlsafe
from django.contrib.auth import get_user_model
from django.db import transaction
from catalog.models import Autor, Egzemplarz, Gatunek, Ksiazka
from pathlib import Path
from django.core.files import File
from django.core.files.base import ContentFile
from django.utils.text import slugify
from PIL import Image, ImageDraw, ImageFont

from hashlib import sha256
from io import BytesIO
import re
from textwrap import fill

from reservations.models import Rezerwacja
from reservations.services import AlreadyReserved, NoAvailableCopy, reserve_book

KSIAZKI_POKAZOWE = [
    {
        "tytul": "Cień nad Motławą",
        "autor": "Zofia Wierzbicka",
        "gatunek": "Kryminał",
        "opis": "Po zaginięciu gdańskiego antykwariusza detektywka znajduje w jego sklepie list, który trzydzieści lat temu miał trafić do jej matki.",
    },
    {
        "tytul": "Dom przy ulicy Lipowej",
        "autor": "Anna Radecka",
        "gatunek": "Powieść obyczajowa",
        "opis": "Dwie siostry wracają do rodzinnego domu, żeby go sprzedać. W starym kredensie znajdują zeszyt, który zmienia ich plany.",
    },
    {
        "tytul": "Mapa pod korą",
        "autor": "Marta Rudzka",
        "gatunek": "Fantasy",
        "opis": "Młoda kartografka odkrywa, że drzewa zapisują drogi do miejsc, których ludzie nie potrafią już odnaleźć.",
    },
    {
        "tytul": "Ostatnie światło Europy",
        "autor": "Jakub Sarnowski",
        "gatunek": "Science fiction",
        "opis": "Załoga stacji na księżycu Jowisza odbiera sygnał z sondy, którą uznano za zaginioną, zanim ktokolwiek z nich się urodził.",
    },
    {
        "tytul": "Nocny pociąg do Przemyśla",
        "autor": "Paweł Bielski",
        "gatunek": "Thriller",
        "opis": "Pasażerka budzi się w pustym wagonie. Na sąsiednim siedzeniu leży jej bilet z dopiskiem: «Nie wysiadaj na następnej stacji».",
    },
    {
        "tytul": "Papierowe miasto",
        "autor": "Helena Brzezińska",
        "gatunek": "Powieść historyczna",
        "opis": "W powojennej Warszawie pracownica drukarni próbuje odnaleźć właścicieli rodzinnych fotografii znalezionych w zrujnowanej kamienicy.",
    },
    {
        "tytul": "Ścieżki, których nie ma na mapie",
        "autor": "Michał Żurawski",
        "gatunek": "Reportaż",
        "opis": "Autor wędruje przez Beskid Niski i rozmawia z ludźmi, którzy postanowili zostać w miejscowościach znikających z rozkładów jazdy.",
    },
    {
        "tytul": "Kret i księżycowy ogród",
        "autor": "Ewa Górska",
        "gatunek": "Literatura dziecięca",
        "opis": "Kret chce wyhodować kwiat, który otwiera się tylko nocą. Żeby znaleźć nasiona, musi po raz pierwszy wyjść z tunelu.",
    },
    {
        "tytul": "Kawa o siódmej",
        "autor": "Natalia Wysocka",
        "gatunek": "Romans",
        "opis": "Dwoje nieznajomych przez pomyłkę zamienia się notesami w kawiarni. Zamiast od razu je oddać, zaczynają zostawiać sobie wiadomości.",
    },
    {
        "tytul": "Miasto po deszczu",
        "autor": "Tomasz Domański",
        "gatunek": "Popularnonaukowa",
        "opis": "Co dzieje się z wodą po ulewie? Książka pokazuje, jak drzewa, ogrody deszczowe i przepuszczalne chodniki pomagają miastom zatrzymać wodę.",
    },
]

POMYSLY_NA_KSIAZKI = [
    (
        "Szyfr w starej drukarni",
        "Kryminał",
        "Reporterka znajduje w dawnej drukarni zaszyfrowane ogłoszenie. "
        "Podany w nim adres prowadzi do domu zaginionego zecera.",
    ),
    (
        "Latarnia bez cienia",
        "Fantasy",
        "Strażniczka latarni odkrywa, że jej światło odsłania wyspę, "
        "która znika z map za każdym razem, gdy gaśnie płomień.",
    ),
    (
        "Zeszyt z przepisami",
        "Powieść obyczajowa",
        "Po zamknięciu rodzinnej piekarni wnuczka znajduje zeszyt z przepisami. "
        "Dopiski na marginesach pomagają jej odtworzyć historię babci.",
    ),
]

OKLADKI_POKAZOWE = {
    "Cień nad Motławą": "cien-nad-motlawa.png",
    "Dom przy ulicy Lipowej": "dom-przy-ulicy-lipowej.png",
    "Mapa pod korą": "mapa-pod-kora.png",
    "Ostatnie światło Europy": "ostatnie-swiatlo-europy.png",
    "Nocny pociąg do Przemyśla": "nocny-pociag-do-przemysla.png",
    "Papierowe miasto": "papierowe-miasto.png",
    "Ścieżki, których nie ma na mapie": "sciezki-ktorych-nie-ma-na-mapie.png",
    "Kret i księżycowy ogród": "kret-i-ksiezycowy-ogrod.png",
    "Kawa o siódmej": "kawa-o-siodmej.png",
    "Miasto po deszczu": "miasto-po-deszczu.png",
}


class Command(BaseCommand):
    help = "Uzupełnia katalog książkami demonstracyjnymi."

    def add_arguments(self, parser):
        parser.add_argument("--books", type=int, default=10)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--users", type=int, default=0)

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Seeder działa tylko przy DEBUG=True.")

        liczba_ksiazek = options["books"]
        if liczba_ksiazek < 0:
            raise CommandError("--books nie może być ujemne.")

        liczba_uzytkownikow = options["users"]
        if liczba_uzytkownikow < 0:
            raise CommandError("--users nie może być ujemne.")

        faker = Faker("pl_PL")
        faker.seed_instance(options["seed"])

        maksymalna_liczba = len(KSIAZKI_POKAZOWE) + len(POMYSLY_NA_KSIAZKI)
        if liczba_ksiazek > maksymalna_liczba:
            raise CommandError(
                f"Obecnie można przygotować maksymalnie {maksymalna_liczba} książek."
            )

        ksiazki = KSIAZKI_POKAZOWE[:liczba_ksiazek]
        liczba_dodatkowych = liczba_ksiazek - len(ksiazki)

        for tytul, gatunek, opis in POMYSLY_NA_KSIAZKI[:liczba_dodatkowych]:
            ksiazki.append(
                {
                    "tytul": tytul,
                    "autor": f"{faker.first_name()} {faker.last_name()}",
                    "gatunek": gatunek,
                    "opis": opis,
                }
            )
        dodane_ksiazki = 0
        dodane_egzemplarze = 0

        with transaction.atomic():
            for numer, dane in enumerate(ksiazki, start=1):
                numer_inwentarzowy = f"DEMO-KS-{numer:03d}"
                liczba_egzemplarzy = faker.random_int(min=1, max=5)

                pierwszy_egzemplarz = (
                    Egzemplarz.objects.select_related("ksiazka")
                    .filter(numer_inwentarzowy=numer_inwentarzowy)
                    .first()
                )
                if pierwszy_egzemplarz is None:
                    imie, nazwisko = dane["autor"].split(" ", maxsplit=1)
                    autor = Autor.objects.filter(imie=imie, nazwisko=nazwisko).first()

                    if autor is None:
                        autor = Autor.objects.create(imie=imie, nazwisko=nazwisko)

                    gatunek, _ = Gatunek.objects.get_or_create(nazwa=dane["gatunek"])

                    ksiazka = Ksiazka.objects.create(
                        tytul=dane["tytul"],
                        opis=dane["opis"],
                    )
                    ksiazka.autorzy.add(autor)
                    ksiazka.gatunki.add(gatunek)

                    Egzemplarz.objects.create(
                        ksiazka=ksiazka,
                        numer_inwentarzowy=numer_inwentarzowy,
                    )
                    dodane_ksiazki += 1
                    dodane_egzemplarze += 1
                else:
                    ksiazka = pierwszy_egzemplarz.ksiazka

                for numer_kopii in range(2, liczba_egzemplarzy + 1):
                    _, utworzony = Egzemplarz.objects.get_or_create(
                        numer_inwentarzowy=f"{numer_inwentarzowy}-{numer_kopii:02d}",
                        defaults={"ksiazka": ksiazka},
                    )
                    if utworzony:
                        dodane_egzemplarze += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Dodano książek: {dodane_ksiazki}, "
                f"dodano egzemplarzy: {dodane_egzemplarze}."
            )
        )

        if liczba_ksiazek:
            ksiazki_demo = (
                Ksiazka.objects.filter(
                    egzemplarze__numer_inwentarzowy__regex=r"^DEMO-KS-[0-9]+$",
                )
                .distinct()
                .prefetch_related("autorzy")
            )
            for ksiazka in ksiazki_demo:
                self.uzupelnij_okladke(ksiazka)
                self.uzupelnij_portrety(ksiazka)

        nowe_konta = self.utworz_konta_demo(liczba_uzytkownikow)
        self.stdout.write(f"Dodano kont demonstracyjnych: {len(nowe_konta)}.")

        for login, haslo in nowe_konta:
            self.stdout.write(f"Login: {login} | Hasło: {haslo}")

        if liczba_ksiazek > 0 and liczba_uzytkownikow > 0:
            self.utworz_rezerwacje_demo()

    def utworz_konta_demo(self, liczba_uzytkownikow):
        User = get_user_model()
        nowe_konta = []

        with transaction.atomic():
            for numer in range(1, liczba_uzytkownikow + 1):
                login = f"demo_czytelnik_{numer:03d}"
                uzytkownik, utworzony = User.objects.get_or_create(
                    username=login,
                )
                if not utworzony:
                    continue
                haslo = token_urlsafe(16)
                uzytkownik.set_password(haslo)
                uzytkownik.save(update_fields=["password"])
                nowe_konta.append((login, haslo))

        return nowe_konta

    def uzupelnij_okladke(self, ksiazka):
        poprzednia_okladka = f"okladki/demo-ksiazka-{ksiazka.pk}"
        stara_generowana = re.fullmatch(
            rf"{re.escape(poprzednia_okladka)}(?:_[A-Za-z0-9]{{7}})?\.png",
            ksiazka.okladka.name or "",
        )
        if ksiazka.okladka and not stara_generowana:
            return

        nazwa_pliku = OKLADKI_POKAZOWE.get(ksiazka.tytul)
        if nazwa_pliku is None:
            self.wygeneruj_okladke(ksiazka)
            return

        sciezka = (
            Path(settings.BASE_DIR) / "catalog" / "demo_assets" / "covers" / nazwa_pliku
        )

        if not sciezka.is_file():
            self.stderr.write(f"Brak pliku okładki: {nazwa_pliku}")
            self.wygeneruj_okladke(ksiazka)
            return

        with sciezka.open("rb") as plik:
            ksiazka.okladka.save(nazwa_pliku, File(plik), save=False)
        ksiazka.save(update_fields=["okladka"])

    def uzupelnij_portrety(self, ksiazka):
        autorzy_pokazowi = {dane["autor"] for dane in KSIAZKI_POKAZOWE}
        folder = Path(settings.BASE_DIR) / "catalog" / "demo_assets" / "authors"

        for autor in ksiazka.autorzy.all():
            nazwa = str(autor)
            if autor.zdjecie or nazwa not in autorzy_pokazowi:
                continue

            nazwa_pliku = slugify(nazwa.replace("ł", "l").replace("Ł", "L")) + ".png"
            sciezka = folder / nazwa_pliku
            if sciezka.is_file():
                with sciezka.open("rb") as plik:
                    autor.zdjecie.save(nazwa_pliku, File(plik), save=False)
                autor.save(update_fields=["zdjecie"])

    def utworz_rezerwacje_demo(self):
        uzytkownik = get_user_model().objects.get(username="demo_czytelnik_001")
        egzemplarz = Egzemplarz.objects.get(numer_inwentarzowy="DEMO-KS-001")
        if Rezerwacja.objects.filter(
            uzytkownik=uzytkownik,
            egzemplarz__ksiazka_id=egzemplarz.ksiazka_id,
        ).exists():
            self.stdout.write("Rezerwacja pokazowa już istnieje w bazie.")
            return

        try:
            rezerwacja = reserve_book(uzytkownik, egzemplarz.ksiazka_id)
        except (AlreadyReserved, NoAvailableCopy) as blad:
            self.stdout.write(f"Pominięto rezerwację pokazową: {blad}")
        else:
            self.stdout.write(f"Dodano rezerwację pokazową #{rezerwacja.pk}.")

    def font_okladki(self, rozmiar):
        for nazwa in (
            "DejaVuSans.ttf",
            "Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ):
            try:
                return ImageFont.truetype(nazwa, rozmiar)
            except OSError:
                continue
        raise CommandError(
            "Do generowania okładek zainstaluj czcionkę DejaVu Sans lub Arial."
        )

    def wygeneruj_okladke(self, ksiazka):
        paleta = ["#164638", "#253657", "#623548", "#704533"]
        indeks = sha256(ksiazka.tytul.encode("utf-8")).digest()[0] % len(paleta)

        obraz = Image.new("RGB", (480, 720), paleta[indeks])
        rysunek = ImageDraw.Draw(obraz)
        krem = "#f5f1e7"

        rysunek.rectangle((24, 24, 455, 695), outline=krem, width=2)
        rysunek.line((65, 365, 415, 365), fill=krem, width=2)

        tytul = fill(ksiazka.tytul, width=18)
        autorzy = ", ".join(str(autor) for autor in ksiazka.autorzy.all())

        sciezka_fontu = "/System/Library/Fonts/Supplemental/Arial.ttf"
        font_tytulu = ImageFont.truetype(sciezka_fontu, 62)
        font_autora = ImageFont.truetype(sciezka_fontu, 30)

        rysunek.multiline_text(
            (240, 190),
            tytul,
            font=font_tytulu,
            fill=krem,
            anchor="mm",
            align="center",
            spacing=8,
        )
        rysunek.multiline_text(
            (240, 425),
            fill(autorzy, width=28),
            font=font_autora,
            fill=krem,
            anchor="mm",
            align="center",
        )

        with BytesIO() as bufor:
            obraz.save(bufor, format="PNG")
            ksiazka.okladka.save(
                f"demo-ksiazka-pl-{ksiazka.pk}.png",
                ContentFile(bufor.getvalue()),
            )
