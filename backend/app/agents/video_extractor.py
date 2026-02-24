"""
Video Frame Extractor
Extracts evenly-spaced keyframes from a video file and saves them as JPEGs.
These frames are then fed into the ImageAnalyzer just like regular photos.

Strategy: extract 1 frame every N seconds (default: every 5s), capped at
MAX_FRAMES to keep Bedrock costs reasonable for a demo.
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

FRAME_INTERVAL_SECONDS = 5   # grab one frame every 5 seconds
MAX_FRAMES = 10               # safety cap — max frames per video


def extract_frames(video_path: str, output_dir: str) -> list[str]:
    """
    Extract keyframes from a video and save as JPEGs.
    Returns list of saved frame paths.
    """
    try:
        import cv2
    except ImportError:
        logger.error("opencv-python-headless not installed. Run: pip install opencv-python-headless")
        return []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"Could not open video: {video_path}")
        return []

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_seconds = total_frames / fps

    interval_frames = int(fps * FRAME_INTERVAL_SECONDS)
    if interval_frames < 1:
        interval_frames = 1

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    saved_paths = []
    frame_idx = 0
    saved_count = 0

    logger.info(
        f"Video: {Path(video_path).name} — "
        f"{duration_seconds:.1f}s, {fps:.0f}fps, extracting every {FRAME_INTERVAL_SECONDS}s"
    )

    while cap.isOpened() and saved_count < MAX_FRAMES:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            break

        frame_file = output_path / f"frame_{saved_count:04d}.jpg"
        cv2.imwrite(str(frame_file), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        saved_paths.append(str(frame_file))
        logger.info(f"  Extracted frame {saved_count + 1} at {frame_idx / fps:.1f}s → {frame_file.name}")

        frame_idx += interval_frames
        saved_count += 1

    cap.release()
    logger.info(f"Extracted {len(saved_paths)} frames from {Path(video_path).name}")
    return saved_paths
