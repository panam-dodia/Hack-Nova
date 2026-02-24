"""
Nova Act — Automatic Ticket Filer
Uses Amazon Nova Act to open your ticketing system (ServiceNow, Procore, Jira, or a
generic web form) and file one ticket per safety violation — no manual copy-paste.

Usage:
    python ticket_filer.py --inspection-id <id> --system servicenow
    python ticket_filer.py --inspection-id <id> --system demo

Requirements:
    pip install amazon-nova-act requests python-dotenv

Getting Nova Act access:
    Sign up at https://nova-act.amazonaws.com (research preview)
    Set NOVA_ACT_API_KEY in your .env file
"""

import os
import sys
import json
import argparse
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger(__name__)

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
NOVA_ACT_API_KEY = os.getenv("NOVA_ACT_API_KEY", "")

# ─── Target system configurations ────────────────────────────────────────────

SYSTEM_CONFIGS = {
    "servicenow": {
        "url": os.getenv("SERVICENOW_URL", "https://yourinstance.service-now.com"),
        "username": os.getenv("SERVICENOW_USER", ""),
        "password": os.getenv("SERVICENOW_PASS", ""),
    },
    "procore": {
        "url": os.getenv("PROCORE_URL", "https://app.procore.com"),
        "username": os.getenv("PROCORE_USER", ""),
        "password": os.getenv("PROCORE_PASS", ""),
    },
    "jira": {
        "url": os.getenv("JIRA_URL", "https://yourcompany.atlassian.net"),
        "username": os.getenv("JIRA_USER", ""),
        "password": os.getenv("JIRA_PASS", ""),
    },
}

SEVERITY_PRIORITY = {
    "CRITICAL": "1 - Critical",
    "HIGH": "2 - High",
    "MEDIUM": "3 - Medium",
    "LOW": "4 - Low",
}


# ─── Fetch violations from the backend ───────────────────────────────────────

def fetch_inspection(inspection_id: str) -> dict:
    resp = requests.get(f"{BACKEND_URL}/api/inspections/{inspection_id}", timeout=30)
    resp.raise_for_status()
    return resp.json()


def update_violation_ticket(inspection_id: str, violation_id: str, ticket_id: str, ticket_url: str = ""):
    requests.patch(
        f"{BACKEND_URL}/api/inspections/{inspection_id}/violations/{violation_id}",
        json={"ticket_id": ticket_id, "ticket_url": ticket_url, "status": "in_progress"},
        timeout=10,
    )


# ─── Nova Act filing ──────────────────────────────────────────────────────────

def file_with_nova_act(violation: dict, system: str, config: dict) -> dict:
    """
    Uses Amazon Nova Act to automate browser-based ticket filing.
    Nova Act lets you control a browser with natural language instructions.
    """
    try:
        from nova_act import NovaAct  # pip install amazon-nova-act
    except ImportError:
        logger.error("amazon-nova-act not installed. Run: pip install amazon-nova-act")
        return {"success": False, "error": "nova-act not installed"}

    title = f"[{violation.get('severity', 'UNKNOWN')}] {violation.get('osha_code', 'OSHA')} — {violation.get('osha_title', 'Safety Violation')}"
    description = f"""SAFETY VIOLATION — AUTO-FILED BY SafetyAI

Site: {violation.get('site_name', 'Unknown site')}
OSHA Regulation: {violation.get('osha_code', 'N/A')} — {violation.get('osha_title', 'N/A')}
Severity: {violation.get('severity', 'N/A')}
Detected: {datetime.now().strftime('%Y-%m-%d %H:%M')}

WHAT WAS OBSERVED:
{violation.get('raw_observation', 'See attached inspection report')}

PLAIN ENGLISH:
{violation.get('plain_english', 'N/A')}

REMEDIATION REQUIRED:
{violation.get('remediation', 'See OSHA guidelines')}

ESTIMATED FIX TIME: {violation.get('estimated_fix_time', 'TBD')}

Filed automatically by SafetyAI — Amazon Nova Hackathon
"""

    if system == "servicenow":
        instructions = [
            f"Navigate to {config['url']}/now/nav/ui/classic/params/target/incident.do%3Fsys_id%3D-1%26sysparm_query%3Dactive%3Dtrue",
            f"Log in with username '{config['username']}' and password '{config['password']}'",
            f"Set the Short Description to: {title}",
            f"Set the Description to: {description}",
            f"Set the Priority to: {SEVERITY_PRIORITY.get(violation.get('severity', 'LOW'), '3 - Medium')}",
            "Set the Category to: Facilities/Safety",
            "Click the Submit button",
            "Return the incident number from the confirmation",
        ]
    elif system == "jira":
        instructions = [
            f"Go to {config['url']}/jira/software/projects/SAFETY/boards",
            f"Log in with '{config['username']}' and '{config['password']}'",
            "Click 'Create Issue'",
            f"Set Summary to: {title}",
            f"Set Description to: {description}",
            f"Set Priority to: {violation.get('severity', 'LOW').capitalize()}",
            "Set Issue Type to: Bug or Task",
            "Submit the issue",
            "Return the issue key (e.g., SAFETY-123)",
        ]
    else:
        logger.warning(f"Unknown system '{system}' for Nova Act. Add configuration in SYSTEM_CONFIGS.")
        return {"success": False, "error": f"Unsupported system: {system}"}

    try:
        ticket_id = None
        ticket_url = ""

        with NovaAct(
            starting_page=config["url"],
            nova_act_api_key=NOVA_ACT_API_KEY,
        ) as agent:
            for instruction in instructions:
                result = agent.act(instruction)
                logger.debug(f"Nova Act step: {instruction[:60]}... → {result}")

            # Extract ticket ID from the last result
            final_result = agent.act(
                "What is the ticket/incident number that was just created? Return just the ID."
            )
            if final_result and hasattr(final_result, 'response'):
                ticket_id = str(final_result.response).strip()
                ticket_url = f"{config['url']}/ticket/{ticket_id}"

        return {"success": True, "ticket_id": ticket_id, "ticket_url": ticket_url}

    except Exception as e:
        logger.error(f"Nova Act error: {e}")
        return {"success": False, "error": str(e)}


