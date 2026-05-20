"""OPC (One Prompt Command) parser for video creation.

Supports two formats:

1. Simple format:
   /makevideo lịch sử hình thành Trái Đất
   
2. OPC pipe format:
   /makevideo topic | style | duration | audience | goal | tone | quality
   
   Example:
   /makevideo lòng kiên trì | hoạt hình cảm xúc | 90s | người trẻ | truyền cảm hứng | nhẹ nhàng, sâu sắc | premium
"""

from typing import TypedDict

# Allowed values
ALLOWED_QUALITY = {"standard", "deep", "premium"}
ALLOWED_DURATION = {"45s", "60s", "90s", "120s", "150s"}
ALLOWED_STYLES = {
    "cinematic documentary",
    "hoạt hình cảm xúc",
    "infographics",
    "documentary",
    "storytelling",
    "educational",
    "animated",
    "live action",
}


class OPCPrompt(TypedDict, total=False):
    """Parsed OPC prompt data."""
    topic: str
    style: str
    duration: str
    audience: str
    goal: str
    tone: str
    quality: str
    raw_input: str


def _normalize_quality(quality: str) -> str:
    """Map quality alias to video mode."""
    q = quality.lower().strip()
    if q in {"standard", "fact"}:
        return "standard"
    if q in {"deep", "detailed"}:
        return "deep"
    if q in {"premium", "cinema"}:
        return "premium"
    return "deep"  # default


def _parse_pipe_format(text: str) -> OPCPrompt | None:
    """Try to parse pipe-separated format.
    
    Returns None if not in pipe format.
    """
    # Check if text contains pipe separator
    if "|" not in text:
        return None
    
    parts = [p.strip() for p in text.split("|")]
    
    # OPC format needs at least topic and optionally other fields
    if len(parts) < 1:
        return None
    
    result: OPCPrompt = {
        "topic": parts[0] if len(parts) > 0 else "",
        "style": parts[1] if len(parts) > 1 else "cinematic documentary",
        "duration": parts[2] if len(parts) > 2 else "90s",
        "audience": parts[3] if len(parts) > 3 else "general audience",
        "goal": parts[4] if len(parts) > 4 else "educate and retain attention",
        "tone": parts[5] if len(parts) > 5 else "deep, clear, engaging",
        "quality": parts[6] if len(parts) > 6 else "deep",
        "raw_input": text,
    }
    
    # Validate quality
    quality_normalized = _normalize_quality(result["quality"])
    result["quality"] = quality_normalized
    
    # Validate duration
    if result["duration"] not in ALLOWED_DURATION:
        result["duration"] = "90s"
    
    return result


def parse_opc_prompt(raw_text: str) -> OPCPrompt:
    """Parse OPC prompt from raw user input.
    
    Supports:
    1. Simple format: just the topic
    2. OPC pipe format: topic | style | duration | audience | goal | tone | quality
    
    Args:
        raw_text: Raw text from user
        
    Returns:
        Parsed OPC prompt with all fields filled
    """
    text = raw_text.strip()
    
    # Try pipe format first
    if "|" in text:
        parsed = _parse_pipe_format(text)
        if parsed:
            return parsed
    
    # Fallback to simple format (just topic)
    result: OPCPrompt = {
        "topic": text,
        "style": "cinematic documentary",
        "duration": "90s",
        "audience": "general audience",
        "goal": "educate and retain attention",
        "tone": "deep, clear, engaging",
        "quality": "deep",
        "raw_input": raw_text,
    }
    
    return result


def format_opc_help() -> str:
    """Format help text for OPC command."""
    return """📋 **OPC — One Prompt Command** 

Tạo video chuyên sâu hơn với một lệnh duy nhất.

**Format:**
/makevideo `chủ đề | phong cách | thời lượng | khán giả | mục đích | tone | chất lượng`

**Ví dụ:**
```
/makevideo lòng kiên trì | hoạt hình cảm xúc | 90s | người trẻ | truyền cảm hứng | nhẹ nhàng, sâu sắc | premium
```

**Giá trị mặc định (nếu bỏ trống):**
• Phong cách: cinematic documentary
• Thời lượng: 90s
• Khán giả: general audience
• Mục đích: educate and retain attention
• Tone: deep, clear, engaging
• Chất lượng: deep

**Thời lượng cho phép:**
45s, 60s, 90s, 120s, 150s

**Chất lượng cho phép:**
• standard — video tiêu chuẩn (4 credits)
• deep — video chuyên sâu (7 credits)
• premium — video premium (10 credits)

**Cách dùng đơn giản (vẫn hỗ trợ):**
/makevideo tên chủ đề tùy ý

Hệ thống sẽ tự chọn cấu hình mặc định phù hợp."""


def get_opc_menu_button() -> dict:
    """Return OPC menu button config."""
    return {
        "text": "🎯 Cách viết OPC",
        "callback_data": "show_opc_help",
    }
