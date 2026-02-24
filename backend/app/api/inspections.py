"""
REST API — Inspections
Handles upload, analysis pipeline, and report retrieval.
"""
import os
import uuid
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app import models
from app.agents import ImageAnalyzer, OSHAMapper, ReportGenerator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/inspections", tags=["inspections"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/x-msvideo"}


# ─── Schemas ─────────────────────────────────────────────────────────────────

class ViolationOut(BaseModel):
    id: str
    inspection_id: str
    image_index: Optional[int]
    raw_observation: Optional[str]
    hazard_type: Optional[str]
    location_in_image: Optional[str]
    osha_code: Optional[str]
    osha_title: Optional[str]
    severity: Optional[str]
    plain_english: Optional[str]
    remediation: Optional[str]
    estimated_fix_time: Optional[str]
    status: str
    ticket_id: Optional[str]
    ticket_url: Optional[str]
    assigned_to: Optional[str]

    class Config:
        from_attributes = True


class InspectionOut(BaseModel):
    id: str
    site_name: str
    location: Optional[str]
    inspector_name: Optional[str]
    status: str
    created_at: datetime
    total_violations: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int

    class Config:
        from_attributes = True


class InspectionDetailOut(InspectionOut):
    violations: list[ViolationOut] = []
    report: Optional[dict] = None


