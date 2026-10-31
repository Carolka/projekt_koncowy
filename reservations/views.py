from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from catalog.models import Ksiazka
from reservations.services import AlreadyReserved, NoAvailableCopy, reserve_book


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
