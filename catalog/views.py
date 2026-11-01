from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q
from .forms import BookSearchForm
from .models import Ksiazka
from reservations.services import expire_reservations


# Create your views here.
def book_list(request):
    form = BookSearchForm(request.GET or None)
    ksiazki = Ksiazka.objects.prefetch_related("autorzy", "gatunki").order_by(
        "tytul", "pk"
    )

    if form.is_valid():
        fraza = form.cleaned_data["q"]
        gatunek = form.cleaned_data["gatunek"]
        tylko_dostepne = form.cleaned_data["dostepne"]

        if fraza:
            ksiazki = ksiazki.filter(
                Q(tytul__icontains=fraza)
                | Q(isbn__icontains=fraza)
                | Q(autorzy__imie__icontains=fraza)
                | Q(autorzy__nazwisko__icontains=fraza)
            )

        if gatunek:
            ksiazki = ksiazki.filter(gatunki=gatunek)

        if tylko_dostepne == "tak":
            expire_reservations()

            ksiazki = ksiazki.filter(
                egzemplarze__aktywny=True,
                egzemplarze__dostepny=True,
            )
    ksiazki = ksiazki.distinct()

    paginator = Paginator(ksiazki, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    parametry = request.GET.copy()
    parametry.pop("page", None)
    query_string = parametry.urlencode()

    if query_string:
        query_string += "&"

    return render(
        request,
        "catalog/book_list.html",
        {
            "form": form,
            "page_obj": page_obj,
            "query_string": query_string,
        },
    )


def book_detail(request, pk):
    # zwolnienie egzemplarzy przeterminowanych rezerwacji
    expire_reservations()

    ksiazka = get_object_or_404(
        Ksiazka.objects.prefetch_related("autorzy", "gatunki"),
        pk=pk,
    )
    liczba_aktywnych_egzemplarzy = ksiazka.egzemplarze.filter(
        aktywny=True,
    ).count()

    liczba_dostepnych_egzemplarzy = ksiazka.egzemplarze.filter(
        aktywny=True,
        dostepny=True,
    ).count()

    return render(
        request,
        "catalog/book_detail.html",
        {
            "ksiazka": ksiazka,
            "liczba_aktywnych_egzemplarzy": liczba_aktywnych_egzemplarzy,
            "liczba_dostepnych_egzemplarzy": liczba_dostepnych_egzemplarzy,
        },
    )
