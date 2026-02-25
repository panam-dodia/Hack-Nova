# Real-Time Safety Monitoring System

## Overview

The Live Monitor transforms SafetyAI from a **post-inspection analysis tool** into a **real-time safety surveillance system** by processing videos frame-by-frame to simulate CCTV monitoring.

## How It Works

### Architecture

```
Uploaded Video (simulates CCTV feed)
    ↓
Frame Extraction (every 1.5 seconds)
    ↓
Amazon Nova Pro (multimodal vision analysis)
    ↓
Amazon Nova 2 Lite (OSHA regulation mapping)
    ↓
Deduplication Engine (5-minute cooldown)
    ↓
WebSocket Broadcast → Live Dashboard
    ↓
Auto-Ticket Filing (Nova Act - for CRITICAL/HIGH)
```

### Key Features

1. **Frame-by-Frame Analysis**
   - Processes 1 frame every 1.5 seconds (configurable)
   - Extracts frames using OpenCV
   - Each frame analyzed by Nova Pro for violations

2. **Smart Deduplication**
   - Prevents duplicate alerts for the same violation
   - 5-minute cooldown period per violation type + location
   - Tracks: (hazard_type, location) → last_seen_timestamp

3. **Evidence Collection**
   - Saves screenshot of each violation frame
   - Extracts 30-second video clip (15s before, 15s after)
   - Stored in `uploads/monitoring/{session_id}/`

4. **Real-Time Alerts**
   - **WebSocket** live updates to frontend
   - **Audio notification** (800 Hz beep)
   - **Browser notifications** (if permitted)
   - **Visual pulse animation** for new violations

5. **Auto-Ticket Filing**
   - Automatically triggers for CRITICAL/HIGH violations
   - Integrates with Nova Act (demo mode included)
   - Updates violation status to "in_progress"
   - Generates ticket IDs: `SAFETY-{session}-{violation}`

## Usage

### Step 1: Start the Backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### Step 2: Start the Frontend

```bash
cd frontend
npm run dev
```

### Step 3: Navigate to Live Monitor

1. Open http://localhost:5173
2. Click **"Live Monitor"** in the navbar
3. Upload a video file (MP4, MOV, AVI)
4. Watch violations appear in real-time

### Step 4: Review Violations

- Each violation shows:
  - Severity badge (CRITICAL/HIGH/MEDIUM/LOW)
  - OSHA code and regulation title
  - Plain English explanation
  - Timestamp in video
  - Location in frame
  - Video clip indicator

### Step 5: Control Playback

- **Pause** - Temporarily stop analysis
- **Resume** - Continue from current position
- **Stop** - End session completely
- **Sound Toggle** - Enable/disable audio alerts

## API Endpoints

### Create Monitoring Session

```http
POST /api/monitoring
Content-Type: multipart/form-data

video: <file>
analysis_interval: 1.5
auto_ticket_filing: true
```

### WebSocket Connection

```javascript
const ws = new WebSocket('ws://localhost:8000/api/monitoring/ws/{session_id}')

ws.onmessage = (event) => {
  const message = JSON.parse(event.data)

  if (message.type === 'violation') {
    // New violation detected
    console.log(message.data)
  } else if (message.type === 'progress') {
    // Processing progress update
    console.log(`${message.data.current_time}s / ${message.data.total_time}s`)
  } else if (message.type === 'completed') {
    // Session finished
  }
}
```

### Control Session

```http
POST /api/monitoring/{session_id}/pause
POST /api/monitoring/{session_id}/resume
POST /api/monitoring/{session_id}/stop
```

## Database Schema

### MonitoringSession

```sql
CREATE TABLE monitoring_sessions (
    id TEXT PRIMARY KEY,
    video_file_path TEXT NOT NULL,
    original_filename TEXT,
    status TEXT DEFAULT 'pending',  -- pending|processing|paused|completed|stopped|failed

    -- Video metadata
    frame_rate REAL,
    total_frames INTEGER,
    duration_seconds REAL,

    -- Processing state
    current_frame INTEGER DEFAULT 0,
    current_timestamp REAL DEFAULT 0.0,
    violations_detected_count INTEGER DEFAULT 0,

    -- Settings
    analysis_interval_seconds REAL DEFAULT 1.5,
    auto_ticket_filing BOOLEAN DEFAULT TRUE,

    created_at DATETIME,
    started_at DATETIME,
    completed_at DATETIME
);
```

### Violation (Extended)

New fields added to existing `violations` table:

```sql
-- Real-time monitoring fields
monitoring_session_id TEXT,  -- FK to monitoring_sessions
detection_timestamp REAL,    -- Video timestamp in seconds
video_clip_path TEXT,        -- Path to 30s evidence clip
frame_path TEXT              -- Path to violation screenshot
```

## Hackathon Demo Flow

### For the Judges:

1. **Upload a construction safety video**
   - Example: workers on scaffolding, electrical work, etc.

2. **Watch violations appear in real-time**
   - Each detection triggers:
     - Sound alert
     - Browser notification
     - Visual pulse animation
     - OSHA regulation mapping

3. **Demonstrate deduplication**
   - Same violation won't spam repeatedly
   - 5-minute cooldown shows intelligence

4. **Show auto-ticketing**
   - CRITICAL/HIGH violations auto-file tickets
   - Status updates to "in_progress"
   - Ready for ServiceNow/Procore integration

5. **Review evidence**
   - 30-second video clips saved
   - Frame screenshots captured
   - Complete audit trail

## Technology Stack

- **Amazon Nova Pro (v1:0)** - Multimodal vision analysis
- **Amazon Nova 2 Lite (v1:0)** - OSHA regulation mapping
- **Amazon Nova Act** - Automated ticket filing (optional)
- **FastAPI + WebSockets** - Real-time backend
- **React + TypeScript** - Interactive frontend
- **OpenCV** - Video processing
- **SQLAlchemy** - Database ORM

## Performance

- **Analysis Rate**: ~0.67 frames/second (1 every 1.5s)
- **Latency**: ~2-3 seconds from detection to alert
- **Video Clip Extraction**: ~500ms per clip
- **WebSocket Broadcast**: <100ms

## Cost Optimization

1. **Frame Sampling** - Only 1 frame every 1.5s instead of all frames
2. **Deduplication** - Prevents redundant Nova API calls
3. **Configurable Interval** - Adjust analysis frequency based on budget
4. **Smart Triggering** - Can add motion detection pre-filter

## Future Enhancements

- **Live RTSP/RTMP streams** (real CCTV integration)
- **Multi-camera monitoring** (grid view)
- **Violation heatmap** (track problem areas over time)
- **Custom alerting rules** (Slack, SMS, email)
- **Historical playback** (review past sessions)
- **AI model fine-tuning** (site-specific hazards)

## Troubleshooting

### WebSocket Connection Issues

If WebSocket fails to connect:

```python
# backend/app/api/monitoring.py
# Check CORS settings allow WebSocket
# Ensure port 8000 is not blocked by firewall
```

### Audio Alerts Not Playing

```javascript
// User must interact with page first (browser security)
// Click anywhere on the page before violations appear
```

### Video Clip Extraction Fails

```python
# Ensure ffmpeg is installed (OpenCV dependency)
# Check disk space in uploads/ directory
```

## License

MIT License - Built for Amazon Nova Hackathon 2024
