"""
Amazon Nova 2 Sonic — Real-time bidirectional speech-to-speech agent.

Architecture:
  Browser mic (PCM 16kHz) → WebSocket → this agent → Bedrock Nova Sonic
  Nova Sonic (PCM 24kHz)  → this agent → WebSocket → Browser speaker

The bidirectional stream runs in a thread-pool executor so it doesn't
block the async FastAPI event loop.  Two asyncio Queues bridge the async
WebSocket world with the synchronous boto3 stream.

Audio specs:
  Input  : PCM 16-bit mono 16 kHz (browser captures and sends this)
  Output : PCM 16-bit mono 24 kHz base64-encoded (Nova Sonic returns this)
"""

import asyncio
import base64
import json
import logging
import queue
import uuid
from typing import AsyncGenerator

import boto3
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)

INPUT_SAMPLE_RATE  = 16000   # Hz — browser sends this
OUTPUT_SAMPLE_RATE = 24000   # Hz — Nova Sonic returns this

SAFETY_SYSTEM_PROMPT = """You are SafetyAI, a real-time voice assistant for construction site safety inspectors.
An inspector is walking the site hands-free and describing what they observe out loud.

Your role:
- Instantly classify each observation as a safety violation or safe condition
- State the OSHA regulation code if it's a violation
- Give the severity (CRITICAL, HIGH, MEDIUM, or LOW)
- Respond in 1-3 SHORT spoken sentences — this is read aloud in real time

Be direct, professional, and conversational. Do not use lists or bullet points.

Example:
Inspector: "I can see a worker on the scaffold without a harness"
You: "Fall protection violation under OSHA 1926.502. Worker must stop immediately and be fitted with a full-body harness before returning to height. Severity: CRITICAL."
"""


class NovaSonicSession:
    """
    Manages one real-time voice session with Amazon Nova Sonic.

    Usage:
        session = NovaSonicSession()
        async for event in session.run(audio_in_queue):
            if event["type"] == "audio":
                # send base64 PCM audio back to browser
            elif event["type"] == "text":
                # send transcript to browser
    """

    MODEL_ID = "amazon.nova-sonic-v1:0"

    def __init__(self):
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )
        self._prompt_name  = str(uuid.uuid4())
        self._content_name = str(uuid.uuid4())

    # ─── Input event builders ─────────────────────────────────────────────────

    def _session_start(self) -> str:
        return json.dumps({
            "event": {
                "sessionStart": {
                    "inferenceConfiguration": {
                        "maxTokens": 1024,
                        "topP": 0.9,
                        "temperature": 0.7,
                    },
                    "turnDetectionConfiguration": {
                        "endpointingSensitivity": "MEDIUM"
                    },
                }
            }
        })

    def _prompt_start(self) -> str:
        return json.dumps({
            "event": {
                "promptStart": {
                    "promptName": self._prompt_name,
                    "systemPrompt": SAFETY_SYSTEM_PROMPT,
                    "textOutputConfiguration": {
                        "mediaType": "text/plain"
                    },
                    "audioOutputConfiguration": {
                        "mediaType":       "audio/lpcm",
                        "sampleRateHertz": OUTPUT_SAMPLE_RATE,
                        "sampleSizeBits":  16,
                        "channelCount":    1,
                        "voiceId":         "matthew",
                        "encoding":        "base64",
                        "audioType":       "SPEECH",
                    },
                }
            }
        })

    def _content_block_start(self) -> str:
        return json.dumps({
            "event": {
                "contentBlockStart": {
                    "promptName":  self._prompt_name,
                    "contentName": self._content_name,
                }
            }
        })

    def _audio_input(self, pcm_bytes: bytes) -> str:
        return json.dumps({
            "event": {
                "audioInput": {
                    "promptName":  self._prompt_name,
                    "contentName": self._content_name,
                    "content":     base64.b64encode(pcm_bytes).decode("utf-8"),
                }
            }
        })

    def _content_block_end(self) -> str:
        return json.dumps({
            "event": {
                "contentBlockEnd": {
                    "promptName":  self._prompt_name,
                    "contentName": self._content_name,
                }
            }
        })

    def _prompt_end(self) -> str:
        return json.dumps({
            "event": {
                "promptEnd": {
                    "promptName": self._prompt_name
                }
            }
        })

    def _session_end(self) -> str:
        return json.dumps({"event": {"sessionEnd": {}}})

    # ─── Core streaming ───────────────────────────────────────────────────────

    def _make_input_stream(self, sync_q: "queue.Queue[bytes | None]"):
        """
        Synchronous generator of input events.
        Runs inside a thread-pool executor — blocking .get() is fine here.
        """
        yield self._session_start()
        yield self._prompt_start()
        yield self._content_block_start()

        while True:
            chunk = sync_q.get(timeout=60)   # wait up to 60s for audio
            if chunk is None:
                break
            yield self._audio_input(chunk)

        yield self._content_block_end()
        yield self._prompt_end()
        yield self._session_end()

    def _run_bedrock_stream(
        self,
        sync_audio_q: "queue.Queue[bytes | None]",
        output_q: "asyncio.Queue",
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        """
        Runs synchronously in a thread-pool executor.
        Calls Nova Sonic via bidirectional stream and feeds results into output_q.
        """
        def put(event: dict):
            loop.call_soon_threadsafe(output_q.put_nowait, event)

        try:
            response = self._client.invoke_model_with_bidirectional_stream(
                modelId=self.MODEL_ID,
                body=self._make_input_stream(sync_audio_q),
            )
            for raw_event in response["body"]:
                ev = raw_event.get("event", {})

                if "textOutput" in ev:
                    put({"type": "text", "content": ev["textOutput"]["content"]})

                elif "audioOutput" in ev:
                    put({"type": "audio", "content": ev["audioOutput"]["content"]})

                elif "error" in ev:
                    logger.error(f"Nova Sonic error event: {ev['error']}")
                    put({"type": "error", "content": str(ev["error"])})

        except ClientError as e:
            logger.error(f"Bedrock ClientError in Nova Sonic stream: {e}")
            put({"type": "error", "content": str(e)})
        except Exception as e:
            logger.error(f"Unexpected error in Nova Sonic stream: {e}", exc_info=True)
            put({"type": "error", "content": str(e)})
        finally:
            put(None)   # sentinel — stream is done

    async def run(
        self, audio_in: "asyncio.Queue[bytes | None]"
    ) -> AsyncGenerator[dict, None]:
        """
        Async generator.  Feed audio chunks into audio_in, receive response events.

        audio_in items:
            bytes  — PCM 16-bit mono 16 kHz chunk
            None   — signals end of audio (closes the stream)

        Yields dicts:
            {"type": "text",  "content": "transcript text"}
            {"type": "audio", "content": "<base64 PCM 24kHz>"}
            {"type": "error", "content": "error message"}
        """
        loop       = asyncio.get_running_loop()
        output_q   = asyncio.Queue()
        sync_audio = queue.Queue()

        # Bridge asyncio → sync queue for the thread-pool executor
        async def drain_audio():
            while True:
                chunk = await audio_in.get()
                sync_audio.put(chunk)
                if chunk is None:
                    break

        drain_task   = asyncio.create_task(drain_audio())
        stream_future = loop.run_in_executor(
            None, self._run_bedrock_stream, sync_audio, output_q, loop
        )

        while True:
            event = await output_q.get()
            if event is None:
                break
            yield event

        await drain_task
        await stream_future
