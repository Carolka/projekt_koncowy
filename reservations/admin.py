from django.contrib import admin, messages
from django.contrib.admin.views.main import SEARCH_VAR, ChangeList
from django.core.exceptions import PermissionDenied
from django.utils import formats, timezone
from django.utils.html import format_html

# Register your models here.
from .models import Rezerwacja
from .services import (
    ReservationNotCancellable,
    ReservationNotCollectable,
    ReservationNotReturnable,
    cancel_reservation,
    collect_reservation,
    return_reservation,
)


class RezerwacjaChangeList(ChangeList):
    def get_filters_params(self, params=None):
        filtry = super().get_filters_params(params)
        # Pole wyszukiwania nie jest filtrem modelu.
        filtry.pop("pole", None)
        return filtry


class RezerwacjaAdmin(admin.ModelAdmin):
    change_list_template = "admin/reservations/rezerwacja/change_list.html"
    list_display = (
        "czytelnik",
        "ksiazka",
        "sygnatura",
        "etykieta_statusu",
        "data_utworzenia",
        "data_terminu_odbioru",
        "data_odbioru",
        "data_terminu_zwrotu",
        "data_anulowania",
        "data_zwrotu",
    )

    pola_wyszukiwania = {
        "uzytkownik": (
            "uzytkownik__username",
            "uzytkownik__first_name",
            "uzytkownik__last_name",
        ),
        "ksiazka": ("egzemplarz__ksiazka__tytul",),
        "sygnatura": ("egzemplarz__numer_inwentarzowy",),
    }
    search_fields = (
        *pola_wyszukiwania["uzytkownik"],
        *pola_wyszukiwania["ksiazka"],
        *pola_wyszukiwania["sygnatura"],
    )

    list_filter = ("status", "utworzona_at")

    readonly_fields = (
        "uzytkownik",
        "egzemplarz",
        "status",
        "utworzona_at",
        "termin_odbioru",
        "odebrana_at",
        "termin_zwrotu",
        "anulowana_at",
        "zwrocona_at",
    )

    list_select_related = ("uzytkownik", "egzemplarz__ksiazka")

    actions = (
        "anuluj_rezerwacje",
        "potwierdz_odbior",
        "potwierdz_zwrot",
    )

    @admin.display(description="Użytkownik", ordering="uzytkownik__last_name")
    def czytelnik(self, rezerwacja):
        uzytkownik = rezerwacja.uzytkownik
        nazwa = uzytkownik.get_full_name() or uzytkownik.get_username()
        numer_karty = f"BK{uzytkownik.pk:05d}"
        return format_html(
            "<strong>{}</strong><br><small>Nr karty: {}</small>", nazwa, numer_karty
        )

    @admin.display(description="Książka", ordering="egzemplarz__ksiazka__tytul")
    def ksiazka(self, rezerwacja):
        ksiazka = rezerwacja.egzemplarz.ksiazka
        autorzy = ", ".join(str(autor) for autor in ksiazka.autorzy.all())
        if autorzy:
            return format_html(
                "<strong>{}</strong><br><small>{}</small>", ksiazka.tytul, autorzy
            )
        return ksiazka.tytul

    @admin.display(description="Sygnatura", ordering="egzemplarz__numer_inwentarzowy")
    def sygnatura(self, rezerwacja):
        return rezerwacja.egzemplarz.numer_inwentarzowy

    @admin.display(description="Status", ordering="status")
    def etykieta_statusu(self, rezerwacja):
        etykieta = (
            "Zwrócona"
            if rezerwacja.status == Rezerwacja.Status.ZAKONCZONA
            else rezerwacja.get_status_display()
        )
        return format_html(
            '<span class="reservation-status-stack">'
            '<span class="reservation-status-badge reservation-status-badge--{}">{}</span>{}'
            '</span>',
            rezerwacja.status.lower(),
            etykieta,
            format_html('<small class="reservation-status-overdue">{}</small>', "Po terminie")
            if rezerwacja.po_terminie else "",
        )

    @staticmethod
    def _krotka_data(wartosc):
        if wartosc is None:
            return None
        return formats.date_format(timezone.localtime(wartosc), "d.m.Y H:i")

    @admin.display(description="Data utworzenia", ordering="utworzona_at")
    def data_utworzenia(self, rezerwacja):
        return self._krotka_data(rezerwacja.utworzona_at)

    @admin.display(description="Termin odbioru", ordering="termin_odbioru")
    def data_terminu_odbioru(self, rezerwacja):
        return self._krotka_data(rezerwacja.termin_odbioru)

    @admin.display(description="Data odbioru", ordering="odebrana_at")
    def data_odbioru(self, rezerwacja):
        return self._krotka_data(rezerwacja.odebrana_at)

    @admin.display(description="Termin zwrotu", ordering="termin_zwrotu")
    def data_terminu_zwrotu(self, rezerwacja):
        return self._krotka_data(rezerwacja.termin_zwrotu)

    @admin.display(description="Data anulowania", ordering="anulowana_at")
    def data_anulowania(self, rezerwacja):
        return self._krotka_data(rezerwacja.anulowana_at)

    @admin.display(description="Data zwrotu", ordering="zwrocona_at")
    def data_zwrotu(self, rezerwacja):
        return self._krotka_data(rezerwacja.zwrocona_at)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("egzemplarz__ksiazka__autorzy")

    def get_changelist(self, request, **kwargs):
        return RezerwacjaChangeList

    def get_search_fields(self, request):
        return self.pola_wyszukiwania.get(request.GET.get("pole"), self.search_fields)

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(
            request, {"title": "Rezerwacje", **(extra_context or {})}
        )
        context = getattr(response, "context_data", None)
        if context and "cl" in context:
            lista = context["cl"]
            context["filtry_rezerwacji"] = [
                {
                    "etykieta": spec.title.capitalize(),
                    "parametry": spec.expected_parameters(),
                    "opcje": list(spec.choices(lista)),
                }
                for spec in lista.filter_specs
            ]
            context["parametr_szukania"] = SEARCH_VAR
            pole = request.GET.get("pole", "")
            context["pole_wyszukiwania"] = pole if pole in self.pola_wyszukiwania else ""
        return response

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return super().change_view(
            request,
            object_id,
            form_url,
            {"title": "Zobacz rezerwację", **(extra_context or {})},
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_cancel_reservation_permission(self, request):
        return request.user.has_perm("reservations.cancel_reservation")

    @admin.action(
        description="Anuluj wybrane rezerwacje",
        permissions=["cancel_reservation"],
    )
    def anuluj_rezerwacje(self, request, queryset):
        liczba_obsluzonych = 0

        for rezerwacja in queryset:
            try:
                cancel_reservation(
                    rezerwacja.pk, request.user, wymagaj_nowego_anulowania=True
                )
            except (PermissionDenied, ReservationNotCancellable) as blad:
                self.message_user(
                    request,
                    f"Rezerwacja #{rezerwacja.pk}: {blad}",
                    level=messages.WARNING,
                )
            else:
                liczba_obsluzonych += 1

        if liczba_obsluzonych:
            self.message_user(
                request,
                f"Akcję anulowania wykonano dla " f"{liczba_obsluzonych} rezerwacji.",
                level=messages.SUCCESS,
            )

    def has_collect_reservation_permission(self, request):
        return request.user.has_perm("reservations.collect_reservation")

    def has_return_reservation_permission(self, request):
        return request.user.has_perm("reservations.return_reservation")

    @admin.action(
        description="Potwierdź odbiór wybranych rezerwacji",
        permissions=["collect_reservation"],
    )
    def potwierdz_odbior(self, request, queryset):
        liczba_potwierdzonych = 0

        for rezerwacja in queryset:
            try:
                collect_reservation(
                    rezerwacja.pk, request.user, wymagaj_nowego_odbioru=True
                )
            except (PermissionDenied, ReservationNotCollectable) as blad:
                self.message_user(
                    request,
                    f"Rezerwacja #{rezerwacja.pk}: {blad}",
                    level=messages.WARNING,
                )
            else:
                liczba_potwierdzonych += 1

        if liczba_potwierdzonych:
            self.message_user(
                request,
                f"Potwierdzono odbiór dla {liczba_potwierdzonych} rezerwacji.",
                level=messages.SUCCESS,
            )

    @admin.action(
        description="Potwierdź zwrot wybranych rezerwacji",
        permissions=["return_reservation"],
    )
    def potwierdz_zwrot(self, request, queryset):
        liczba_zwroconych = 0

        for rezerwacja in queryset:
            try:
                return_reservation(
                    rezerwacja.pk, request.user, wymagaj_nowego_zwrotu=True
                )
            except (PermissionDenied, ReservationNotReturnable) as blad:
                self.message_user(
                    request,
                    f"Rezerwacja #{rezerwacja.pk}: {blad}",
                    level=messages.WARNING,
                )
            else:
                liczba_zwroconych += 1

        if liczba_zwroconych:
            self.message_user(
                request,
                f"Potwierdzono zwrot dla {liczba_zwroconych} rezerwacji.",
                level=messages.SUCCESS,
            )


admin.site.register(Rezerwacja, RezerwacjaAdmin)
