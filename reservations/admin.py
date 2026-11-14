from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied

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


class RezerwacjaAdmin(admin.ModelAdmin):
    list_display = (
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

    search_fields = (
        "uzytkownik__username",
        "egzemplarz__ksiazka__tytul",
        "egzemplarz__numer_inwentarzowy",
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

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(
            request, {"title": "Rezerwacje", **(extra_context or {})}
        )

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
                cancel_reservation(rezerwacja.pk, request.user)
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
                collect_reservation(rezerwacja.pk, request.user)
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
                return_reservation(rezerwacja.pk, request.user)
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
