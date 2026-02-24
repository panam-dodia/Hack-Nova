"""
Agent 2 — OSHA Mapper (Amazon Nova Lite)
Takes raw observations and maps each one to the exact OSHA regulation,
severity level, and plain-English remediation guidance.
"""
import json
import logging

import boto3
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a certified OSHA compliance specialist for the construction industry.
Map raw safety observations to specific OSHA 29 CFR regulations with precision.

Key regulations to reference:
29 CFR 1926.20  — General safety and health provisions
29 CFR 1926.25  — Housekeeping
29 CFR 1926.28  — Personal protective equipment (general)
29 CFR 1926.95  — PPE criteria and use
29 CFR 1926.100 — Head protection (hard hats)
29 CFR 1926.101 — Hearing protection
29 CFR 1926.102 — Eye and face protection
29 CFR 1926.150 — Fire protection
29 CFR 1926.151 — Fire prevention
29 CFR 1926.152 — Flammable and combustible liquids
29 CFR 1926.200 — Accident prevention signs and tags
29 CFR 1926.250 — General requirements for storage
29 CFR 1926.300 — General requirements for tools
29 CFR 1926.350 — Gas welding and cutting
29 CFR 1926.403 — Electrical — general requirements
29 CFR 1926.404 — Wiring design and protection
29 CFR 1926.416 — General requirements (electrical safety)
29 CFR 1926.451 — General requirements (scaffolding)
29 CFR 1926.452 — Additional requirements for specific scaffolds
29 CFR 1926.502 — Fall protection systems criteria
29 CFR 1926.503 — Training requirements (fall protection)
29 CFR 1926.1053 — Ladders
29 CFR 1910.37  — Maintenance, safeguards, and operational features for exit routes
29 CFR 1910.157 — Portable fire extinguishers
29 CFR 1910.1200 — Hazard communication (chemicals/SDS)

Severity definitions:
CRITICAL — Imminent danger; worker death or permanent disability likely within hours. Stop work order warranted.
HIGH     — Serious hazard; injury likely within days without correction.
MEDIUM   — Significant violation; injury possible but not imminent.
LOW      — Minor or administrative violation; low injury probability."""


class OSHAMapper:
    def __init__(self):
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )
        self.model_id = settings.nova_lite_model_id

    def map_violations(self, observations: list[dict]) -> list[dict]:
        """Map raw observations to OSHA codes with severity and remediation."""
        if not observations:
            return []

        obs_text = json.dumps(observations, indent=2)

        prompt = f"""{SYSTEM_PROMPT}

Raw safety observations from a construction site inspection:

{obs_text}

For EACH observation, produce one JSON object. Return a JSON array:
[
  {{
    "observation_index": 0,
    "original_observation": "exact text from the observation field",
    "hazard_type": "category from the observation",
    "image_index": 0,
    "osha_code": "29 CFR 1926.100",
    "osha_title": "Head Protection",
    "severity": "HIGH",
    "plain_english": "A worker is not wearing a hard hat. Hard hats protect against falling objects and overhead strikes that can cause fatal skull fractures.",
    "remediation": "1. Stop the worker immediately and provide a hard hat from site supply.\\n2. Document the violation with photos and worker ID.\\n3. Issue a written warning per company policy.\\n4. Schedule a PPE refresher training within 5 days.",
    "estimated_fix_time": "Immediate — 15 minutes"
  }}
]

Return ONLY the JSON array. No other text."""

        request_body = {
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": 4096, "temperature": 0.1},
        }

        try:
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body),
                contentType="application/json",
                accept="application/json",
            )
            response_body = json.loads(response["body"].read())
            output_text = response_body["output"]["message"]["content"][0]["text"]
            return self._parse_json_array(output_text)

        except ClientError as e:
            logger.error(f"Bedrock error in OSHA mapping: {e}")
            raise

    @staticmethod
    def _parse_json_array(text: str) -> list:
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse error in OSHA mapper: {e}")
        return []