class UpdateViolationRequest(BaseModel):
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    ticket_id: Optional[str] = None
    ticket_url: Optional[str] = None


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.post("", response_model=InspectionOut, status_code=201)
async def create_inspection(
    site_name: str = Form(...),
    inspector_name: str = Form(""),
    location: str = Form(""),
    files: list[UploadFile] = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    """Upload media and kick off the analysis pipeline in the background."""
    if not files:
        raise HTTPException(status_code=400, detail="At least one image or video is required.")

    # Create inspection record
    inspection = models.Inspection(
        id=str(uuid.uuid4()),
        site_name=site_name,
        inspector_name=inspector_name or None,
        location=location or None,
        status="uploading",
    )
    db.add(inspection)
    db.commit()
    db.refresh(inspection)

    # Save uploaded files
    upload_path = Path(settings.upload_dir) / inspection.id
    upload_path.mkdir(parents=True, exist_ok=True)

    saved_images = []   # direct image paths
    saved_videos = []   # video paths to extract frames from

    for file in files:
        if file.content_type not in ALLOWED_IMAGE_TYPES | ALLOWED_VIDEO_TYPES:
            continue  # skip unsupported types silently

        ext = Path(file.filename).suffix if file.filename else ".jpg"
        dest = upload_path / f"{uuid.uuid4()}{ext}"

        async with aiofiles.open(dest, "wb") as f:
            content = await file.read()
            await f.write(content)

        is_image = file.content_type in ALLOWED_IMAGE_TYPES
        media = models.InspectionMedia(
            inspection_id=inspection.id,
            file_path=str(dest),
            original_filename=file.filename,
            file_type="image" if is_image else "video",
            mime_type=file.content_type,
        )
        db.add(media)

        if is_image:
            saved_images.append(str(dest))
        else:
            saved_videos.append(str(dest))

    db.commit()

    # Kick off async analysis — pass both images and videos
    background_tasks.add_task(
        _run_analysis_pipeline, inspection.id, saved_images, saved_videos
    )

    db.refresh(inspection)
    return inspection


@router.get("", response_model=list[InspectionOut])
def list_inspections(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return (
        db.query(models.Inspection)
        .order_by(models.Inspection.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{inspection_id}", response_model=InspectionDetailOut)
def get_inspection(inspection_id: str, db: Session = Depends(get_db)):
    inspection = db.query(models.Inspection).filter(models.Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")

    report_data = None
    if inspection.report:
        import json
        try:
            report_data = json.loads(inspection.report.content) if inspection.report.content else None
        except Exception:
            report_data = None

    return InspectionDetailOut(
        **InspectionOut.model_validate(inspection).model_dump(),
        violations=[ViolationOut.model_validate(v) for v in inspection.violations],
        report=report_data,
    )


@router.patch("/{inspection_id}/violations/{violation_id}", response_model=ViolationOut)
def update_violation(
    inspection_id: str,
    violation_id: str,
    body: UpdateViolationRequest,
    db: Session = Depends(get_db),
):
    violation = (
        db.query(models.Violation)
        .filter(
            models.Violation.id == violation_id,
            models.Violation.inspection_id == inspection_id,
        )
        .first()
    )
    if not violation:
        raise HTTPException(status_code=404, detail="Violation not found")

    if body.status is not None:
        violation.status = body.status
    if body.assigned_to is not None:
        violation.assigned_to = body.assigned_to
    if body.ticket_id is not None:
        violation.ticket_id = body.ticket_id
    if body.ticket_url is not None:
        violation.ticket_url = body.ticket_url

    db.commit()
    db.refresh(violation)
    return violation


@router.delete("/{inspection_id}", status_code=204)
def delete_inspection(inspection_id: str, db: Session = Depends(get_db)):
    inspection = db.query(models.Inspection).filter(models.Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    db.delete(inspection)
    db.commit()


# ─── Background pipeline ─────────────────────────────────────────────────────

def _run_analysis_pipeline(inspection_id: str, image_paths: list[str], video_paths: list[str] = None):
    """
    Runs synchronously in a background thread (FastAPI BackgroundTasks).
    Step 0: Extract frames from any uploaded videos
    Step 1: Nova Pro analyzes all images → raw observations
    Step 2: Nova Lite maps to OSHA codes + severity
    Step 3: Nova Lite generates report
    """
    from app.database import SessionLocal
    from app.agents.video_extractor import extract_frames
    db = SessionLocal()

    try:
        inspection = db.query(models.Inspection).filter(models.Inspection.id == inspection_id).first()
        if not inspection:
            return

        # Update status
        inspection.status = "analyzing"
        db.commit()

        # ── Step 0: Extract video frames ───────────────────────────────────
        all_image_paths = list(image_paths)
        if video_paths:
            for video_path in video_paths:
                frames_dir = str(Path(video_path).parent / "frames" / Path(video_path).stem)
                logger.info(f"[{inspection_id}] Extracting frames from {Path(video_path).name}")
                frames = extract_frames(video_path, frames_dir)
                all_image_paths.extend(frames)
                logger.info(f"[{inspection_id}] Got {len(frames)} frames from video")

        if not all_image_paths:
            inspection.status = "completed"
            db.commit()
            return

        # ── Step 1: Image Analysis ─────────────────────────────────────────
        logger.info(f"[{inspection_id}] Step 1: Analyzing {len(all_image_paths)} images with Nova Pro")
        analyzer = ImageAnalyzer()
        image_paths = all_image_paths
        raw_observations = analyzer.analyze_multiple(image_paths)
        logger.info(f"[{inspection_id}] Found {len(raw_observations)} raw observations")

        if not raw_observations:
            inspection.status = "completed"
            db.commit()
            return

        # ── Step 2: OSHA Mapping ───────────────────────────────────────────
        logger.info(f"[{inspection_id}] Step 2: Mapping to OSHA codes with Nova Lite")
        mapper = OSHAMapper()
        violations_data = mapper.map_violations(raw_observations)
        logger.info(f"[{inspection_id}] Mapped {len(violations_data)} violations")

        # Persist violations
        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for item in violations_data:
            sev = item.get("severity", "LOW")
            counts[sev] = counts.get(sev, 0) + 1

            v = models.Violation(
                inspection_id=inspection_id,
                image_index=item.get("image_index"),
                raw_observation=item.get("original_observation"),
                hazard_type=item.get("hazard_type"),
                location_in_image=item.get("location", ""),
                osha_code=item.get("osha_code"),
                osha_title=item.get("osha_title"),
                severity=sev,
                plain_english=item.get("plain_english"),
                remediation=item.get("remediation"),
                estimated_fix_time=item.get("estimated_fix_time"),
            )
            db.add(v)

        inspection.total_violations = len(violations_data)
        inspection.critical_count = counts["CRITICAL"]
        inspection.high_count = counts["HIGH"]
        inspection.medium_count = counts["MEDIUM"]
        inspection.low_count = counts["LOW"]
        db.commit()

        # ── Step 3: Report Generation ──────────────────────────────────────
        logger.info(f"[{inspection_id}] Step 3: Generating report with Nova Lite")
        generator = ReportGenerator()
        report_data = generator.generate_report(
            violations=violations_data,
            site_name=inspection.site_name,
            inspector_name=inspection.inspector_name or "Unknown",
            inspection_date=inspection.created_at.strftime("%Y-%m-%d"),
        )

        import json
        report = models.Report(
            inspection_id=inspection_id,
            content=json.dumps(report_data),
            summary=report_data.get("executive_summary", ""),
        )
        db.add(report)

        inspection.status = "completed"
        db.commit()
        logger.info(f"[{inspection_id}] Analysis complete")

    except Exception as e:
        logger.error(f"[{inspection_id}] Pipeline failed: {e}", exc_info=True)
        try:
            inspection = db.query(models.Inspection).filter(models.Inspection.id == inspection_id).first()
            if inspection:
                inspection.status = "failed"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
