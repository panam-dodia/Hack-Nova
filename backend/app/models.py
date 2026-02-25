import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Boolean, Float
from sqlalchemy.orm import relationship
from app.database import Base


def new_id() -> str:
    return str(uuid.uuid4())


class Inspection(Base):
    __tablename__ = "inspections"

    id = Column(String, primary_key=True, default=new_id)
    site_name = Column(String, nullable=False)
    location = Column(String, nullable=True)
    inspector_name = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending | analyzing | completed | failed
    created_at = Column(DateTime, default=datetime.utcnow)

    # Violation summary counts
    total_violations = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)
    high_count = Column(Integer, default=0)
    medium_count = Column(Integer, default=0)
    low_count = Column(Integer, default=0)

    media = relationship("InspectionMedia", back_populates="inspection", cascade="all, delete")
    violations = relationship("Violation", back_populates="inspection", cascade="all, delete")
    report = relationship("Report", back_populates="inspection", uselist=False, cascade="all, delete")


class InspectionMedia(Base):
    __tablename__ = "inspection_media"

    id = Column(String, primary_key=True, default=new_id)
    inspection_id = Column(String, ForeignKey("inspections.id"), nullable=False)
    file_path = Column(String, nullable=False)
    original_filename = Column(String, nullable=True)
    file_type = Column(String, nullable=True)  # image | video
    mime_type = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    inspection = relationship("Inspection", back_populates="media")


class MonitoringSession(Base):
    __tablename__ = "monitoring_sessions"

    id = Column(String, primary_key=True, default=new_id)
    video_file_path = Column(String, nullable=False)
    original_filename = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending | processing | paused | completed | failed

    # Video metadata
    frame_rate = Column(Float, nullable=True)
    total_frames = Column(Integer, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Processing state
    current_frame = Column(Integer, default=0)
    current_timestamp = Column(Float, default=0.0)
    violations_detected_count = Column(Integer, default=0)

    # Settings
    analysis_interval_seconds = Column(Float, default=1.5)  # Analyze every 1-2 seconds
    auto_ticket_filing = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    violations = relationship("Violation", back_populates="monitoring_session", cascade="all, delete")


class Violation(Base):
    __tablename__ = "violations"

    id = Column(String, primary_key=True, default=new_id)
    inspection_id = Column(String, ForeignKey("inspections.id"), nullable=False)
    image_index = Column(Integer, nullable=True)

    # Raw observation from Nova Pro
    raw_observation = Column(Text, nullable=True)
    hazard_type = Column(String, nullable=True)
    location_in_image = Column(String, nullable=True)

    # OSHA mapping from Nova Lite
    osha_code = Column(String, nullable=True)
    osha_title = Column(String, nullable=True)
    severity = Column(String, nullable=True)  # CRITICAL | HIGH | MEDIUM | LOW
    plain_english = Column(Text, nullable=True)
    remediation = Column(Text, nullable=True)
    estimated_fix_time = Column(String, nullable=True)

    # Ticket filing
    status = Column(String, default="open")  # open | in_progress | resolved
    ticket_id = Column(String, nullable=True)
    ticket_url = Column(String, nullable=True)
    assigned_to = Column(String, nullable=True)

    # Real-time monitoring fields
    monitoring_session_id = Column(String, ForeignKey("monitoring_sessions.id"), nullable=True)
    detection_timestamp = Column(Float, nullable=True)  # Video timestamp in seconds
    video_clip_path = Column(String, nullable=True)  # 30-second evidence clip
    frame_path = Column(String, nullable=True)  # Screenshot of violation

    created_at = Column(DateTime, default=datetime.utcnow)

    inspection = relationship("Inspection", back_populates="violations")
    monitoring_session = relationship("MonitoringSession", back_populates="violations")


class Report(Base):
    __tablename__ = "reports"

    id = Column(String, primary_key=True, default=new_id)
    inspection_id = Column(String, ForeignKey("inspections.id"), nullable=False)
    content = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    inspection = relationship("Inspection", back_populates="report")
