from django.shortcuts import render
from django.core.paginator import Paginator
from django.db.models import Q
from .forms import BookSearchForm
from .models import Ksiazka


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
