"""
Agent 4 — Voice Assistant (Amazon Nova Lite)
Real-time hands-free safety guidance for on-site inspectors.
Inspector speaks a description; agent classifies it and gives immediate guidance.
"""
import json
import logging

import boto3
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)

VOICE_SYSTEM_PROMPT = """You are SafetyAI, a real-time voice assistant for construction site inspectors.
An inspector is walking the site hands-free and describing what they see.

Your job:
1. Instantly classify each observation as a safety violation (or confirm it's safe)
2. Identify the OSHA code
3. Give a severity rating
4. Respond in short, clear spoken language (this will be read aloud)

Keep responses under 3 sentences. Be direct and actionable.
Always end with the severity: "Severity: CRITICAL / HIGH / MEDIUM / LOW"

Example:
Inspector says: "I see a worker on the scaffolding without a harness"
You respond: "Fall protection violation — OSHA 1926.502. Worker must stop work immediately and be fitted with a full-body harness and lanyard before returning to height. Severity: CRITICAL"
"""


class VoiceAgent:
    def __init__(self):
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )
        self.model_id = settings.nova_lite_model_id

    def process_observation(self, inspector_text: str, conversation_history: list[dict] = None) -> dict:
        """
        Process a voice observation from the inspector.
        Returns spoken response + structured violation data.
        """
        messages = []

        # Include conversation history for context
        if conversation_history:
            messages.extend(conversation_history[-6:])  # last 3 exchanges

        messages.append({
            "role": "user",
            "content": [{"text": f"{VOICE_SYSTEM_PROMPT}\n\nInspector says: {inspector_text}"}],
        })

        request_body = {
            "messages": messages,
            "inferenceConfig": {"maxTokens": 512, "temperature": 0.1},
        }

        try:
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body),
                contentType="application/json",
                accept="application/json",
            )
            response_body = json.loads(response["body"].read())
            spoken_response = response_body["output"]["message"]["content"][0]["text"]

            # Parse severity from response
            severity = self._extract_severity(spoken_response)
            osha_code = self._extract_osha_code(spoken_response)

            return {
                "spoken_response": spoken_response,
                "severity": severity,
                "osha_code": osha_code,
                "original_text": inspector_text,
                "is_violation": severity is not None,
            }

        except ClientError as e:
            logger.error(f"Bedrock voice error: {e}")
            raise

    @staticmethod
    def _extract_severity(text: str) -> str | None:
        text_upper = text.upper()
        for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            if sev in text_upper:
                return sev
        return None

    @staticmethod
    def _extract_osha_code(text: str) -> str | None:
        import re
        match = re.search(r"(29\s*CFR\s*)?(1926|1910)\.\d+", text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
        return None
