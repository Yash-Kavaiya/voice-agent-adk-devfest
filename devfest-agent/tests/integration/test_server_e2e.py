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

import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
import requests
from requests.exceptions import RequestException
from websockets.asyncio.client import connect

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "http://127.0.0.1:8000"
RUN_LIVE_URL = "ws://127.0.0.1:8000/run_live"

HEADERS = {"Content-Type": "application/json"}


def log_output(pipe: Any, log_func: Any) -> None:
    """Log the output from the given pipe."""
    for line in iter(pipe.readline, ""):
        log_func(line.strip())


def start_server() -> subprocess.Popen[str]:
    """Start the FastAPI server using subprocess and log its output."""
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.fast_api_app:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ]
    env = os.environ.copy()
    env["INTEGRATION_TEST"] = "TRUE"
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )

    # Start threads to log stdout and stderr in real-time
    threading.Thread(
        target=log_output, args=(process.stdout, logger.info), daemon=True
    ).start()
    threading.Thread(
        target=log_output, args=(process.stderr, logger.error), daemon=True
    ).start()

    return process


def wait_for_server(timeout: int = 90, interval: int = 1) -> bool:
    """Wait for the server to be ready (uvicorn serves nothing until the lifespan runs)."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{BASE_URL}/list-apps", timeout=10)
            if response.status_code == 200:
                logger.info("Server is ready")
                return True
        except RequestException:
            pass
        time.sleep(interval)
    logger.error(f"Server did not become ready within {timeout} seconds")
    return False


@pytest.fixture(scope="session")
def server_fixture(request: Any) -> Iterator[subprocess.Popen[str]]:
    """Pytest fixture to start and stop the server for testing."""
    logger.info("Starting server process")
    server_process = start_server()
    if not wait_for_server():
        pytest.fail("Server failed to start")
    logger.info("Server process started")

    def stop_server() -> None:
        logger.info("Stopping server process")
        server_process.terminate()
        server_process.wait()
        logger.info("Server process stopped")

    request.addfinalizer(stop_server)
    yield server_process


def test_adk_run_live(server_fixture: subprocess.Popen[str]) -> None:
    """Test the native ADK Live route (/run_live) end to end."""
    logger.info("Starting ADK /run_live test")
    user_id = f"user_{uuid.uuid4()}"
    # /run_live closes with 1002 if the session doesn't already exist.
    session_response = requests.post(
        f"{BASE_URL}/apps/app/users/{user_id}/sessions",
        headers=HEADERS,
        json={},
        timeout=60,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    ws_url = (
        f"{RUN_LIVE_URL}?app_name=app&user_id={user_id}"
        f"&session_id={session_id}&modalities=AUDIO"
    )

    async def _turn() -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        async with connect(ws_url) as websocket:
            await websocket.send(
                json.dumps({"content": {"role": "user", "parts": [{"text": "Hi!"}]}})
            )
            while True:
                raw = await asyncio.wait_for(websocket.recv(), timeout=60)
                event = json.loads(raw)
                events.append(event)
                # A tool round-trip emits an extra turnComplete before the
                # answer; keep reading until something has been said.
                if event.get("turnComplete") and any(
                    e.get("outputTranscription") for e in events
                ):
                    break
            await websocket.send(json.dumps({"close": True}))
        return events

    events = asyncio.run(_turn())
    assert events, "No events received from /run_live"
    assert any(
        (transcription := event.get("outputTranscription"))
        and transcription.get("finished")
        and transcription.get("text")
        for event in events
    ), "Expected a finished output transcription"
