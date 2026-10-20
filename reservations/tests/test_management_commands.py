from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase


class ExpireReservationsCommandTests(SimpleTestCase):
    # Sprawdzamy, czy komenda wypisuje liczbę zwróconą przez serwis.
    def test_command_runs_service_and_reports_number_of_expired_reservations(self):
        output = StringIO()
        with patch(
            "reservations.management.commands.expire_reservations.expire_reservations",
            return_value=3,
        ) as expire_reservations_mock:
            call_command("expire_reservations", stdout=output)

        expire_reservations_mock.assert_called_once_with()
        self.assertIn(
            "Liczba wygaszonych rezerwacji: 3",
            output.getvalue(),
        )
