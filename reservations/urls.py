from django.urls import path
from . import views

app_name = "reservations"

urlpatterns = [
    path(
        "book/<int:book_id>/reserve/",
        views.reserve_book_view,
        name="reserve_book",
    ),
    path(
        "reservations/<int:reservation_id>/cancel/",
        views.cancel_reservation_view,
        name="cancel_reservation",
    ),
    path(
        "reservations/",
        views.my_reservations,
        name="my_reservations",
    ),
    path(
        "librarian/reservations/",
        views.librarian_reservations,
        name="librarian_reservations",
    ),
]
