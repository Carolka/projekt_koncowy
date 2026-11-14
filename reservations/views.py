from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.http import require_POST, require_GET
from django.db.models import Q
from django.utils import timezone
from django.core.paginator import Paginator
from catalog.models import Ksiazka
from reservations.services import (
    AlreadyReserved,
    NoAvailableCopy,
    reserve_book,
    ReservationNotCancellable,
    ReservationNotCollectable,
    ReservationNotReturnable,
    return_reservation,
    cancel_reservation,
    expire_reservations,
    collect_reservation,
)
from reservations.models import Rezerwacja


# Create your views here.
@login_required
@require_POST
def reserve_book_view(request, book_id):
    get_object_or_404(Ksiazka, pk=book_id)

    try:
        reserve_book(request.user, book_id)
    except (AlreadyReserved, NoAvailableCopy) as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request,
            "Rezerwacja została utworzona. Masz 48 godzin na odbiór.",
        )

    return redirect("catalog:book_detail", pk=book_id)


@login_required
@require_POST
def cancel_reservation_view(request, reservation_id):
    rezerwacja = get_object_or_404(
        Rezerwacja.objects.select_related("egzemplarz"),
        pk=reservation_id,
    )

    try:
        cancel_reservation(
            rezerwacja.pk, request.user, wymagaj_nowego_anulowania=True
        )
    except ReservationNotCancellable as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Rezerwacja została anulowana.")

    return redirect(
        "catalog:book_detail",
        pk=rezerwacja.egzemplarz.ksiazka_id,
    )


@login_required
@require_GET
def my_reservations(request):
    teraz = timezone.now()

    rezerwacje = (
        Rezerwacja.objects.filter(
            uzytkownik=request.user,
        )
        .select_related(
            "egzemplarz__ksiazka",
        )
        .order_by(
            "-utworzona_at",
            "-pk",
        )
    )

    biezace_rezerwacje = rezerwacje.filter(
        Q(
            status=Rezerwacja.Status.OCZEKUJACA,
            termin_odbioru__gt=teraz,
        )
        | Q(status=Rezerwacja.Status.ODEBRANA)
    )

    historyczne_rezerwacje = rezerwacje.filter(
        Q(
            status__in=[
                Rezerwacja.Status.ANULOWANA,
                Rezerwacja.Status.WYGASLA,
                Rezerwacja.Status.ZAKONCZONA,
            ]
        )
        | Q(
            status=Rezerwacja.Status.OCZEKUJACA,
            termin_odbioru__lte=teraz,
        )
    )

    return render(
        request,
        "reservations/my_reservations.html",
        {
            "biezace_rezerwacje": biezace_rezerwacje,
            "historyczne_rezerwacje": historyczne_rezerwacje,
            "teraz": teraz,
        },
    )


@require_GET
@login_required
@permission_required(
    "reservations.view_rezerwacja",
    raise_exception=True,
)
def librarian_reservations(request):
    # aktualizacja wygasłych rezerwacji przed wyświetleniem
    expire_reservations()

    fraza = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")

    dozwolone_statusy = dict(Rezerwacja.Status.choices)
    if status not in dozwolone_statusy:
        status = ""

    rezerwacje = Rezerwacja.objects.select_related(
        "uzytkownik",
        "egzemplarz__ksiazka",
    )

    if fraza:
        rezerwacje = rezerwacje.filter(
            Q(uzytkownik__username__icontains=fraza)
            | Q(uzytkownik__first_name__icontains=fraza)
            | Q(uzytkownik__last_name__icontains=fraza)
            | Q(egzemplarz__ksiazka__tytul__icontains=fraza)
            | Q(egzemplarz__numer_inwentarzowy__icontains=fraza)
        )
    if status:
        rezerwacje = rezerwacje.filter(status=status)

    rezerwacje = rezerwacje.order_by("-utworzona_at", "-pk")
    page_obj = Paginator(rezerwacje, 20).get_page(request.GET.get("page"))
    for rezerwacja in page_obj:
        rezerwacja.mozna_potwierdzic_odbior = (
            rezerwacja.status == Rezerwacja.Status.OCZEKUJACA
            and request.user.has_perm("reservations.collect_reservation")
        )
        rezerwacja.mozna_potwierdzic_zwrot = (
            rezerwacja.status == Rezerwacja.Status.ODEBRANA
            and request.user.has_perm("reservations.return_reservation")
        )
        rezerwacja.mozna_anulowac = (
            rezerwacja.status == Rezerwacja.Status.OCZEKUJACA
            and request.user.has_perm("reservations.cancel_reservation")
        )
        rezerwacja.ma_akcje = (
            rezerwacja.mozna_potwierdzic_odbior
            or rezerwacja.mozna_potwierdzic_zwrot
            or rezerwacja.mozna_anulowac
        )
    parametry = request.GET.copy()
    parametry.pop("page", None)
    query_string = parametry.urlencode()
    if query_string:
        query_string += "&"

    statusy = [
        {
            "kod": kod,
            "nazwa": nazwa,
            "wybrany": kod == status,
        }
        for kod, nazwa in Rezerwacja.Status.choices
    ]

    return render(
        request,
        "reservations/librarian_reservations.html",
        {
            "rezerwacje": page_obj,
            "page_obj": page_obj,
            "fraza": fraza,
            "wybrany_status": status,
            "statusy": statusy,
            "query_string": query_string,
        },
    )


@require_POST
@login_required
@permission_required(
    "reservations.collect_reservation",
    raise_exception=True,
)
def collect_reservation_view(request, reservation_id):
    rezerwacja = get_object_or_404(
        Rezerwacja,
        pk=reservation_id,
    )

    expire_reservations()

    try:
        collect_reservation(
            rezerwacja.pk, request.user, wymagaj_nowego_odbioru=True
        )
    except ReservationNotCollectable as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Odbiór książki został potwierdzony.")

    return redirect("reservations:librarian_reservations")


@require_POST
@login_required
@permission_required(
    "reservations.return_reservation",
    raise_exception=True,
)
def return_reservation_view(request, reservation_id):
    rezerwacja = get_object_or_404(
        Rezerwacja,
        pk=reservation_id,
    )
    try:
        return_reservation(
            rezerwacja.pk, request.user, wymagaj_nowego_zwrotu=True
        )
    except ReservationNotReturnable as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Zwrot książki został potwierdzony.")

    return redirect("reservations:librarian_reservations")


@require_POST
@login_required
@permission_required(
    "reservations.cancel_reservation",
    raise_exception=True,
)
def librarian_cancel_reservation_view(request, reservation_id):
    rezerwacja = get_object_or_404(
        Rezerwacja,
        pk=reservation_id,
    )
    try:
        cancel_reservation(
            rezerwacja.pk, request.user, wymagaj_nowego_anulowania=True
        )
    except ReservationNotCancellable as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Rezerwacja została anulowana.")

    return redirect("reservations:librarian_reservations")
