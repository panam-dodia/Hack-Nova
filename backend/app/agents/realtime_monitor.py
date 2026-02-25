"""
Real-Time Monitor Agent
Processes uploaded videos frame-by-frame to simulate live CCTV monitoring.
Detects violations in real-time with deduplication and auto-ticket filing.
"""
import asyncio
import cv2
import json
import logging
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable
from dataclasses import dataclass, asdict

from app.agents.image_analyzer import ImageAnalyzer
from app.agents.osha_mapper import OSHAMapper

logger = logging.getLogger(__name__)


@dataclass
class ViolationAlert:
    """Real-time violation alert that gets broadcast via WebSocket"""
    violation_id: str
    session_id: str
    timestamp: float  # Video timestamp in seconds
    frame_number: int
    hazard_type: str
    severity: str
    observation: str
    location: str
    osha_code: Optional[str] = None
    osha_title: Optional[str] = None
    plain_english: Optional[str] = None
    frame_path: Optional[str] = None
    video_clip_path: Optional[str] = None
    detected_at: str = None  # ISO timestamp

    def to_dict(self):
        return asdict(self)


class ViolationDeduplicator:
    """
    Prevents duplicate alerts for the same violation.
    Uses cooldown period: once detected, same violation type won't alert again for N seconds.
    """
    def __init__(self, cooldown_seconds: int = 300):  # 5 minute default
        self.cooldown_seconds = cooldown_seconds
        self.last_seen = {}  # (hazard_type, location) -> timestamp

    def should_alert(self, hazard_type: str, location: str, current_timestamp: float) -> bool:
        """Check if this violation should trigger an alert"""
        key = (hazard_type.lower(), location.lower())
        last_time = self.last_seen.get(key)

        if last_time is None:
            # First time seeing this violation
            self.last_seen[key] = current_timestamp
            return True

        time_since_last = current_timestamp - last_time
        if time_since_last >= self.cooldown_seconds:
            # Cooldown period has passed
            self.last_seen[key] = current_timestamp
            return True

        # Still in cooldown period
        return False

    def reset(self):
        """Clear all cooldown timers"""
        self.last_seen.clear()


