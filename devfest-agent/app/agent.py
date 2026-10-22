# ruff: noqa
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
import os
import random
from zoneinfo import ZoneInfo

from google.adk.agents import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.genai import types


# Live models are native audio (audio in, audio out) and are served from a
# regional endpoint, not `global`. Pin the region on the model so it wins over
# GOOGLE_CLOUD_LOCATION. Leave LIVE_LOCATION empty when using AI Studio.
MODEL = os.getenv("LIVE_MODEL", "gemini-3.8-live")
LIVE_LOCATION = os.getenv("LIVE_LOCATION", "us-central1")
VOICE = os.getenv("LIVE_VOICE", "Aoede")

RESTAURANT_NAME = "Trattoria DevFest"
RESTAURANT_TZ = ZoneInfo("America/Los_Angeles")

# Bookable slots run every 30 minutes; the last seating is 21:30.
OPENING_TIME = datetime.time(17, 0)
LAST_SEATING = datetime.time(21, 30)
SLOT_MINUTES = 30
SEATS_PER_SLOT = 16
MAX_PARTY_SIZE = 12
# Prime time is mostly booked already, so the demo can show alternatives.
PRE_BOOKED_SEATS = {datetime.time(19, 30): 14, datetime.time(20, 0): 12}

# Mock reservation book: booking code -> booking details.
_BOOKINGS: dict[str, dict] = {}


def _parse_slot(date: str, time: str) -> tuple[datetime.date, datetime.time] | str:
    """Parses and validates a requested slot, returning an error string if invalid."""
    try:
        day = datetime.date.fromisoformat(date)
    except ValueError:
        return f"Invalid date '{date}'. Use the YYYY-MM-DD format."
    try:
        slot = datetime.time.fromisoformat(time)
    except ValueError:
        return f"Invalid time '{time}'. Use the 24-hour HH:MM format."
    if day < datetime.datetime.now(RESTAURANT_TZ).date():
        return "That date is in the past."
    if not OPENING_TIME <= slot <= LAST_SEATING or slot.minute % SLOT_MINUTES:
        return (
            "We seat guests every half hour from 17:00 to 21:30, "
            "so that time is not bookable."
        )
    return day, slot


def _seats_left(day: datetime.date, slot: datetime.time) -> int:
    booked = PRE_BOOKED_SEATS.get(slot, 0) + sum(
        b["party_size"]
        for b in _BOOKINGS.values()
        if b["date"] == day.isoformat() and b["time"] == slot.strftime("%H:%M")
    )
    return SEATS_PER_SLOT - booked


def _all_slots() -> list[datetime.time]:
    slots, current = [], datetime.datetime.combine(datetime.date.min, OPENING_TIME)
    while current.time() <= LAST_SEATING:
        slots.append(current.time())
        current += datetime.timedelta(minutes=SLOT_MINUTES)
    return slots


def check_availability(date: str, time: str, party_size: int) -> dict:
    """Checks whether a table is available at the restaurant.

    Args:
        date: The reservation date in YYYY-MM-DD format.
        time: The reservation time in 24-hour HH:MM format, e.g. "19:30".
        party_size: The number of guests.

    Returns:
        A dict with "available" (bool), and either the confirmed slot or an
        "alternatives" list of nearby open times on the same date, or an "error".
    """
    if not 1 <= party_size <= MAX_PARTY_SIZE:
        return {
            "available": False,
            "error": f"We take bookings for 1 to {MAX_PARTY_SIZE} guests.",
        }
    parsed = _parse_slot(date, time)
    if isinstance(parsed, str):
        return {"available": False, "error": parsed}
    day, slot = parsed

    if _seats_left(day, slot) >= party_size:
        return {
            "available": True,
            "date": day.isoformat(),
            "time": slot.strftime("%H:%M"),
            "party_size": party_size,
        }

    # Offer the three closest open slots on the same day.
    requested = slot.hour * 60 + slot.minute
    open_slots = [s for s in _all_slots() if _seats_left(day, s) >= party_size]
    open_slots.sort(key=lambda s: abs(s.hour * 60 + s.minute - requested))
    return {
        "available": False,
        "date": day.isoformat(),
        "alternatives": sorted(s.strftime("%H:%M") for s in open_slots[:3]),
    }


def create_booking(
    name: str,
    date: str,
    time: str,
    party_size: int,
    phone: str,
    tool_context: ToolContext,
) -> dict:
    """Books a table. Only call this after the guest has confirmed every detail.

    Args:
        name: The name the booking is under.
        date: The reservation date in YYYY-MM-DD format.
        time: The reservation time in 24-hour HH:MM format, e.g. "19:30".
        party_size: The number of guests.
        phone: A contact phone number for the booking.

    Returns:
        A dict with "status" ("confirmed" or "failed"), the booking details and a
        booking code on success, or an "error" on failure.
    """
    availability = check_availability(date, time, party_size)
    if not availability["available"]:
        return {"status": "failed", **availability}

    code = f"BK-{random.randint(1000, 9999)}"
    while code in _BOOKINGS:
        code = f"BK-{random.randint(1000, 9999)}"
    booking = {
        "booking_code": code,
        "name": name,
        "date": availability["date"],
        "time": availability["time"],
        "party_size": party_size,
        "phone": phone,
    }
    _BOOKINGS[code] = booking
    tool_context.state["last_booking"] = booking
    return {"status": "confirmed", **booking}


def instruction(context: ReadonlyContext) -> str:
    today = datetime.datetime.now(RESTAURANT_TZ)
    return f"""You are the friendly phone host for {RESTAURANT_NAME}, an Italian restaurant. You take table reservations by voice.
Today is {today.strftime("%A, %B %d, %Y")}. Resolve relative dates like "tomorrow" or "this Friday" yourself.

Everything you say is spoken aloud, so:
- Never use markdown, lists, emoji, symbols, or URLs.
- Keep each reply to one or two short sentences, then ask one question.
- Say dates, times, and numbers the way a person would, like "Friday, March third at seven thirty". Read booking codes and phone numbers digit by digit.

To make a booking, collect the date, time, and party size, then say something like "let me check that for you" and call check_availability.
If the slot is taken, offer the alternatives it returns. We seat guests every half hour from five to nine thirty in the evening, for up to {MAX_PARTY_SIZE} guests.
Once a slot is available, ask for the name and a phone number. Then read back the name, date, time, party size, and phone number, and only call create_booking after the guest clearly says yes.
After booking, tell them their booking code and wish them a lovely evening.
If something is unclear or you may have misheard, ask again rather than guessing. Politely steer off-topic requests back to reservations."""


root_agent = Agent(
    # Keep in sync with create_params.root_agent_name in agents-cli-manifest.yaml:
    # telemetry reports this name as gen_ai.agent.name, and agents-cli reports the
    # manifest's value. Renaming the agent only here makes the two disagree, and
    # anything selecting traces by name stops finding this agent's.
    name="devfest_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
        client_kwargs={"location": LIVE_LOCATION} if LIVE_LOCATION else None,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE)
            ),
            language_code="en-US",
        ),
    ),
    instruction=instruction,
    tools=[check_availability, create_booking],
)

app = App(
    root_agent=root_agent,
    name="app",
)
