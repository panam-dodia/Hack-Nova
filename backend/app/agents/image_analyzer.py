"""
Agent 1 — Image Analyzer (Amazon Nova Pro)
Looks at each photo like an experienced safety inspector and returns raw observations.
"""
import base64
import json
import logging
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png", ".gif": "gif", ".webp": "webp"}

INSPECTOR_PROMPT = """You are an expert OSHA construction site safety inspector with 20+ years of field experience.

Analyze this image and identify safety violations that are DIRECTLY AND VISIBLY present.

STRICT RULES — FOLLOW EXACTLY:
- Only report what is DIRECTLY AND CLEARLY VISIBLE. Never infer, assume, or speculate.
- For ANY PPE violation, the specific body part must be FULLY VISIBLE AND uncovered:
  * No hard hat → the worker's HEAD must be clearly in frame without a helmet
  * No gloves → the worker's HANDS must be clearly in frame without gloves
  * No boots → the worker's FEET must be clearly in frame without protection
  * No vest → the worker's TORSO must be clearly in frame without a high-vis vest
  * No goggles → the worker's FACE must be clearly in frame without eye protection
  * If a body part is not visible, out of frame, or obscured — do NOT report that PPE as missing.
- If no workers are present in the image, return [].
- If there is no active construction, industrial work, or physical labor visible, return [].
- If the scene is a clean campus, street, lobby, office, or public space, return [].
- Ask yourself: "Would a real OSHA inspector physically present write this up?" If no, skip it.

When workers and construction ARE clearly visible, look for:
- PPE violations (only for VISIBLE uncovered body parts — see rules above)
- Fall hazards (missing guardrails, unsecured scaffolding, unprotected floor openings, unsafe ladders)
- Fire/chemical hazards (improper storage, missing labels, flammable materials near ignition)
- Blocked emergency exits or evacuation routes
- Electrical hazards (exposed wiring, missing GFCI)
- Unstable or improperly stacked materials
- Equipment safety issues (missing guards, improper use)
- Housekeeping violations (debris, tripping hazards, wet floors with no sign)

Return your findings as a JSON array. Each item must follow this exact structure:
[
  {
    "observation": "Specific description of what you can SEE (not infer)",
    "location": "Where in the image (e.g., 'foreground left', 'background near scaffolding')",
    "hazard_type": "Category (PPE | Fall | Fire | Chemical | Electrical | Housekeeping | Equipment | Signage | Storage | Other)",
    "danger_description": "Why this is dangerous and what injury could result",
    "body_part_visible": true
  }
]

IMPORTANT: For PPE violations, set "body_part_visible" to true ONLY if the relevant body part
(head, hands, feet, torso, face) is clearly visible and uncovered in the image.
Set it to false if the body part is not in frame, obscured, or not clearly visible.

If you see NO violations, return: []
Return ONLY the JSON array. No preamble, no explanation outside the JSON."""


class ImageAnalyzer:
    def __init__(self):
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )
        self.model_id = settings.nova_pro_model_id

    def analyze_image(self, image_path: str) -> list[dict]:
        """Analyze a single image and return raw safety observations."""
        path = Path(image_path)
        ext = path.suffix.lower()
        image_format = SUPPORTED_FORMATS.get(ext, "jpeg")

        with open(image_path, "rb") as f:
            image_bytes = f.read()

        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

        request_body = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "image": {
                                "format": image_format,
                                "source": {"bytes": image_b64},
                            }
                        },
                        {"text": INSPECTOR_PROMPT},
                    ],
                }
            ],
            "inferenceConfig": {
                "maxTokens": 2048,
                "temperature": 0.1,
            },
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
            logger.error(f"Bedrock error analyzing {image_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error analyzing {image_path}: {e}")
            raise

    def analyze_multiple(self, image_paths: list[str]) -> list[dict]:
        """Analyze multiple images and combine all observations."""
        all_observations = []
        for idx, path in enumerate(image_paths):
            try:
                observations = self.analyze_image(path)
                for obs in observations:
                    obs["image_index"] = idx
                    obs["image_path"] = path
                all_observations.extend(observations)
                logger.info(f"Image {idx + 1}/{len(image_paths)}: found {len(observations)} issues")
            except Exception as e:
                logger.warning(f"Skipping image {path}: {e}")
        return all_observations

    @staticmethod
    def _parse_json_array(text: str) -> list:
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                raw = json.loads(text[start:end])
                return ImageAnalyzer._filter_observations(raw)
            except json.JSONDecodeError:
                logger.warning("Could not parse JSON from image analysis response")
        return []

    @staticmethod
    def _filter_observations(observations: list) -> list:
        """
        Hard enforcement filter — removes PPE violations where the body
        part cannot be confirmed visible in the observation text itself.

        The model cannot be trusted to set body_part_visible correctly
        (it hallucinates the flag too). So for high-hallucination PPE
        items we require the observation text to explicitly name the body
        part — if it doesn't, the violation is dropped regardless of what
        the model reported.
        """
        # Maps: PPE keyword → body-part words that MUST appear in observation text
        REQUIRE_BODY_PART_IN_TEXT = {
            "glove":          ["hand", "finger"],
            "boot":           ["foot", "feet", "ankle"],
            "shoe":           ["foot", "feet", "ankle"],
            "goggle":         ["eye", "face"],
            "eye protection": ["eye", "face"],
            "face shield":    ["eye", "face"],
            "hearing":        ["ear"],
        }

        filtered = []
        for obs in observations:
            hazard = obs.get("hazard_type", "").upper()
            obs_text = obs.get("observation", "").lower()
            body_part_visible = obs.get("body_part_visible", True)

            if hazard != "PPE":
                filtered.append(obs)
                continue

            # Model explicitly flagged the body part as not visible → drop
            if body_part_visible is False:
                logger.info(f"Dropped (body_part_visible=false): {obs_text[:70]}")
                continue

            # For high-hallucination PPE items: require the body part word
            # to appear in the observation text. If the model says
            # "worker not wearing gloves" without mentioning hands, it's guessing.
            drop = False
            for keyword, required_words in REQUIRE_BODY_PART_IN_TEXT.items():
                if keyword in obs_text:
                    if not any(w in obs_text for w in required_words):
                        logger.info(f"Dropped inferred PPE ({keyword}, body part not mentioned): {obs_text[:70]}")
                        drop = True
                        break

            if not drop:
                filtered.append(obs)

        removed = len(observations) - len(filtered)
        if removed:
            logger.info(f"Filtered {removed} hallucinated PPE violation(s) in post-processing")
        return filtered
