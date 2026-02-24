# SafetyAI — AI-Powered OSHA Inspection Platform

> Snap photos → AI finds violations → AI maps OSHA codes → AI files tickets

Built with **Amazon Nova Pro** (image analysis), **Nova Lite** (OSHA mapping + report), **Nova Lite** (voice assistant), and **Nova Act** (automated ticket filing) via Amazon Bedrock.

---

## Architecture

```
Browser / Mobile
      ↓
React + Vite (port 5173)
      ↓
FastAPI backend (port 8000)
      ↓
Amazon Bedrock
  ├── Nova Pro   → analyze photos for violations
  ├── Nova Lite  → map to OSHA codes + severity
  └── Nova Lite  → voice assistant + report gen
      ↓
Nova Act → file tickets in ServiceNow / Procore / Jira
      ↓
SQLite (dev) / PostgreSQL (prod)
```

---

## One-Time Setup

### 1. AWS Prerequisites (manual steps)

1. Sign into [AWS Console](https://console.aws.amazon.com) → go to **IAM**
2. Create a user or role → attach **`AmazonBedrockFullAccess`**
3. Under that user → **Security credentials** → create an **Access key**
4. Save the Access Key ID and Secret Access Key

> **Note:** Nova models (Nova Pro, Nova Lite) are automatically available on first invocation — no manual model access request needed.

### 2. Backend setup

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate       # Mac/Linux
# .venv\Scripts\activate        # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Open .env and fill in:
#   AWS_ACCESS_KEY_ID=...
#   AWS_SECRET_ACCESS_KEY=...
#   AWS_REGION=us-east-1

# Start the server
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend setup

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

### 4. (Optional) Nova Act ticket filer

```bash
cd nova-act
pip install -r requirements.txt

# Add to backend/.env:
#   NOVA_ACT_API_KEY=your_key
#   SERVICENOW_URL=https://yourinstance.service-now.com
#   SERVICENOW_USER=admin
#   SERVICENOW_PASS=password

# Demo mode (no real ticketing system needed):
python ticket_filer.py --inspection-id <id> --system demo

# File real tickets:
python ticket_filer.py --inspection-id <id> --system servicenow
```

---

## Usage Flow

1. Open `http://localhost:5173`
2. Click **New Inspection**
3. Enter site name and drag-drop construction site photos
4. Click **Run AI Inspection**
5. Watch the dashboard — status changes: `uploading → analyzing → completed`
6. Click the inspection to see every violation with its OSHA code and remediation steps
7. View the **Full Report** tab for risk score, executive summary, and fines exposure
8. Click the **Mic** button in the navbar for hands-free voice mode

---

## Environment Variables Reference

| Variable | Description | Default |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | IAM access key | — |
| `AWS_SECRET_ACCESS_KEY` | IAM secret key | — |
| `AWS_REGION` | Bedrock region | `us-east-1` |
| `DATABASE_URL` | SQLAlchemy URL | `sqlite:///./safety_inspector.db` |
| `NOVA_PRO_MODEL_ID` | Nova Pro model ID | `amazon.nova-pro-v1:0` |
| `NOVA_LITE_MODEL_ID` | Nova Lite model ID | `amazon.nova-lite-v1:0` |
| `NOVA_ACT_API_KEY` | Nova Act API key | — |
| `CORS_ORIGINS` | Allowed frontend origins | `http://localhost:5173` |

---

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── image_analyzer.py   ← Nova Pro: scans photos
│   │   │   ├── osha_mapper.py      ← Nova Lite: maps OSHA codes
│   │   │   ├── report_generator.py ← Nova Lite: writes report
│   │   │   └── voice_agent.py      ← Nova Lite: voice assistant
│   │   ├── api/
│   │   │   ├── inspections.py      ← upload + analysis pipeline
│   │   │   └── voice.py            ← REST + WebSocket voice
│   │   ├── main.py
│   │   ├── models.py
│   │   └── database.py
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Dashboard.tsx
│       │   ├── NewInspection.tsx
│       │   └── InspectionDetail.tsx
│       └── components/
│           ├── ViolationCard.tsx
│           ├── UploadZone.tsx
│           └── VoiceAssistant.tsx
└── nova-act/
    └── ticket_filer.py             ← Nova Act browser automation
```