class RealtimeMonitor:
    """
    Processes video frame-by-frame to detect safety violations in real-time.
    Simulates live CCTV monitoring for hackathon demo.
    """

    def __init__(self):
        self.image_analyzer = ImageAnalyzer()
        self.osha_mapper = OSHAMapper()
        self.is_running = False
        self.current_session_id = None

    async def start_monitoring(
        self,
        session_id: str,
        video_path: str,
        analysis_interval: float = 1.5,
        on_violation: Optional[Callable] = None,
        on_progress: Optional[Callable] = None,
    ):
        """
        Start processing video frame-by-frame.

        Args:
            session_id: Unique monitoring session ID
            video_path: Path to video file
            analysis_interval: Seconds between frame analyses (default 1.5)
            on_violation: Async callback when violation detected: async fn(ViolationAlert)
            on_progress: Async callback for progress updates: async fn(current_time, total_time, frame)
        """
        self.is_running = True
        self.current_session_id = session_id
        deduplicator = ViolationDeduplicator(cooldown_seconds=300)

        # Open video
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps

        logger.info(f"Starting monitoring session {session_id}: {fps} fps, {total_frames} frames, {duration:.1f}s")

        # Calculate frame skip interval
        frames_per_analysis = int(fps * analysis_interval)

        frame_number = 0
        analysis_count = 0
        violations_detected = 0

        # Create output directory for frames and clips
        output_dir = Path("uploads") / "monitoring" / session_id
        frames_dir = output_dir / "frames"
        clips_dir = output_dir / "clips"
        frames_dir.mkdir(parents=True, exist_ok=True)
        clips_dir.mkdir(parents=True, exist_ok=True)

        try:
            while self.is_running and cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    logger.info("End of video reached")
                    break

                current_timestamp = frame_number / fps

                # Analyze frame at intervals
                if frame_number % frames_per_analysis == 0:
                    analysis_count += 1

                    # Save frame for analysis
                    frame_path = frames_dir / f"frame_{frame_number:06d}.jpg"
                    cv2.imwrite(str(frame_path), frame)

                    # Send progress update
                    if on_progress:
                        await on_progress(current_timestamp, duration, frame_number)

                    # Analyze frame for violations
                    try:
                        observations = self.image_analyzer.analyze_image(str(frame_path))

                        if observations:
                            logger.info(f"Frame {frame_number} ({current_timestamp:.1f}s): {len(observations)} observations")

                            # Map to OSHA violations
                            violations = self.osha_mapper.map_violations(observations)

                            for idx, violation in enumerate(violations):
                                obs = observations[idx]
                                hazard_type = obs.get("hazard_type", "Unknown")
                                location = obs.get("location", "Unknown location")

                                # Check deduplication
                                if deduplicator.should_alert(hazard_type, location, current_timestamp):
                                    violations_detected += 1

                                    # Extract video clip around violation (15 seconds before/after)
                                    clip_path = await self._extract_clip(
                                        video_path,
                                        current_timestamp,
                                        clips_dir / f"violation_{violations_detected}.mp4",
                                        duration_before=15,
                                        duration_after=15
                                    )

                                    # Create alert
                                    alert = ViolationAlert(
                                        violation_id=f"{session_id}_{violations_detected}",
                                        session_id=session_id,
                                        timestamp=current_timestamp,
                                        frame_number=frame_number,
                                        hazard_type=hazard_type,
                                        severity=violation.get("severity", "MEDIUM"),
                                        observation=obs.get("observation", ""),
                                        location=location,
                                        osha_code=violation.get("osha_code"),
                                        osha_title=violation.get("osha_title"),
                                        plain_english=violation.get("plain_english"),
                                        frame_path=str(frame_path),
                                        video_clip_path=str(clip_path) if clip_path else None,
                                        detected_at=datetime.utcnow().isoformat(),
                                    )

                                    logger.info(f"🚨 VIOLATION DETECTED: {hazard_type} at {current_timestamp:.1f}s - {violation.get('severity')}")

                                    # Trigger callback
                                    if on_violation:
                                        await on_violation(alert)
                                else:
                                    logger.debug(f"Duplicate violation suppressed: {hazard_type} at {location}")

                    except Exception as e:
                        logger.error(f"Error analyzing frame {frame_number}: {e}")

                frame_number += 1

                # Small delay to simulate real-time processing
                await asyncio.sleep(0.01)

        finally:
            cap.release()
            self.is_running = False
            logger.info(f"Monitoring session {session_id} completed: {analysis_count} frames analyzed, {violations_detected} violations")

    async def _extract_clip(
        self,
        video_path: str,
        timestamp: float,
        output_path: Path,
        duration_before: float = 15,
        duration_after: float = 15,
    ) -> Optional[Path]:
        """
        Extract a video clip around a violation timestamp.

        Args:
            video_path: Source video path
            timestamp: Center timestamp in seconds
            output_path: Where to save clip
            duration_before: Seconds to include before violation
            duration_after: Seconds to include after violation

        Returns:
            Path to extracted clip or None if failed
        """
        try:
            start_time = max(0, timestamp - duration_before)
            duration = duration_before + duration_after

            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            # Jump to start time
            start_frame = int(start_time * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

            # Create video writer
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

            frames_to_write = int(duration * fps)
            for _ in range(frames_to_write):
                ret, frame = cap.read()
                if not ret:
                    break
                out.write(frame)

            cap.release()
            out.release()

            logger.info(f"Extracted clip: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Error extracting clip: {e}")
            return None

    def pause(self):
        """Pause monitoring"""
        self.is_running = False
        logger.info(f"Monitoring paused for session {self.current_session_id}")

    def resume(self):
        """Resume monitoring"""
        self.is_running = True
        logger.info(f"Monitoring resumed for session {self.current_session_id}")

    def stop(self):
        """Stop monitoring completely"""
        self.is_running = False
        logger.info(f"Monitoring stopped for session {self.current_session_id}")
