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

from dotenv import load_dotenv
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# The agent reads LIVE_* settings at import time, so load .env first.
load_dotenv()

from app.agent import root_agent  # noqa: E402

APP_NAME = "test"
USER_ID = "test_user"


def test_agent_live_stream() -> None:
    """The agent answers over run_live with audio plus a transcript, using its tools."""

    async def _turn() -> tuple[str, int, set[str]]:
        session_service = InMemorySessionService()
        # The session must exist before run_live, or it raises "Session not found".
        session = await session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID
        )
        runner = Runner(
            agent=root_agent, session_service=session_service, app_name=APP_NAME
        )
        queue = LiveRequestQueue()
        queue.send_content(
            types.Content(
                role="user",
                parts=[types.Part(text="Is there a table for two tomorrow at 7pm?")],
            )
        )

        transcript, audio_chunks, tool_calls = "", 0, set()
        try:
            async for event in runner.run_live(
                user_id=USER_ID,
                session_id=session.id,
                live_request_queue=queue,
                run_config=RunConfig(
                    response_modalities=["AUDIO"],
                    input_audio_transcription=types.AudioTranscriptionConfig(),
                    output_audio_transcription=types.AudioTranscriptionConfig(),
                ),
            ):
                # Consume the finished aggregate; partials would duplicate text.
                if (
                    event.output_transcription
                    and event.output_transcription.finished
                    and event.output_transcription.text
                ):
                    transcript += event.output_transcription.text
                tool_calls.update(call.name for call in event.get_function_calls())
                if event.content and event.content.parts:
                    audio_chunks += sum(
                        1 for part in event.content.parts if part.inline_data
                    )
                # A tool round-trip emits an extra turn_complete before the
                # spoken answer, so only stop once the tool result was spoken.
                if event.turn_complete and transcript and tool_calls:
                    break
        finally:
            queue.close()
        return transcript, audio_chunks, tool_calls

    transcript, audio_chunks, tool_calls = asyncio.run(
        asyncio.wait_for(_turn(), timeout=120)
    )
    assert transcript.strip(), "Expected a non-empty output transcript"
    assert audio_chunks > 0, "Expected the agent to return audio"
    assert "check_availability" in tool_calls, "Expected an availability check"
