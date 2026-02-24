"""
Voice API — Nova 2 Sonic real-time speech-to-speech.

Two endpoints:
  POST /api/voice/chat     — text-in / text-out (Nova Lite fallback)
  WS   /ws/sonic           — real-time audio-in / audio+text-out (Nova 2 Sonic)
  WS   /ws/voice           — legacy text WebSocket (kept for compatibility)

Nova Sonic WebSocket protocol
  Browser → Backend:
    Binary frames  : raw PCM 16-bit mono 16 kHz audio chunks
    Text "end"     : signals end of speech turn

  Backend → Browser:
    {"type":"text",   "content":"transcript or response text"}
    {"type":"audio",  "content":"<base64 PCM 24kHz>"}
    {"type":"error",  "content":"error message"}
    {"type":"status", "content":"connected|processing|done"}
"""

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.agents.voice_agent import VoiceAgent
from app.agents.nova_sonic_agent import NovaSonicSession

logger = logging.getLogger(__name__)
router = APIRouter(tags=["voice"])


# ─── REST fallback (Nova Lite) ────────────────────────────────────────────────

class VoiceRequest(BaseModel):
    text: str
    conversation_history: Optional[list[dict]] = None


class VoiceResponse(BaseModel):
    spoken_response: str
    severity: Optional[str]
    osha_code: Optional[str]
    original_text: str
    is_violation: bool


@router.post("/api/voice/chat", response_model=VoiceResponse)
def voice_chat(req: VoiceRequest):
    """Text-in / text-out via Nova Lite (fallback when mic unavailable)."""
    agent = VoiceAgent()
    result = agent.process_observation(req.text, req.conversation_history)
    return result


# ─── Nova 2 Sonic real-time WebSocket ────────────────────────────────────────

@router.websocket("/ws/sonic")
async def nova_sonic_websocket(websocket: WebSocket):
    """
    Real-time bidirectional voice session using Amazon Nova 2 Sonic.

    Flow per turn:
      1. Browser streams PCM audio chunks as binary frames.
      2. Browser sends text "end" when done speaking.
      3. Backend pipes audio to Nova Sonic via bidirectional Bedrock stream.
      4. Nova Sonic returns text transcript + audio response chunks.
      5. Backend forwards both to browser in real time.
      6. Browser plays audio and displays transcript.
    """
    await websocket.accept()
    logger.info("Nova Sonic WebSocket connected")

    async def send_json(data: dict):
        await websocket.send_text(json.dumps(data))

    await send_json({"type": "status", "content": "connected"})

    try:
        while True:
            audio_queue: asyncio.Queue = asyncio.Queue()

            # ── Collect audio from browser until "end" ────────────────────
            async def collect_audio():
                chunk_count = 0
                while True:
                    message = await websocket.receive()

                    if message["type"] == "websocket.disconnect":
                        await audio_queue.put(None)
                        return

                    if "bytes" in message and message["bytes"]:
                        await audio_queue.put(message["bytes"])
                        chunk_count += 1

                    elif "text" in message and message["text"].strip().lower() == "end":
                        logger.info(f"Turn: received {chunk_count} audio chunks")
                        await audio_queue.put(None)  # close signal for Nova Sonic
                        return

            collect_task = asyncio.create_task(collect_audio())
            await send_json({"type": "status", "content": "processing"})

            # ── Stream to Nova Sonic and forward responses ────────────────
            session = NovaSonicSession()
            try:
                async for event in session.run(audio_queue):
                    await send_json(event)
            except Exception as e:
                logger.error(f"Nova Sonic stream error: {e}", exc_info=True)
                await send_json({"type": "error", "content": str(e)})

            await send_json({"type": "status", "content": "done"})
            await collect_task

    except WebSocketDisconnect:
        logger.info("Nova Sonic WebSocket disconnected")
    except Exception as e:
        logger.error(f"Nova Sonic WebSocket fatal error: {e}", exc_info=True)
        try:
            await send_json({"type": "error", "content": str(e)})
        except Exception:
            pass


# ─── Legacy text WebSocket (Nova Lite) ───────────────────────────────────────

@router.websocket("/ws/voice")
async def voice_text_websocket(websocket: WebSocket):
    """
    Text-based WebSocket using Nova Lite.
    Used as fallback for browsers that cannot capture raw PCM.
    Client sends: {"text": "I see a worker without a hard hat"}
    Server sends: {"spoken_response": "...", "severity": "HIGH", ...}
    """
    await websocket.accept()
    agent = VoiceAgent()
    history: list[dict] = []
    logger.info("Legacy text voice WebSocket connected")

    try:
        while True:
            raw  = await websocket.receive_text()
            data = json.loads(raw)
            text = data.get("text", "").strip()
            if not text:
                continue

            try:
                result = agent.process_observation(text, history)
                history.append({"role": "user",      "content": [{"text": text}]})
                history.append({"role": "assistant",  "content": [{"text": result["spoken_response"]}]})
                history = history[-10:]
                await websocket.send_text(json.dumps(result))
            except Exception as e:
                logger.error(f"Voice text error: {e}")
                await websocket.send_text(json.dumps({
                    "spoken_response": "Error processing that. Please try again.",
                    "severity": None, "osha_code": None,
                    "original_text": text, "is_violation": False,
                }))

    except WebSocketDisconnect:
        logger.info("Legacy voice WebSocket disconnected")
