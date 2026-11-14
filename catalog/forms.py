from django import forms
from .models import Gatunek


class BookSearchForm(forms.Form):
    q = forms.CharField(
        label="Szukaj",
        required=False,
        max_length=255,
    )
    pole = forms.ChoiceField(
        label="Szukaj według",
        choices=[
            ("", "Tytuł, autor lub ISBN"),
            ("tytul", "Tytuł"),
            ("autor", "Autor"),
        ],
        required=False,
    )
    gatunek = forms.ModelChoiceField(
        label="Gatunek",
        queryset=Gatunek.objects.all(),
        required=False,
        empty_label="Wszystkie gatunki",
    )

    dostepne = forms.ChoiceField(
        label="Dostępność",
        choices=[
            ("", "Wszystkie książki"),
            ("tak", "Tylko dostępne"),
        ],
        required=False,
    )
