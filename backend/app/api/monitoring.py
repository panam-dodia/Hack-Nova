"""
REST API + WebSocket — Real-Time Monitoring
Handles video upload for real-time monitoring and live violation broadcasts.
"""
import os
import uuid
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    BackgroundTasks,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app import models
from app.agents.realtime_monitor import RealtimeMonitor, ViolationAlert

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])

ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/avi"}


# ─── WebSocket Connection Manager ────────────────────────────────────────────

class ConnectionManager:
    """Manages WebSocket connections for each monitoring session"""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        logger.info(f"WebSocket connected for session {session_id}")

    def disconnect(self, websocket: WebSocket, session_id: str):
        if session_id in self.active_connections:
            self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        logger.info(f"WebSocket disconnected for session {session_id}")

    async def broadcast(self, session_id: str, message: dict):
        """Send message to all connected clients for this session"""
        if session_id in self.active_connections:
            dead_connections = []
            for connection in self.active_connections[session_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to WebSocket: {e}")
                    dead_connections.append(connection)

            # Clean up dead connections
            for dead in dead_connections:
                self.disconnect(dead, session_id)


manager = ConnectionManager()
active_monitors: dict[str, RealtimeMonitor] = {}


# ─── Schemas ─────────────────────────────────────────────────────────────────

class MonitoringSessionOut(BaseModel):
    id: str
    video_file_path: str
    original_filename: Optional[str]
    status: str
    frame_rate: Optional[float]
    total_frames: Optional[int]
    duration_seconds: Optional[float]
    current_frame: int
    current_timestamp: float
    violations_detected_count: int
    analysis_interval_seconds: float
    auto_ticket_filing: bool
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class ViolationOut(BaseModel):
    id: str
    monitoring_session_id: Optional[str]
    inspection_id: str
    hazard_type: Optional[str]
    location_in_image: Optional[str]
    osha_code: Optional[str]
    osha_title: Optional[str]
    severity: Optional[str]
    plain_english: Optional[str]
    detection_timestamp: Optional[float]
    frame_path: Optional[str]
    video_clip_path: Optional[str]
    status: str

    class Config:
        from_attributes = True


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.post("", response_model=MonitoringSessionOut, status_code=201)
async def start_monitoring_session(
    video: UploadFile = File(...),
    analysis_interval: float = Form(1.5),
    auto_ticket_filing: bool = Form(True),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    """
    Upload a video and start a real-time monitoring session.
    Video will be processed frame-by-frame to simulate live CCTV monitoring.
    """
    if video.content_type not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_VIDEO_TYPES)}",
        )

    # Create monitoring session record
    session_id = str(uuid.uuid4())
    session_dir = Path(settings.upload_dir) / "monitoring" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    video_filename = f"{session_id}_{video.filename}"
    video_path = session_dir / video_filename

    # Save video file
    async with aiofiles.open(video_path, "wb") as f:
        content = await video.read()
        await f.write(content)

    logger.info(f"Video uploaded for monitoring: {video_path}")

    # Create database record
    session = models.MonitoringSession(
        id=session_id,
        video_file_path=str(video_path),
        original_filename=video.filename,
        status="pending",
        analysis_interval_seconds=analysis_interval,
        auto_ticket_filing=auto_ticket_filing,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # Start monitoring in background
    background_tasks.add_task(_run_monitoring_pipeline, session_id, str(video_path), db)

    return session


@router.get("", response_model=list[MonitoringSessionOut])
def list_monitoring_sessions(db: Session = Depends(get_db)):
    """Get all monitoring sessions"""
    sessions = db.query(models.MonitoringSession).order_by(models.MonitoringSession.created_at.desc()).all()
    return sessions


@router.get("/{session_id}", response_model=MonitoringSessionOut)
def get_monitoring_session(session_id: str, db: Session = Depends(get_db)):
    """Get details of a specific monitoring session"""
    session = db.query(models.MonitoringSession).filter(models.MonitoringSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Monitoring session not found")
    return session


@router.get("/{session_id}/violations", response_model=list[ViolationOut])
def get_session_violations(session_id: str, db: Session = Depends(get_db)):
    """Get all violations detected in this monitoring session"""
    violations = (
        db.query(models.Violation)
        .filter(models.Violation.monitoring_session_id == session_id)
        .order_by(models.Violation.detection_timestamp)
        .all()
    )
    return violations


@router.post("/{session_id}/pause")
def pause_monitoring(session_id: str):
    """Pause a running monitoring session"""
    if session_id in active_monitors:
        active_monitors[session_id].pause()
        return {"status": "paused", "session_id": session_id}
    raise HTTPException(status_code=404, detail="No active monitoring session found")


@router.post("/{session_id}/resume")
def resume_monitoring(session_id: str):
    """Resume a paused monitoring session"""
    if session_id in active_monitors:
        active_monitors[session_id].resume()
        return {"status": "resumed", "session_id": session_id}
    raise HTTPException(status_code=404, detail="No active monitoring session found")


@router.post("/{session_id}/stop")
def stop_monitoring(session_id: str, db: Session = Depends(get_db)):
    """Stop a monitoring session completely"""
    if session_id in active_monitors:
        active_monitors[session_id].stop()
        del active_monitors[session_id]

        # Update database
        session = db.query(models.MonitoringSession).filter(models.MonitoringSession.id == session_id).first()
        if session:
            session.status = "stopped"
            session.completed_at = datetime.utcnow()
            db.commit()

        return {"status": "stopped", "session_id": session_id}

    raise HTTPException(status_code=404, detail="No active monitoring session found")


# ─── WebSocket ───────────────────────────────────────────────────────────────

@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket for live violation updates.
    Clients connect here to receive real-time alerts.
    """
    await manager.connect(websocket, session_id)
    try:
        while True:
            # Keep connection alive and listen for any client messages
            data = await websocket.receive_text()
            logger.debug(f"Received from client: {data}")

    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
        logger.info(f"Client disconnected from session {session_id}")


# ─── Auto-Ticket Filing ──────────────────────────────────────────────────────

async def _auto_file_ticket(alert: ViolationAlert, session_id: str) -> Optional[str]:
    """
    Automatically file a ticket for critical/high violations.
    In production, this would use Nova Act to file in ServiceNow/Procore/Jira.
    For the hackathon demo, we simulate ticket filing.
    """
    try:
        # Generate ticket ID (in production, Nova Act would return the real ticket ID)
        ticket_id = f"SAFETY-{session_id[:8]}-{alert.violation_id[-6:]}"

        logger.info(f"🎫 Auto-filing ticket {ticket_id} for {alert.severity} violation: {alert.hazard_type}")

        # TODO: In production, call Nova Act here:
        # from nova_act import NovaAct
        # act = NovaAct(api_key=settings.nova_act_api_key)
        # result = await act.execute_task(
        #     "Go to ServiceNow, create incident",
        #     form_data={
        #         "title": f"[{alert.severity}] {alert.osha_code} — {alert.osha_title}",
        #         "description": alert.plain_english,
        #         "priority": "1-Critical" if alert.severity == "CRITICAL" else "2-High",
        #         "category": "Safety",
        #     }
        # )
        # return result.ticket_id

        # For demo: simulate 2-second ticket creation delay
        await asyncio.sleep(2)

        return ticket_id

    except Exception as e:
        logger.error(f"Error filing ticket: {e}")
        return None


# ─── Background Processing ───────────────────────────────────────────────────

async def _run_monitoring_pipeline(session_id: str, video_path: str, db: Session):
    """
    Background task: Process video frame-by-frame and detect violations.
    Broadcasts violations via WebSocket in real-time.
    """
    logger.info(f"Starting monitoring pipeline for session {session_id}")

    # Update session status
    session = db.query(models.MonitoringSession).filter(models.MonitoringSession.id == session_id).first()
    if not session:
        logger.error(f"Session {session_id} not found in database")
        return

    session.status = "processing"
    session.started_at = datetime.utcnow()
    db.commit()

    # Get video metadata
    import cv2
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    cap.release()

    session.frame_rate = fps
    session.total_frames = total_frames
    session.duration_seconds = duration
    db.commit()

    # Create monitor instance
    monitor = RealtimeMonitor()
    active_monitors[session_id] = monitor

    # Callback for violations
    async def on_violation_detected(alert: ViolationAlert):
        logger.info(f"Broadcasting violation: {alert.violation_id}")

        # Create inspection record (for compatibility with existing system)
        inspection = models.Inspection(
            id=str(uuid.uuid4()),
            site_name=f"Real-Time Monitor {session_id[:8]}",
            location="Live CCTV",
            inspector_name="AI Monitor",
            status="completed",
            created_at=datetime.utcnow(),
        )
        db.add(inspection)
        db.commit()

        # Save violation to database
        violation = models.Violation(
            id=alert.violation_id,
            inspection_id=inspection.id,
            monitoring_session_id=session_id,
            raw_observation=alert.observation,
            hazard_type=alert.hazard_type,
            location_in_image=alert.location,
            osha_code=alert.osha_code,
            osha_title=alert.osha_title,
            severity=alert.severity,
            plain_english=alert.plain_english,
            detection_timestamp=alert.timestamp,
            frame_path=alert.frame_path,
            video_clip_path=alert.video_clip_path,
            status="open",
        )
        db.add(violation)

        # Update session violation count
        session.violations_detected_count += 1
        db.commit()

        # Auto-file ticket if enabled and severity is CRITICAL or HIGH
        if session.auto_ticket_filing and alert.severity in ["CRITICAL", "HIGH"]:
            try:
                ticket_id = await _auto_file_ticket(alert, session_id)
                if ticket_id:
                    violation.ticket_id = ticket_id
                    violation.status = "in_progress"
                    db.commit()
                    logger.info(f"Auto-filed ticket {ticket_id} for violation {alert.violation_id}")
            except Exception as e:
                logger.error(f"Failed to auto-file ticket: {e}")

        # Broadcast via WebSocket
        await manager.broadcast(session_id, {
            "type": "violation",
            "data": alert.to_dict(),
        })

    # Callback for progress updates
    async def on_progress(current_time: float, total_time: float, frame: int):
        session.current_timestamp = current_time
        session.current_frame = frame
        db.commit()

        # Broadcast progress
        await manager.broadcast(session_id, {
            "type": "progress",
            "data": {
                "current_time": current_time,
                "total_time": total_time,
                "frame": frame,
                "progress_percent": (current_time / total_time) * 100 if total_time > 0 else 0,
            },
        })

    try:
        # Start monitoring
        await monitor.start_monitoring(
            session_id=session_id,
            video_path=video_path,
            analysis_interval=session.analysis_interval_seconds,
            on_violation=on_violation_detected,
            on_progress=on_progress,
        )

        # Mark as completed
        session.status = "completed"
        session.completed_at = datetime.utcnow()
        db.commit()

        # Broadcast completion
        await manager.broadcast(session_id, {
            "type": "completed",
            "data": {"session_id": session_id, "violations_count": session.violations_detected_count},
        })

        logger.info(f"Monitoring completed for session {session_id}")

    except Exception as e:
        logger.error(f"Error in monitoring pipeline for session {session_id}: {e}")
        session.status = "failed"
        db.commit()

        await manager.broadcast(session_id, {
            "type": "error",
            "data": {"error": str(e)},
        })

    finally:
        # Clean up
        if session_id in active_monitors:
            del active_monitors[session_id]
