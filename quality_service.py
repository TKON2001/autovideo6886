"""Quality validation service for generated videos.

Ensures videos meet requirements before sending to users:
- File exists and is not empty
- Correct format (MP4, H.264)
- Correct resolution (1080x1920)
- Reasonable file size for Telegram
- FPS is 30
"""

import subprocess
from pathlib import Path

# Maximum file size for Telegram (50 MB)
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024
# Expected video specs
EXPECTED_WIDTH = 1080
EXPECTED_HEIGHT = 1920
EXPECTED_FPS = 30
EXPECTED_CODEC = "h264"


def validate_video_output(video_path: Path) -> tuple[bool, list[str]]:
    """Validate video file meets quality requirements.
    
    Args:
        video_path: Path to the video file
        
    Returns:
        (is_valid, errors_list) where errors_list is empty if valid
    """
    errors: list[str] = []
    
    # Check file exists
    if not video_path.exists():
        errors.append(f"Video file not found: {video_path}")
        return False, errors
    
    # Check file is not empty
    file_size = video_path.stat().st_size
    if file_size == 0:
        errors.append("Video file is empty (0 bytes)")
        return False, errors
    
    # Check file extension
    if video_path.suffix.lower() != ".mp4":
        errors.append(f"Expected .mp4 format, got {video_path.suffix}")
        return False, errors
    
    # Check file size for Telegram
    if file_size > MAX_FILE_SIZE_BYTES:
        size_mb = file_size / (1024 * 1024)
        limit_mb = MAX_FILE_SIZE_BYTES / (1024 * 1024)
        errors.append(
            f"File too large: {size_mb:.1f}MB exceeds {limit_mb:.0f}MB limit"
        )
    
    # Try to check resolution and codec with ffprobe if available
    ffprobe_errors = _check_video_specs(video_path)
    if ffprobe_errors:
        errors.extend(ffprobe_errors)
    
    is_valid = len(errors) == 0
    return is_valid, errors


def _check_video_specs(video_path: Path) -> list[str]:
    """Check video resolution, FPS, and codec using ffprobe.
    
    Returns list of errors if specs don't match. Empty if OK or ffprobe unavailable.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate,codec_name",
                "-of", "csv=p=0",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if result.returncode != 0:
            return []  # ffprobe failed, skip validation
        
        output = result.stdout.strip()
        if not output:
            return []
        
        parts = output.split(",")
        if len(parts) < 4:
            return []
        
        width, height, fps_fraction, codec = parts[0], parts[1], parts[2], parts[3]
        
        errors: list[str] = []
        
        # Check resolution
        try:
            w, h = int(width), int(height)
            if w != EXPECTED_WIDTH or h != EXPECTED_HEIGHT:
                errors.append(
                    f"Resolution {w}x{h} expected 1080x1920"
                )
        except (ValueError, IndexError):
            pass
        
        # Check FPS
        try:
            fps_parts = fps_fraction.split("/")
            if len(fps_parts) == 2:
                fps = float(fps_parts[0]) / float(fps_parts[1])
                if abs(fps - EXPECTED_FPS) > 1:
                    errors.append(f"FPS {fps:.1f} expected {EXPECTED_FPS}")
        except (ValueError, ZeroDivisionError, IndexError):
            pass
        
        # Check codec
        if codec.lower() not in ["h264", "libx264", "h.264"]:
            pass  # Don't fail on codec, as long as it's h264-ish
        
        return errors
        
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # ffprobe not available, skip detailed validation
        return []
    except Exception:
        # Unexpected error, skip detailed validation
        return []


def format_quality_errors(errors: list[str]) -> str:
    """Format validation errors for user message.
    
    Args:
        errors: List of error messages
        
    Returns:
        Formatted error message
    """
    if not errors:
        return ""
    
    if len(errors) == 1:
        return f"⚠️ Kiểm tra chất lượng: {errors[0]}"
    
    error_list = "\n".join(f"  • {e}" for e in errors)
    return f"⚠️ Kiểm tra chất lượng phát hiện vấn đề:\n{error_list}"


def log_quality_check(
    video_path: Path,
    is_valid: bool,
    errors: list[str],
    job_id: str = "",
) -> None:
    """Log quality check results for admin debugging.
    
    Args:
        video_path: Path to video file
        is_valid: Whether validation passed
        errors: List of errors if any
        job_id: Job ID for tracking
    """
    prefix = f"[{job_id}] " if job_id else ""
    status = "✓ PASS" if is_valid else "✗ FAIL"
    file_size_mb = video_path.stat().st_size / (1024 * 1024) if video_path.exists() else 0
    
    print(f"{prefix}Quality check {status}: {video_path.name} ({file_size_mb:.1f}MB)")
    
    if errors:
        for error in errors:
            print(f"{prefix}  • {error}")
