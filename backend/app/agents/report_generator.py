"""
Agent 3 — Report Generator (Amazon Nova Lite)
Synthesizes all violations into a professional inspection report with
an executive summary, prioritized action list, and compliance risk score.
"""
import json
import logging
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


class ReportGenerator:
    def __init__(self):
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )
        self.model_id = settings.nova_lite_model_id

    def generate_report(
        self,
        violations: list[dict],
        site_name: str,
        inspector_name: str,
        inspection_date: str,
    ) -> dict:
        """Generate a structured inspection report from mapped violations."""

        if not violations:
            return self._empty_report(site_name, inspector_name, inspection_date)

        # Sort by severity for the prompt
        sorted_violations = sorted(
            violations, key=lambda v: SEVERITY_ORDER.get(v.get("severity", "LOW"), 3)
        )

        violations_text = json.dumps(sorted_violations, indent=2)

        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for v in violations:
            sev = v.get("severity", "LOW")
            counts[sev] = counts.get(sev, 0) + 1

        prompt = f"""You are a senior safety compliance officer writing an official OSHA inspection report.

Site: {site_name}
Inspector: {inspector_name}
Date: {inspection_date}
Total violations: {len(violations)} (Critical: {counts['CRITICAL']}, High: {counts['HIGH']}, Medium: {counts['MEDIUM']}, Low: {counts['LOW']})

Violations found:
{violations_text}

Write a comprehensive inspection report. Return a JSON object with this exact structure:
{{
  "executive_summary": "2-3 paragraph professional summary of findings, overall risk level, and immediate actions required",
  "risk_score": 85,
  "risk_level": "HIGH",
  "risk_rationale": "Brief explanation of the risk score (0-100, where 100 is maximum danger)",
  "immediate_actions": [
    "Action that must happen TODAY (Critical/High items)",
    "..."
  ],
  "short_term_actions": [
    "Actions to complete within 7 days (Medium items)",
    "..."
  ],
  "long_term_actions": [
    "Actions to complete within 30 days (Low/systemic items)",
    "..."
  ],
  "compliance_status": "NON-COMPLIANT",
  "estimated_fine_exposure": "$5,000 - $15,000 per OSHA willful violation guidelines",
  "follow_up_inspection_recommended": true,
  "notes": "Any additional professional observations or patterns noticed"
}}

Risk score calculation: Start at 0. Add 25 per CRITICAL violation (max 100). Add 10 per HIGH. Add 5 per MEDIUM. Add 1 per LOW. Cap at 100.
Return ONLY the JSON object. No other text."""

        request_body = {
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": 3000, "temperature": 0.2},
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
            return self._parse_json_object(output_text)

        except ClientError as e:
            logger.error(f"Bedrock error generating report: {e}")
            raise

    @staticmethod
    def _parse_json_object(text: str) -> dict:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse error in report generator: {e}")
        return {}

    @staticmethod
    def _empty_report(site_name: str, inspector_name: str, inspection_date: str) -> dict:
        return {
            "executive_summary": f"Inspection of {site_name} on {inspection_date} by {inspector_name} found no safety violations. The site appears to be in compliance with OSHA regulations.",
            "risk_score": 0,
            "risk_level": "LOW",
            "risk_rationale": "No violations detected.",
            "immediate_actions": [],
            "short_term_actions": [],
            "long_term_actions": [],
            "compliance_status": "COMPLIANT",
            "estimated_fine_exposure": "$0",
            "follow_up_inspection_recommended": False,
            "notes": "Site passed inspection with no violations found.",
        }
