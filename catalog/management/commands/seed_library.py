from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from faker import Faker
from secrets import token_urlsafe
from django.contrib.auth import get_user_model
from django.db import transaction
from catalog.models import Autor, Egzemplarz, Gatunek, Ksiazka
from pathlib import Path
from django.core.files import File

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

        ksiazki = KSIAZKI_POKAZOWE[:liczba_ksiazek]
        while len(ksiazki) < liczba_ksiazek:
            miejsce = faker.random_element(
                ["Gdańsku", "Krakowie", "Lublinie", "Toruniu"]
            )
            temat = faker.random_element(["List", "Ślad", "Szyfr", "Sekret"])

            ksiazki.append(
                {
                    "tytul": f"{temat} w {miejsce}",
                    "autor": f"{faker.first_name()} {faker.last_name()}",
                    "gatunek": "Kryminał",
                    "opis": (
                        f"Podczas śledztwa w {miejsce} detektywka odkrywa, "
                        f"że {temat.lower()} może wyjaśnić zaginięcie bibliotekarza."
                    ),
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

                self.uzupelnij_okladke(ksiazka, dane["tytul"])

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

        nowe_konta = self.utworz_konta_demo(liczba_uzytkownikow)
        self.stdout.write(f"Dodano kont demonstracyjnych: {len(nowe_konta)}.")

        for login, haslo in nowe_konta:
            self.stdout.write(f"Login: {login} | Hasło: {haslo}")

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

    def uzupelnij_okladke(self, ksiazka, tytul_pokazowy):
        nazwa_pliku = OKLADKI_POKAZOWE.get(tytul_pokazowy)

        if ksiazka.okladka or nazwa_pliku is None:
            return

        sciezka = (
            Path(settings.BASE_DIR) / "catalog" / "demo_assets" / "covers" / nazwa_pliku
        )

        if not sciezka.is_file():
            self.stderr.write("Brak pliku okładki: {nazwa_pliku}")
            return

        with sciezka.open("rb") as plik:
            ksiazka.okladka.save(nazwa_pliku, File(plik), save=False)
        ksiazka.save(update_fields=["okladka"])
