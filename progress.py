import time

from telegram import Message


MIN_EDIT_INTERVAL_SECONDS = 3.0


def format_seconds(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes:02d}:{secs:02d}"


def estimate_total_seconds(scene_count: int | None = None) -> float:
    scene_count = scene_count or 10
    render_seconds = max(60, scene_count * 35)
    return 20 + scene_count * 20 + scene_count * 8 + render_seconds + 10


def format_progress_message(
    step_name: str,
    progress_percent: int,
    elapsed_seconds: float,
    estimated_total_seconds: float,
) -> str:
    remaining = max(0, estimated_total_seconds - elapsed_seconds)
    progress_percent = max(0, min(100, int(progress_percent)))

    return (
        "🎬 Đang tạo video cho bạn...\n\n"
        f"📌 Trạng thái: {step_name}\n"
        f"📊 Tiến độ: {progress_percent}%\n"
        f"⏱ Đã chạy: {format_seconds(elapsed_seconds)}\n"
        f"⌛ Ước tính còn: {format_seconds(remaining)}\n\n"
        "Vui lòng không gửi lại lệnh nhiều lần trong lúc bot đang xử lý."
    )


async def safe_edit_message(message: Message, text: str) -> bool:
    try:
        await message.edit_text(text)
        return True
    except Exception:
        return False


class ProgressReporter:
    def __init__(self, message: Message, estimated_total_seconds: float):
        self.message = message
        self.estimated_total_seconds = estimated_total_seconds
        self.started_at = time.monotonic()
        self.last_edit_at = 0.0
        self.last_text = ""

    def update_estimate(self, estimated_total_seconds: float) -> None:
        self.estimated_total_seconds = estimated_total_seconds

    async def update(
        self,
        step_name: str,
        progress_percent: int,
        force: bool = False,
    ) -> None:
        now = time.monotonic()
        if not force and now - self.last_edit_at < MIN_EDIT_INTERVAL_SECONDS:
            return

        elapsed = now - self.started_at
        text = format_progress_message(
            step_name=step_name,
            progress_percent=progress_percent,
            elapsed_seconds=elapsed,
            estimated_total_seconds=self.estimated_total_seconds,
        )

        if text == self.last_text:
            return

        if await safe_edit_message(self.message, text):
            self.last_edit_at = now
            self.last_text = text
