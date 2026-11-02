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
    path(
        "librarian/reservations/<int:reservation_id>/collect/",
        views.collect_reservation_view,
        name="collect_reservation",
    ),
    path(
        "librarian/reservations/<int:reservation_id>/return/",
        views.return_reservation_view,
        name="return_reservation",
    ),
    path(
        "librarian/reservations/<int:reservation_id>/cancel/",
        views.librarian_cancel_reservation_view,
        name="librarian_cancel_reservation",
    ),
]
