# Building a Voice-First Restaurant Booking Agent with ADK + Gemini Live

This guide walks through how this project went from the default `agents-cli` ADK scaffold (a text weather/time agent) to **Trattoria DevFest**, a voice agent that takes table reservations over a real-time, bidirectional audio stream.

What you end up with:

- **Gemini Live** (`gemini-3.8-live`), a native-audio model: you speak, it speaks back, with no separate speech-to-text or text-to-speech step.
- **BIDI streaming** over ADK's built-in `/run_live` WebSocket. You can interrupt it mid-sentence (barge-in).
- **Input and output transcription** on, so both sides of the call appear as text in the UI.
- Two tools, **`check_availability`** and **`create_booking`**, backed by an in-memory reservation book.
- The **ADK playground** (`agents-cli playground`), where you talk to the agent through your mic.

---

## 0. Prerequisites

- Python 3.11+ and [`uv`](https://docs.astral.sh/uv/)
- `agents-cli` (this project was generated with v1.11.0)
- **One** of these Gemini backends:
  - **AI Studio API key** (what this guide uses): a `GEMINI_API_KEY` from <https://aistudio.google.com/apikey>, on a project **with billing credits**.
  - **Gemini platform (Google Cloud)**: a GCP project with the API enabled, plus `gcloud auth application-default login`.

## 1. Start from the scaffold

The project was created with the standard ADK template:

```bash
agents-cli scaffold create devfest-agent --agent adk --deployment-target agent_runtime
cd devfest-agent
agents-cli install
```

There is **no Live-specific template**. You scaffold a normal ADK agent and convert it, as described below.

## 2. Point the agent at a Live model — `app/agent.py`

Live models are served from **regional** endpoints, not `global`. The model, region, and voice are read from environment variables so you can change them without touching code:

```python
MODEL = os.getenv("LIVE_MODEL", "gemini-3.8-live")
LIVE_LOCATION = os.getenv("LIVE_LOCATION", "us-central1")
VOICE = os.getenv("LIVE_VOICE", "Aoede")

root_agent = Agent(
    name="devfest_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
        # Pin the region on the model (Gemini platform only).
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
```

Why `client_kwargs` instead of `GOOGLE_CLOUD_LOCATION`? An explicit `location` on the model overrides the environment variable. That matters because `GOOGLE_CLOUD_LOCATION` is often `global`, which doesn't serve Live, and the same variable is shared with sessions and telemetry. **On AI Studio, `location` must be empty**: the Gemini API rejects it with `Gemini API does not support project/location`.

## 3. Add the booking tools

Both tools are plain Python functions. ADK turns the signature and docstring into the tool schema the model sees, so the docstrings matter.

| Tool | Inputs | Returns |
|---|---|---|
| `check_availability` | `date` (YYYY-MM-DD), `time` (HH:MM), `party_size` | `{"available": true, ...}`, or `{"available": false, "alternatives": ["18:30", "19:00", "20:30"]}`, or an `error` |
| `create_booking` | `name`, `date`, `time`, `party_size`, `phone` (+ `tool_context`) | `{"status": "confirmed", "booking_code": "BK-4821", ...}` or `{"status": "failed", ...}` |

Mock restaurant rules:

- Seatings every 30 minutes from **17:00 to 21:30**, 16 seats per slot, parties of 1–12.
- **19:30 and 20:00 are pre-booked** to nearly full, so the agent offers alternatives during a demo.
- `create_booking` re-checks availability before writing. This stops two callers from double-booking. It also saves the booking to session state as `last_booking`.

The tools return in microseconds, so they're plain synchronous functions. A slow real backend would warrant ADK's non-blocking tool pattern, so the agent can keep talking while the tool runs.

## 4. Write the instruction for the ear, not the eye

Most of a voice agent's quality comes from its instruction. The instruction is a function, so it can include today's date and the model can resolve "this Friday" on its own. It tells the model to:

- **Never use markdown, lists, emoji, or URLs**, because they'd be read aloud literally.
- Keep replies to **one or two sentences**, then ask one question.
- Say dates and times naturally, and read **codes and phone numbers digit by digit**.
- Say **"let me check that for you"** before calling a tool. Silence on a call sounds like a dropped line.
- **Read back every detail and wait for a clear "yes"** before `create_booking`, because speech recognition can mishear names and numbers.

## 5. Remove A2A — `app/fast_api_app.py`

The scaffold enables the A2A protocol, which is request/response only and has no Live transport. A Live agent can't be served over it. So:

- Removed `attach_a2a_routes` and its imports from `app/fast_api_app.py`.
- Deleted `app/app_utils/a2a.py`.
- `uv remove a2a-sdk`
- Set `is_a2a: false` in `agents-cli-manifest.yaml`, and removed the A2A Inspector and `publish gemini` sections from the README.

The `/run_live` WebSocket comes from ADK's `get_fast_api_app`, so **no server code was written** for streaming.

## 6. Transcription and streaming config

ADK's `RunConfig` enables both transcriptions by default, and the playground and `/run_live` keep those defaults:

```python
RunConfig(
    response_modalities=["AUDIO"],                                # native audio out
    input_audio_transcription=types.AudioTranscriptionConfig(),   # what you said
    output_audio_transcription=types.AudioTranscriptionConfig(),  # what it said
)
```

The integration test sets these explicitly so the intent is visible. Audio formats: **16 kHz 16-bit mono PCM in, 24 kHz out**.

## 7. Rewrite the tests for Live

A Live model **rejects** text-only requests. The scaffold's tests use `runner.run()` and `/run_sse`, so they have to be rewritten. Don't just delete them.

- `tests/unit/test_booking_tools.py` (**new**): open slot, full slot with alternatives, 7 kinds of invalid input, and a booking that uses up capacity. No network.
- `tests/integration/test_agent.py`: drives `Runner.run_live` with a `LiveRequestQueue`. It asserts that audio came back, that there's an output transcript, and that `check_availability` was called. It calls `load_dotenv()` **before** importing the agent, because pytest doesn't load `.env` itself.
- `tests/integration/test_server_e2e.py`: the readiness probe now polls `/list-apps`. The A2A, SSE, and reasoning-engine tests are replaced by `test_adk_run_live`, which creates a session over HTTP and then talks to `/run_live` over a WebSocket.

A gotcha in both live tests: a tool call produces an **extra `turn_complete`** before the spoken answer. Keep reading until there's a transcript, or you'll stop too early.

## 8. Configure `.env`

For AI Studio:

```dotenv
# GOOGLE_GENAI_USE_ENTERPRISE=true
# GOOGLE_CLOUD_PROJECT=...
# GOOGLE_CLOUD_LOCATION=global
GEMINI_API_KEY=your-key
LIVE_LOCATION=
```

For the Gemini platform, uncomment the three `GOOGLE_*` lines, set `LIVE_LOCATION=us-central1`, and run `gcloud auth application-default login`.

## 9. Run it

```bash
uv run pytest tests/unit                  # tool logic, offline
agents-cli lint                           # ruff, codespell, ty
agents-cli playground --port 8501         # start the dev UI
```

Open <http://127.0.0.1:8501>. In Codespaces, open the forwarded port 8501. Pick the **`app`** agent, click the **microphone**, and talk.

Try this conversation:

1. "Hi, I'd like a table for four this Friday at seven thirty."
   The agent should check, then say 7:30 is full and offer 7:00, 8:30, and so on.
2. "Seven is fine."
   It asks for your name and phone number.
3. Give them. It reads everything back.
4. "Yes."
   It books and reads your `BK-` code digit by digit.

Open the **Events** panel to watch the `check_availability` and `create_booking` calls, and the transcripts for both sides.

To script a turn without a mic, against the running playground:

```bash
agents-cli run "Do you have a table for 4 this Friday at 8pm?" \
  --mode adk_live --url http://127.0.0.1:8501
```

And the full live test suite:

```bash
uv run pytest tests/integration
```

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `1011 ... Your prepayment credits are depleted` | The AI Studio project has no billing credits. | Top up at <https://ai.studio/projects>, or switch to the Gemini platform. |
| `ValueError: Gemini API does not support project/location` | `LIVE_LOCATION` is set while using an AI Studio key, or `.env` wasn't loaded and the client fell back to the Gemini API. | Set `LIVE_LOCATION=` (empty) for AI Studio. Make sure `.env` loads before the agent is imported. |
| `DefaultCredentialsError` | Gemini platform selected without Application Default Credentials. | `gcloud auth application-default login`, or use an AI Studio key. |
| Model or region not found on the Gemini platform | `LIVE_LOCATION` is `global`, or a region that doesn't serve the model. | Use a regional endpoint such as `us-central1`; check the model × region matrix. |
| Test ends with no answer | It stopped at the `turn_complete` from the tool call. | Keep reading until a transcript arrives. |
| Agent reads out "asterisk" or "bullet" | The instruction lets formatting through. | Ban formatting explicitly in the instruction. |

## Status of this build

| Check | Result |
|---|---|
| Unit tests (`tests/unit`) | ✅ 11 passed |
| `agents-cli lint` | ✅ all checks passed |
| Playground server | ✅ running on port 8501, `app` listed |
| Live connection | ⚠️ Connection and model are accepted; Google closes the session with *"prepayment credits are depleted"*. Works once AI Studio billing is topped up. |

## Not covered here

- Deploying: `agents-cli deploy`. The deploy target is Agent Runtime. If you deploy to Cloud Run instead, use `--timeout 3600` so a call can last longer than 5 minutes.
- A real reservation backend: replace `_BOOKINGS` with a database or booking API. Use ADK's non-blocking tools if it's slow.
- `agents-cli publish gemini` doesn't apply: Gemini has no way to talk to a Live agent.
