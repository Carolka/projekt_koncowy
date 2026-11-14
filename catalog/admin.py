from django.contrib import admin

from .models import Autor, Egzemplarz, Gatunek, Ksiazka

# Register your models here.


@admin.register(Autor)
class AutorAdmin(admin.ModelAdmin):
    list_display = ("imie", "nazwisko")
    search_fields = ("imie", "nazwisko")
    ordering = ("nazwisko", "imie")

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(
            request, {"title": "Autorzy", **(extra_context or {})}
        )

    def render_change_form(
        self, request, context, add=False, change=False, form_url="", obj=None
    ):
        if change:
            context["title"] = (
                "Zmień autora"
                if self.has_change_permission(request, obj)
                else "Zobacz autora"
            )
        return super().render_change_form(
            request, context, add=add, change=change, form_url=form_url, obj=obj
        )


@admin.register(Gatunek)
class GatunekAdmin(admin.ModelAdmin):
    list_display = ("nazwa",)
    search_fields = ("nazwa",)
    ordering = ("nazwa",)


class EgzemplarzInline(admin.TabularInline):
    model = Egzemplarz
    extra = 0
    fields = ("numer_inwentarzowy", "aktywny", "dostepny")
    readonly_fields = ("dostepny",)


@admin.register(Ksiazka)
class KsiazkaAdmin(admin.ModelAdmin):
    list_display = ("tytul", "isbn", "rok_wydania")
    search_fields = (
        "tytul",
        "isbn",
        "autorzy__imie",
        "autorzy__nazwisko",
        "egzemplarze__numer_inwentarzowy",
    )
    list_filter = ("gatunki", "egzemplarze__aktywny")
    filter_horizontal = ("autorzy", "gatunki")
    inlines = (EgzemplarzInline,)

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(
            request, {"title": "Książki", **(extra_context or {})}
        )

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        if change:
            context["title"] = (
                "Zmień książkę"
                if self.has_change_permission(request, obj)
                else "Zobacz książkę"
            )
        return super().render_change_form(
            request, context, add=add, change=change, form_url=form_url, obj=obj
        )


@admin.register(Egzemplarz)
class EgzemplarzAdmin(admin.ModelAdmin):
    list_display = ("numer_inwentarzowy", "ksiazka", "aktywny", "dostepny")
    search_fields = (
        "numer_inwentarzowy",
        "ksiazka__tytul",
        "ksiazka__isbn",
        "ksiazka__autorzy__imie",
        "ksiazka__autorzy__nazwisko",
    )
    list_filter = ("aktywny", "dostepny")
    list_select_related = ("ksiazka",)
    readonly_fields = ("dostepny",)
