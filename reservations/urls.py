from django.urls import path
from . import views

app_name = "reservations"

urlpatterns = [
    path(
        "book/<int:book_id>/reserve/",
        views.reserve_book_view,
        name="reserve_book",
    ),
]
