# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
from collections.abc import Iterator
from types import SimpleNamespace

import pytest

from app import agent
from app.agent import check_availability, create_booking

TOMORROW = (
    datetime.datetime.now(agent.RESTAURANT_TZ).date() + datetime.timedelta(days=1)
).isoformat()


@pytest.fixture(autouse=True)
def empty_book() -> Iterator[None]:
    agent._BOOKINGS.clear()
    yield
    agent._BOOKINGS.clear()


def _context() -> SimpleNamespace:
    return SimpleNamespace(state={})


def test_open_slot_is_available() -> None:
    result = check_availability(TOMORROW, "18:00", 4)
    assert result == {
        "available": True,
        "date": TOMORROW,
        "time": "18:00",
        "party_size": 4,
    }


def test_full_slot_offers_nearby_alternatives() -> None:
    result = check_availability(TOMORROW, "19:30", 6)
    assert result["available"] is False
    assert result["alternatives"] == ["18:30", "19:00", "20:30"]


@pytest.mark.parametrize(
    ("date", "time", "party_size"),
    [
        ("next friday", "19:00", 2),
        (TOMORROW, "7pm", 2),
        (TOMORROW, "16:00", 2),
        (TOMORROW, "19:15", 2),
        ("2020-01-01", "19:00", 2),
        (TOMORROW, "19:00", 0),
        (TOMORROW, "19:00", 13),
    ],
)
def test_invalid_requests_return_error(date: str, time: str, party_size: int) -> None:
    result = check_availability(date, time, party_size)
    assert result["available"] is False
    assert result["error"]


def test_booking_consumes_capacity() -> None:
    context = _context()
    booking = create_booking("Ada", TOMORROW, "18:00", 12, "4155550100", context)
    assert booking["status"] == "confirmed"
    assert booking["booking_code"].startswith("BK-")
    assert context.state["last_booking"]["name"] == "Ada"

    assert check_availability(TOMORROW, "18:00", 4)["available"] is True
    assert check_availability(TOMORROW, "18:00", 5)["available"] is False
    failed = create_booking("Bo", TOMORROW, "18:00", 5, "4155550101", _context())
    assert failed["status"] == "failed"