def file_demo_ticket(violation: dict, idx: int) -> dict:
    """
    Demo mode — simulates ticket filing without a real ticketing system.
    Shows exactly what Nova Act WOULD file.
    """
    ticket_id = f"DEMO-{1000 + idx}"
    print(f"\n{'─' * 60}")
    print(f"  TICKET #{ticket_id}")
    print(f"  Title : [{violation.get('severity')}] {violation.get('osha_code')} — {violation.get('osha_title')}")
    print(f"  Body  : {violation.get('plain_english', '')[:120]}...")
    print(f"  Fix   : {violation.get('estimated_fix_time', 'TBD')}")
    print(f"  Status: IN PROGRESS")
    print(f"{'─' * 60}")
    return {"success": True, "ticket_id": ticket_id, "ticket_url": f"https://demo.tickets.local/{ticket_id}"}


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Nova Act — SafetyAI Ticket Filer")
    parser.add_argument("--inspection-id", required=True, help="Inspection ID from SafetyAI")
    parser.add_argument(
        "--system",
        default="demo",
        choices=["demo", "servicenow", "procore", "jira"],
        help="Target ticketing system",
    )
    parser.add_argument(
        "--severity-filter",
        default="ALL",
        choices=["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"],
        help="Only file tickets for violations at or above this severity",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print tickets without filing")
    args = parser.parse_args()

    logger.info(f"Fetching inspection {args.inspection_id} from SafetyAI backend")
    inspection = fetch_inspection(args.inspection_id)

    if inspection.get("status") != "completed":
        logger.error(f"Inspection status is '{inspection.get('status')}' — must be 'completed' to file tickets")
        sys.exit(1)

    violations = inspection.get("violations", [])
    severity_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    if args.severity_filter != "ALL":
        cutoff = severity_order.index(args.severity_filter)
        violations = [v for v in violations if severity_order.index(v.get("severity", "LOW")) <= cutoff]

    # Only file open violations
    violations = [v for v in violations if v.get("status") == "open"]

    logger.info(f"Found {len(violations)} open violations to file as tickets")

    if args.dry_run:
        for i, v in enumerate(violations):
            print(json.dumps({
                "would_file": f"#{i + 1}",
                "title": f"[{v.get('severity')}] {v.get('osha_code')} — {v.get('osha_title')}",
                "severity": v.get("severity"),
            }, indent=2))
        return

    config = SYSTEM_CONFIGS.get(args.system, {})
    results = []

    for idx, violation in enumerate(violations):
        logger.info(
            f"Filing ticket {idx + 1}/{len(violations)}: {violation.get('osha_code')} [{violation.get('severity')}]"
        )
        # Attach site name for richer ticket description
        violation["site_name"] = inspection.get("site_name", "Unknown")

        if args.system == "demo":
            result = file_demo_ticket(violation, idx)
        else:
            result = file_with_nova_act(violation, args.system, config)

        results.append(result)

        if result.get("success"):
            update_violation_ticket(
                args.inspection_id,
                violation["id"],
                result["ticket_id"],
                result.get("ticket_url", ""),
            )
            logger.info(f"  ✓ Ticket filed: {result['ticket_id']}")
        else:
            logger.warning(f"  ✗ Failed: {result.get('error')}")

    filed = sum(1 for r in results if r.get("success"))
    print(f"\nDone. Filed {filed}/{len(violations)} tickets in {args.system}.")


if __name__ == "__main__":
    main()
