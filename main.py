import asyncio
import logging
import os
import sys
import time
import tracemalloc
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

from telegram import BotCommand, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    TypeHandler,
)

from ai_service import create_image, create_video_plan, create_voice, get_video_mode
from config import get_settings, is_admin
from db_service import (
    PRICING_PACKAGES,
    VALID_PACKAGES,
    add_credits,
    count_active_jobs_by_user,
    count_user_jobs_today,
    create_job,
    count_total_users,
    create_pending_purchase,
    deduct_credits,
    ensure_user,
    get_all_users,
    get_job,
    get_jobs_recent,
    get_job_stats,
    get_system_stats,
    get_user,
    get_user_jobs,
    get_users_low_credit,
    get_video_credit_cost,
    init_database,
    mark_job_completed,
    mark_job_failed,
    set_credits,
    set_package,
    update_job_status,
    update_job_state,
)
from handlers_menu import handle_menu_callback, profile_command, show_main_menu
from job_queue import (
    VideoJob as QueueVideoJob,
    enqueue_video_job,
    start_video_workers,
)
from progress import ProgressReporter, estimate_total_seconds, safe_edit_message
from quality_service import validate_video_output, format_quality_errors, log_quality_check
from opc_parser import parse_opc_prompt, format_opc_help
from video_service import HEIGHT as VIDEO_HEIGHT
from video_service import WIDTH as VIDEO_WIDTH
from video_service import build_video, create_image_slide, create_slide


settings = get_settings()
USER_LOCKS: dict[int, asyncio.Lock] = {}
MAKEVIDEO_COOLDOWNS: dict[int, float] = {}
ADMIN_DENIED_MESSAGE = "Bạn không có quyền dùng lệnh này."
MENU_QUALITY_MODES = {
    "standard": "fact",
    "deep": "deep",
    "premium": "premium",
}
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "bot.log"
logger = logging.getLogger("ai_video_bot")


def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("Invalid %s=%r, using %s", name, value, default)
        return default


MONITOR_INTERVAL_SECONDS = _get_int_env("BOT_MONITOR_INTERVAL_SECONDS", 60)
MEMORY_WARN_MB = _get_int_env("BOT_MEMORY_WARN_MB", 1200)


def setup_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.INFO)
    logging.captureWarnings(True)


def _shorten(value: str | None, limit: int = 160) -> str:
    if not value:
        return ""
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _get_process_memory_mb() -> float | None:
    if os.name == "nt":
        try:
            import ctypes
            import ctypes.wintypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.wintypes.DWORD),
                    ("page_fault_count", ctypes.wintypes.DWORD),
                    ("peak_working_set_size", ctypes.c_size_t),
                    ("working_set_size", ctypes.c_size_t),
                    ("quota_peak_paged_pool_usage", ctypes.c_size_t),
                    ("quota_paged_pool_usage", ctypes.c_size_t),
                    ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
                    ("quota_non_paged_pool_usage", ctypes.c_size_t),
                    ("pagefile_usage", ctypes.c_size_t),
                    ("peak_pagefile_usage", ctypes.c_size_t),
                ]

            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            get_process_memory_info = ctypes.WinDLL(
                "psapi.dll",
                use_last_error=True,
            ).GetProcessMemoryInfo
            get_process_memory_info.argtypes = [
                ctypes.wintypes.HANDLE,
                ctypes.POINTER(ProcessMemoryCounters),
                ctypes.wintypes.DWORD,
            ]
            get_process_memory_info.restype = ctypes.wintypes.BOOL
            ok = get_process_memory_info(handle, ctypes.byref(counters), counters.cb)
            if ok:
                return counters.working_set_size / 1024 / 1024
            logger.debug(
                "Cannot read Windows process memory, error=%s",
                ctypes.get_last_error(),
            )
            return None
        except Exception:
            logger.debug("Cannot read Windows process memory", exc_info=True)
            return None

    if sys.platform.startswith("linux"):
        try:
            with open("/proc/self/status", encoding="utf-8") as status_file:
                for line in status_file:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) / 1024
        except Exception:
            logger.debug("Cannot read Linux process memory", exc_info=True)

    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return usage / 1024 / 1024
        return usage / 1024
    except Exception:
        logger.debug("Cannot read process memory from resource", exc_info=True)
        return None


def _describe_update(update: Update) -> str:
    user = update.effective_user
    chat = update.effective_chat
    user_part = (
        f"user_id={user.id} username=@{user.username or '-'}"
        if user
        else "user_id=- username=-"
    )
    chat_part = f"chat_id={chat.id}" if chat else "chat_id=-"

    if update.callback_query:
        event = f"callback data={_shorten(update.callback_query.data, 120)}"
    elif update.message:
        text = update.message.text or update.message.caption
        event = f"message text={_shorten(text, 120)}" if text else "message"
    else:
        event = "update"

    return f"{user_part} {chat_part} {event}"


async def log_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("telegram_update %s", _describe_update(update))


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    exc_info = None
    if context.error:
        exc_info = (
            type(context.error),
            context.error,
            context.error.__traceback__,
        )

    update_info = _describe_update(update) if isinstance(update, Update) else repr(update)
    logger.error("unhandled_error update=%s", update_info, exc_info=exc_info)


async def monitor_resources() -> None:
    if not tracemalloc.is_tracing():
        tracemalloc.start()

    while True:
        try:
            rss_mb = _get_process_memory_mb()
            current_bytes, peak_bytes = tracemalloc.get_traced_memory()
            job_stats = get_job_stats()
            active_jobs = job_stats.get("processing_jobs", 0)
            queued_jobs = job_stats.get("queued_jobs", 0)
            task_count = len(asyncio.all_tasks())
            rss_text = f"{rss_mb:.1f}" if rss_mb is not None else "unknown"

            logger.info(
                "resource_monitor rss_mb=%s python_current_mb=%.1f "
                "python_peak_mb=%.1f queued_video_jobs=%s active_video_jobs=%s "
                "asyncio_tasks=%s",
                rss_text,
                current_bytes / 1024 / 1024,
                peak_bytes / 1024 / 1024,
                queued_jobs,
                active_jobs,
                task_count,
            )

            if rss_mb is not None and rss_mb >= MEMORY_WARN_MB:
                logger.warning(
                    "memory_warning rss_mb=%.1f limit_mb=%s queued_video_jobs=%s "
                    "active_video_jobs=%s",
                    rss_mb,
                    MEMORY_WARN_MB,
                    queued_jobs,
                    active_jobs,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("resource_monitor_failed")

        await asyncio.sleep(MONITOR_INTERVAL_SECONDS)


PRICING_TEXT = """
💎 BẢNG GIÁ AI VIDEO BOT

Gói Starter – 200.000đ
• 40 credits
• Phù hợp dùng thử nghiêm túc
• Tạo khoảng 10 video tiêu chuẩn

Gói Creator – 500.000đ
• 120 credits
• Phù hợp làm content đều
• Tạo khoảng 30 video tiêu chuẩn

Gói Pro – 1.000.000đ
• 300 credits
• Phù hợp creator / bán hàng
• Ưu tiên xử lý nhanh hơn

Gói Agency – 2.000.000đ
• 700 credits
• Phù hợp team / làm dịch vụ
• Hỗ trợ setup style riêng

Quy đổi credit:
• Video ngắn: 2 credits
• Video tiêu chuẩn: 4 credits
• Video chuyên sâu: 7 credits
• Video premium: 10 credits

Thanh toán:
Chuyển khoản xong gửi ảnh bill cho admin để cộng credit.

Tạo đơn mua:
/buy starter
/buy creator
/buy pro
/buy agency
"""


def _get_user_lock(telegram_user_id: int) -> asyncio.Lock:
    if telegram_user_id not in USER_LOCKS:
        USER_LOCKS[telegram_user_id] = asyncio.Lock()
    return USER_LOCKS[telegram_user_id]


def _current_username(update: Update) -> str | None:
    user = update.effective_user
    if not user:
        return None
    return user.username


def _current_first_name(update: Update) -> str | None:
    user = update.effective_user
    if not user:
        return None
    return user.first_name


def _ensure_current_user(update: Update):
    user = update.effective_user
    if not user:
        return None
    return ensure_user(user.id, user.username, user.first_name)


def _format_vnd(amount: int) -> str:
    return f"{amount:,}".replace(",", ".") + "đ"


def _payment_instruction(
    telegram_user_id: int,
    package: dict | None = None,
    purchase_id: int | None = None,
) -> str:
    amount_line = ""
    package_line = ""
    if package:
        package_line = (
            f"Gói: {package['name']}\n"
            f"Credit nhận được: {package['credits']} credits\n"
        )
        amount_line = f"Số tiền: {_format_vnd(package['amount_vnd'])}\n"

    note_parts = [settings.payment_transfer_prefix, str(telegram_user_id)]
    if purchase_id is not None:
        note_parts.append(f"DON{purchase_id}")
    transfer_note = " ".join(note_parts)

    return (
        "Thông tin chuyển khoản:\n\n"
        f"{package_line}"
        f"{amount_line}"
        f"Ngân hàng: {settings.payment_bank_name}\n"
        f"Số tài khoản: {settings.payment_account_number}\n"
        f"Chủ tài khoản: {settings.payment_account_name}\n"
        f"Nội dung CK: {transfer_note}\n\n"
        "Chuyển khoản xong gửi ảnh bill cho admin để cộng credit.\n"
        f"Admin: {settings.payment_admin_contact}"
    )


def _video_preset_for_mode(mode: str) -> str:
    if mode == "premium":
        return "premium"
    if mode in {"quick", "fact"}:
        return "standard"
    return "deep"


async def safe_reply_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup=None,
    **kwargs,
):
    if update.message:
        return await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            **kwargs,
        )

    if update.callback_query and update.callback_query.message:
        return await update.callback_query.message.reply_text(
            text,
            reply_markup=reply_markup,
            **kwargs,
        )

    if update.effective_chat:
        return await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            **kwargs,
        )

    raise RuntimeError(
        "Cannot send message: no message, callback query, or effective chat found."
    )


async def generate_video(
    topic: str,
    mode: str,
    progress: ProgressReporter,
    job_id: str = None,
) -> Path:
    """Generate video and update job state.

    Args:
        topic: Video topic/prompt
        mode: Video mode (deep, standard, premium, etc.)
        progress: Progress reporter
        job_id: Optional job ID for state tracking
    """
    if job_id is None:
        job_id = str(uuid.uuid4())[:8]

    work_dir = Path("output") / job_id
    images_dir = work_dir / "images"
    slides_dir = work_dir / "slides"
    work_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "video_generate_start job_id=%s mode=%s topic=%s",
        job_id,
        mode,
        _shorten(topic, 120),
    )
    await progress.update("Đang phân tích chủ đề", 3, force=True)
    if job_id:
        try:
            update_job_state(job_id, "processing", status="processing", progress_percent=3)
        except Exception:
            logger.exception("job_state_update_failed job_id=%s state=analyzing", job_id)

    await progress.update("Đang viết kịch bản chuyên sâu", 7)

    mode_config = get_video_mode(mode)
    plan = await asyncio.to_thread(create_video_plan, topic, mode)
    scenes = plan["scenes"][: mode_config["max_scenes"]]
    scene_count = len(scenes)
    logger.info(
        "video_plan_ready job_id=%s mode=%s scenes=%s",
        job_id,
        mode,
        scene_count,
    )
    progress.update_estimate(estimate_total_seconds(scene_count))
    await progress.update("Đã viết xong kịch bản", 10, force=True)

    slide_paths = []
    audio_paths = []
    scene_durations = []

    for index, scene in enumerate(scenes):
        logger.info(
            "video_scene_image_start job_id=%s scene=%s/%s",
            job_id,
            index + 1,
            scene_count,
        )
        before_percent = 10 + int((index / scene_count) * 45)
        await progress.update(
            f"Đang tạo ảnh minh họa {index + 1}/{scene_count}",
            before_percent,
        )

        slide_path = await asyncio.to_thread(create_slide, scene, index, slides_dir)
        image_prompt = scene.get("image_prompt")

        if settings.image_enabled and image_prompt:
            try:
                image_path = images_dir / f"image_{index + 1}.png"
                await asyncio.to_thread(create_image, image_prompt, image_path)
                slide_path = await asyncio.to_thread(
                    create_image_slide,
                    scene,
                    image_path,
                    index,
                    slides_dir,
                )
            except Exception as exc:
                logger.warning(
                    "image_generation_failed job_id=%s scene=%s error=%s",
                    job_id,
                    index + 1,
                    exc,
                    exc_info=True,
                )

        image_percent = 10 + int(((index + 1) / scene_count) * 45)
        await progress.update(
            f"Đã tạo ảnh minh họa {index + 1}/{scene_count}",
            image_percent,
        )

        slide_paths.append(slide_path)
        scene_durations.append(scene.get("duration_sec", 0))

    # Update job to generating phase
    if job_id:
        try:
            update_job_state(job_id, "processing", status="processing", progress_percent=55)
        except Exception:
            logger.exception("job_state_update_failed job_id=%s state=generating", job_id)

    for index, scene in enumerate(scenes):
        logger.info(
            "video_scene_voice_start job_id=%s scene=%s/%s",
            job_id,
            index + 1,
            scene_count,
        )
        before_percent = 55 + int((index / scene_count) * 25)
        await progress.update(
            f"Đang tạo giọng đọc {index + 1}/{scene_count}",
            before_percent,
        )

        audio_path = work_dir / f"voice_{index + 1}.mp3"
        await asyncio.to_thread(create_voice, scene["narration"], audio_path)

        audio_paths.append(audio_path)

        voice_percent = 55 + int(((index + 1) / scene_count) * 25)
        await progress.update(
            f"Đã tạo giọng đọc {index + 1}/{scene_count}",
            voice_percent,
        )

    output_video = work_dir / "final_video.mp4"
    logger.info("video_render_start job_id=%s output=%s", job_id, output_video)
    await progress.update("Đang render video chất lượng cao", 85, force=True)

    if job_id:
        try:
            update_job_state(job_id, "processing", status="processing", progress_percent=85)
        except Exception:
            logger.exception("job_state_update_failed job_id=%s state=rendering", job_id)

    await asyncio.to_thread(
        build_video,
        slide_paths,
        audio_paths,
        output_video,
        scene_durations,
        _video_preset_for_mode(mode),
    )
    await progress.update("Đã render xong, chuẩn bị gửi video", 95, force=True)
    logger.info("video_generate_done job_id=%s output=%s", job_id, output_video)

    return output_video


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
Hướng dẫn nhanh:

1. Chọn kiểu video:
/quickvideo nếu muốn test nhanh. Chi phí: 2 credits.
/factvideo nếu muốn video tiêu chuẩn. Chi phí: 4 credits.
/makevideo nếu muốn video sâu và dài hơn. Chi phí: 7 credits.
/premiumvideo nếu muốn bản điện ảnh cao hơn. Chi phí: 10 credits.
/storyvideo nếu chủ đề cần kể chuyện.
/factvideo nếu chủ đề là kiến thức, lịch sử, khoa học, xã hội.

2. Viết chủ đề càng rõ càng tốt:
Thay vì: /makevideo thành công
Nên viết: /makevideo vì sao người trẻ dễ mất phương hướng sau khi ra trường

3. Đợi bot xử lý:
Bot sẽ viết kịch bản, tạo ảnh, tạo giọng đọc, ghép video rồi gửi MP4.

4. Nếu hết quota OpenAI:
Tắt tạo ảnh bằng OPENAI_IMAGE_ENABLED=false trong file .env để tiết kiệm hơn.

5. Nếu hết credit bot:
Dùng /pricing để xem gói và /balance để xem số dư.
"""
    await safe_reply_text(update, context, text)


async def commands_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
Danh sách lệnh:

/start - mở menu bắt đầu
/help - hướng dẫn sử dụng
/commands - danh sách lệnh
/examples - ví dụ chủ đề
/tips - mẹo viết chủ đề
/pricing - bảng giá credit
/balance - số dư credit
/profile - tài khoản của bạn
/myid - xem Telegram ID của bạn
/status - xem cấu hình hiện tại

/makevideo <chủ đề> - tạo video chuyên sâu
/video <chủ đề> - alias của /makevideo
/quickvideo <chủ đề> - tạo video ngắn
/storyvideo <chủ đề> - tạo video kể chuyện
/factvideo <chủ đề> - tạo video giải thích
/premiumvideo <chủ đề> - tạo video premium điện ảnh

/buy <gói> - tạo yêu cầu mua credit
/addcredits <telegram_user_id> <credits> - admin cộng credit
/users - admin xem danh sách user
/user <telegram_user_id> - admin xem chi tiết user
/balanceof <telegram_user_id> - admin xem credit user
/setcredits <telegram_user_id> <credits> - admin set credit
/setpackage <telegram_user_id> <gói> - admin set gói
"""
    await safe_reply_text(update, context, text)


async def examples_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
Ví dụ chủ đề có thể dùng:

/quickvideo 5 sai lầm khiến người trẻ mất động lực
/makevideo vì sao nền văn minh La Mã sụp đổ
/storyvideo hành trình của một người từ thất bại đến kỷ luật
/factvideo hố đen hoạt động như thế nào
/premiumvideo một thành phố tương lai nơi con người sống cùng AI
/makevideo vì sao AI đang thay đổi cách con người làm việc
/factvideo nguồn gốc của tiền và vì sao nó có giá trị
/storyvideo câu chuyện về một thành phố bị lãng quên dưới lòng đất
"""
    await safe_reply_text(update, context, text)


async def tips_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
Mẹo viết chủ đề để video hay hơn:

- Nêu rõ góc nhìn: "vì sao", "điều gì xảy ra nếu", "bài học từ..."
- Thêm đối tượng người xem: "cho người mới đi làm", "cho học sinh", "cho chủ shop"
- Thêm cảm xúc hoặc bối cảnh: "cô đơn", "áp lực", "khủng hoảng", "bước ngoặt"
- Tránh chủ đề quá rộng như "cuộc sống", "thành công", "AI".

Công thức tốt:
/makevideo vì sao <vấn đề> xảy ra và nó thay đổi <đối tượng> như thế nào
"""
    await safe_reply_text(update, context, text)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    balance = None
    if user:
        account = _ensure_current_user(update)
        balance = account.credit_balance

    image_status = "bật" if settings.image_enabled else "tắt"
    admin_status = "đã cấu hình" if settings.admin_telegram_ids else "chưa cấu hình"
    text = f"""
Cấu hình hiện tại:

Số dư của bạn: {balance if balance is not None else 0} credits
Text model: {settings.text_model}
TTS model: {settings.tts_model}
TTS voice: {settings.tts_voice}
Tạo ảnh AI: {image_status}
Image model: {settings.image_model}
Image size: {settings.image_size}
Image quality: {settings.image_quality}
Video format: 1080x1920, 30fps, MP4 H.264
Admin credit: {admin_status}

Video tạo ra nằm trong thư mục output/<job_id>/final_video.mp4
"""
    await safe_reply_text(update, context, text)


async def pricing_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    payment_text = ""
    if user:
        payment_text = "\n\n" + _payment_instruction(user.id)
    await safe_reply_text(update, context, PRICING_TEXT + payment_text)


async def opc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show OPC (One Prompt Command) help."""
    help_text = format_opc_help()
    await safe_reply_text(update, context, help_text, parse_mode="Markdown")


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        await safe_reply_text(update, context, "Không xác định được tài khoản Telegram.")
        return

    account = _ensure_current_user(update)
    await safe_reply_text(update, context,
        f"Telegram ID: {user.id}\n"
        f"Gói hiện tại: {account.package_name}\n"
        f"Số dư hiện tại của bạn: {account.credit_balance} credits.\n\n"
        "Dùng /pricing để xem bảng giá nạp thêm credit."
    )


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        await safe_reply_text(update, context, "Không xác định được tài khoản Telegram.")
        return

    _ensure_current_user(update)
    await safe_reply_text(update, context, f"Telegram ID của bạn: {user.id}")


async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        await safe_reply_text(update, context, "Không xác định được tài khoản Telegram.")
        return

    _ensure_current_user(update)

    if not context.args:
        await safe_reply_text(update, context,
            "Bạn muốn mua gói nào?\n\n"
            "/buy starter\n"
            "/buy creator\n"
            "/buy pro\n"
            "/buy agency\n\n"
            "Thông tin chuyển khoản chung:\n\n"
            + _payment_instruction(user.id)
            + "\n\nChọn đúng gói bằng /buy starter, /buy creator, "
            "/buy pro hoặc /buy agency để bot tạo mã đơn và số tiền chính xác."
        )
        return

    package_key = context.args[0].lower().strip()
    package = PRICING_PACKAGES.get(package_key)
    if not package:
        await safe_reply_text(update, context,
            "Gói không hợp lệ. Chọn một trong các gói:\n"
            "/buy starter\n/buy creator\n/buy pro\n/buy agency"
        )
        return

    purchase_id = create_pending_purchase(user.id, package_key)
    await safe_reply_text(update, context,
        f"Đã tạo yêu cầu mua credit #{purchase_id}.\n\n"
        + _payment_instruction(user.id, package, purchase_id)
        + "\n\n"
        f"Sau khi xác nhận, admin cộng bằng lệnh:\n"
        f"/addcredits {user.id} {package['credits']}"
    )


async def addcredits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin = update.effective_user
    if not admin or not is_admin(admin.id):
        await safe_reply_text(update, context, ADMIN_DENIED_MESSAGE)
        return

    if len(context.args) != 2:
        await safe_reply_text(update, context,
            "Sai cú pháp.\nVí dụ: /addcredits 123456789 40"
        )
        return

    try:
        target_user_id = int(context.args[0])
        credits = int(context.args[1])
    except ValueError:
        await safe_reply_text(update, context,
            "telegram_user_id và credits phải là số.\n"
            "Ví dụ: /addcredits 123456789 40"
        )
        return

    try:
        new_balance = add_credits(
            target_user_id,
            credits,
            description=f"Admin {admin.id} cộng credit thủ công",
        )
    except ValueError as exc:
        await safe_reply_text(update, context, f"Lỗi cộng credit: {exc}")
        return

    await safe_reply_text(update, context,
        f"Đã cộng {credits} credits cho user {target_user_id}.\n"
        f"Số dư mới: {new_balance} credits."
    )


async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin = update.effective_user
    if not admin or not is_admin(admin.id):
        await safe_reply_text(update, context, ADMIN_DENIED_MESSAGE)
        return

    users = get_all_users()
    if not users:
        await safe_reply_text(update, context, "Chưa có user nào.")
        return

    lines = ["Danh sách user gần nhất:\n"]
    for item in users:
        username = f"@{item['username']}" if item["username"] else "Không có username"
        first_name = item["first_name"] or "Không có tên"
        lines.append(
            f"ID: {item['telegram_user_id']}\n"
            f"User: {username}\n"
            f"Tên: {first_name}\n"
            f"Gói: {item['package_name']}\n"
            f"Credit: {item['credit_balance']}\n"
            "---"
        )

    await safe_reply_text(update, context, "\n".join(lines))


async def user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin = update.effective_user
    if not admin or not is_admin(admin.id):
        await safe_reply_text(update, context, ADMIN_DENIED_MESSAGE)
        return

    if len(context.args) != 1:
        await safe_reply_text(update, context, "Dùng: /user <telegram_user_id>")
        return

    try:
        telegram_user_id = int(context.args[0])
    except ValueError:
        await safe_reply_text(update, context, "telegram_user_id phải là số.")
        return

    user = get_user(telegram_user_id)
    if not user:
        await safe_reply_text(update, context, "Không tìm thấy user.")
        return

    username = f"@{user['username']}" if user["username"] else "Không có username"
    first_name = user["first_name"] or "Không có tên"
    await safe_reply_text(update, context,
        "Thông tin user:\n\n"
        f"ID: {user['telegram_user_id']}\n"
        f"Username: {username}\n"
        f"Tên: {first_name}\n"
        f"Role: {user['role']}\n"
        f"Gói: {user['package_name']}\n"
        f"Credit: {user['credit_balance']}\n"
        f"Tạo lúc: {user['created_at']}\n"
        f"Cập nhật: {user['updated_at']}"
    )


async def balanceof_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin = update.effective_user
    if not admin or not is_admin(admin.id):
        await safe_reply_text(update, context, ADMIN_DENIED_MESSAGE)
        return

    if len(context.args) != 1:
        await safe_reply_text(update, context, "Dùng: /balanceof <telegram_user_id>")
        return

    try:
        telegram_user_id = int(context.args[0])
    except ValueError:
        await safe_reply_text(update, context, "telegram_user_id phải là số.")
        return

    user = get_user(telegram_user_id)
    if not user:
        await safe_reply_text(update, context, "Không tìm thấy user.")
        return

    await safe_reply_text(update, context,
        f"User {telegram_user_id} còn {user['credit_balance']} credits."
    )


async def jobs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent video jobs (admin only)."""
    admin = update.effective_user
    if not admin or not is_admin(admin.id):
        await safe_reply_text(update, context, ADMIN_DENIED_MESSAGE)
        return

    jobs = get_jobs_recent(limit=20)
    if not jobs:
        await safe_reply_text(update, context, "Chưa có video job nào.")
        return

    lines = ["📋 **20 Video Job Gần Nhất:**\n"]
    for job in jobs:
        status_emoji = {
            "queued": "🕒",
            "completed": "✅",
            "processing": "⏳",
            "failed": "❌",
        }.get(job["status"], "❓")

        lines.append(
            f"{status_emoji} Job: {job['job_id']}\n"
            f"   User: {job['telegram_user_id']}\n"
            f"   Chủ đề: {job['topic'][:50]}\n"
            f"   Chất lượng: {job['quality']} | Trạng thái: {job['sop_state']} ({job['status']})\n"
            f"   Tiến độ: {job['progress_percent']}%\n"
            f"   Lúc: {job['created_at'][:10]}\n"
        )

    await safe_reply_text(update, context, "\n".join(lines))


async def job_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed job information (admin only)."""
    admin = update.effective_user
    if not admin or not is_admin(admin.id):
        await safe_reply_text(update, context, ADMIN_DENIED_MESSAGE)
        return

    if len(context.args) != 1:
        await safe_reply_text(update, context, "Dùng: /job <job_id>")
        return

    job_id = context.args[0]
    job = get_job(job_id)

    if not job:
        await safe_reply_text(update, context, f"Không tìm thấy job: {job_id}")
        return

    status_emoji = {
        "queued": "🕒",
        "completed": "✅",
        "processing": "⏳",
        "failed": "❌",
    }.get(job.status, "❓")

    error_line = f"Lỗi: {job.error_message}\n" if job.error_message else ""
    output_line = f"Output: {job.output_path}\n" if job.output_path else ""

    text = (
        f"{status_emoji} **Chi Tiết Job {job.job_id}**\n\n"
        f"User ID: {job.telegram_user_id}\n"
        f"Chat ID: {job.chat_id}\n"
        f"Chủ đề: {job.topic}\n"
        f"Chất lượng: {job.quality}\n"
        f"Credit yêu cầu: {job.required_credits}\n"
        f"Trạng thái: {job.status}\n"
        f"SOP State: {job.sop_state}\n"
        f"Tiến độ: {job.progress_percent}%\n"
        f"Thời gian ước tính: {job.estimated_total_seconds}s\n"
        f"{error_line}"
        f"{output_line}"
        f"Tạo lúc: {job.created_at}\n"
        f"Cập nhật: {job.updated_at}"
    )

    await safe_reply_text(update, context, text)


async def myjobs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        await safe_reply_text(update, context, "Không xác định được tài khoản Telegram.")
        return

    jobs = get_user_jobs(user.id, limit=10)
    if not jobs:
        await safe_reply_text(update, context, "Bạn chưa có video job nào.")
        return

    lines = ["📋 10 job gần nhất của bạn:\n"]
    for job in jobs:
        status_emoji = {
            "queued": "🕒",
            "completed": "✅",
            "processing": "⏳",
            "failed": "❌",
        }.get(job.status, "❓")
        lines.append(
            f"{status_emoji} Job: {job.job_id}\n"
            f"Chất lượng: {job.quality} | Trạng thái: {job.status}\n"
            f"Tiến độ: {job.progress_percent}%\n"
            f"Tạo lúc: {job.created_at[:19]}\n"
            "---"
        )

    await safe_reply_text(update, context, "\n".join(lines))


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show system statistics (admin only)."""
    admin = update.effective_user
    if not admin or not is_admin(admin.id):
        await safe_reply_text(update, context, ADMIN_DENIED_MESSAGE)
        return

    stats = get_system_stats()

    success_rate = (
        f"{(stats['successful_jobs'] / stats['total_jobs'] * 100):.1f}%"
        if stats['total_jobs'] > 0
        else "0%"
    )

    text = (
        "📊 **Thống Kê Hệ Thống**\n\n"
        f"👥 **Người Dùng:**\n"
        f"  Tổng: {stats['total_users']}\n"
        f"  Hết credit: {stats['users_low_credit']}\n"
        f"  Đang chờ thanh toán: {stats['pending_payments']}\n\n"
        f"💳 **Credit:**\n"
        f"  Tổng trong hệ: {stats['total_credits']} credits\n\n"
        f"🎬 **Video Job:**\n"
        f"  Tổng: {stats['total_jobs']}\n"
        f"  Thành công: {stats['successful_jobs']}\n"
        f"  Thất bại: {stats['failed_jobs']}\n"
        f"  Đang xếp hàng: {stats['queued_jobs']}\n"
        f"  Đang xử lý: {stats['processing_jobs']}\n"
        f"  Tỷ lệ thành công: {success_rate}\n\n"
        f"📅 **Hôm nay:**\n"
        f"  Job tạo: {stats['today_jobs']}"
    )

    await safe_reply_text(update, context, text)


async def lowcredit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List users with low credit (admin only)."""
    admin = update.effective_user
    if not admin or not is_admin(admin.id):
        await safe_reply_text(update, context, ADMIN_DENIED_MESSAGE)
        return

    users = get_users_low_credit(threshold=5)

    if not users:
        await safe_reply_text(update, context, "Tất cả user đều có credit đủ (> 5).")
        return

    lines = ["⚠️ **Người Dùng Hết/Sắp Hết Credit (≤5):**\n"]
    for user in users:
        username = f"@{user['username']}" if user['username'] else "Không username"
        first_name = user['first_name'] or "Không tên"

        lines.append(
            f"ID: {user['telegram_user_id']}\n"
            f"  {username} - {first_name}\n"
            f"  Credit: {user['credit_balance']} | Gói: {user['package_name']}\n"
            f"  Tạo: {user['created_at'][:10]}\n"
        )

    await safe_reply_text(update, context, "\n".join(lines))


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast message to all users (admin only)."""
    admin = update.effective_user
    if not admin or not is_admin(admin.id):
        await safe_reply_text(update, context, ADMIN_DENIED_MESSAGE)
        return

    if not context.args:
        await safe_reply_text(update, context,
            "Dùng: /broadcast <message>\n"
            "Ví dụ: /broadcast Hệ thống bảo trì 1 giờ."
        )
        return

    message = " ".join(context.args)

    # Show confirmation
    users = get_all_users(limit=10000)
    await safe_reply_text(update, context,
        f"📢 Chuẩn bị gửi broadcast đến {len(users)} user:\n\n"
        f"Nội dung: {message}\n\n"
        "Nhập: /confirm_broadcast để tiếp tục"
    )

    # Store message in context for later confirmation
    context.user_data['broadcast_message'] = message


async def confirm_broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm and send broadcast (admin only)."""
    admin = update.effective_user
    if not admin or not is_admin(admin.id):
        await safe_reply_text(update, context, ADMIN_DENIED_MESSAGE)
        return

    message = context.user_data.get('broadcast_message')
    if not message:
        await safe_reply_text(update, context, "Không có broadcast message nào đang chờ.")
        return

    users = get_all_users(limit=10000)
    sent = 0
    failed = 0

    status_msg = await safe_reply_text(update, context, "📢 Đang gửi broadcast...")

    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user['telegram_user_id'],
                text=f"📢 **Thông báo từ Admin:**\n\n{message}"
            )
            sent += 1
        except Exception as exc:
            failed += 1
            logger.warning(
                "broadcast_failed user_id=%s error=%s",
                user["telegram_user_id"],
                exc,
                exc_info=True,
            )

    await safe_edit_message(
        status_msg,
        f"✅ Gửi broadcast xong.\n"
        f"Thành công: {sent}/{len(users)}\n"
        f"Thất bại: {failed}"
    )

    # Clear stored message
    context.user_data['broadcast_message'] = None


async def setcredits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin = update.effective_user
    if not admin or not is_admin(admin.id):
        await safe_reply_text(update, context, ADMIN_DENIED_MESSAGE)
        return

    if len(context.args) != 2:
        await safe_reply_text(update, context, "Dùng: /setcredits <telegram_user_id> <credits>")
        return

    try:
        telegram_user_id = int(context.args[0])
        credits = int(context.args[1])
    except ValueError:
        await safe_reply_text(update, context, "telegram_user_id và credits phải là số.")
        return

    try:
        new_balance = set_credits(telegram_user_id, credits)
    except ValueError as exc:
        await safe_reply_text(update, context, f"Lỗi set credit: {exc}")
        return

    await safe_reply_text(update, context,
        f"Đã set user {telegram_user_id} = {new_balance} credits."
    )


async def setpackage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin = update.effective_user
    if not admin or not is_admin(admin.id):
        await safe_reply_text(update, context, ADMIN_DENIED_MESSAGE)
        return

    if len(context.args) != 2:
        await safe_reply_text(update, context, "Dùng: /setpackage <telegram_user_id> <package_name>")
        return

    try:
        telegram_user_id = int(context.args[0])
    except ValueError:
        await safe_reply_text(update, context, "telegram_user_id phải là số.")
        return

    package_name = context.args[1].lower().strip()
    if package_name not in VALID_PACKAGES:
        await safe_reply_text(update, context,
            "Gói không hợp lệ. Chọn: trial, starter, creator, pro, agency"
        )
        return

    try:
        new_package = set_package(telegram_user_id, package_name)
    except ValueError as exc:
        await safe_reply_text(update, context, f"Lỗi set gói: {exc}")
        return

    await safe_reply_text(update, context,
        f"Đã set user {telegram_user_id} sang gói {new_package}."
    )


async def run_video_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    mode: str,
    command_name: str,
    example: str,
):
    user = update.effective_user
    if not user:
        await safe_reply_text(update, context, "Không xác định được tài khoản Telegram.")
        return

    chat = update.effective_chat
    if not chat:
        await safe_reply_text(update, context, "Không xác định được cuộc trò chuyện Telegram.")
        return

    args = context.args or []
    if not args:
        await safe_reply_text(update, context,
            f"Bạn chưa nhập chủ đề.\nVí dụ: {command_name} {example}"
        )
        return

    now = time.monotonic()
    last_request_at = MAKEVIDEO_COOLDOWNS.get(user.id)
    cooldown = settings.makevideo_cooldown_seconds
    if cooldown > 0 and last_request_at is not None:
        remaining = int(cooldown - (now - last_request_at))
        if remaining > 0:
            await safe_reply_text(
                update,
                context,
                f"Bạn thao tác quá nhanh. Vui lòng chờ {remaining} giây rồi thử lại.",
            )
            return

    active_jobs = count_active_jobs_by_user(user.id)
    if active_jobs >= settings.max_active_job_per_user:
        await safe_reply_text(update, context,
            "Bạn đang có một video đang được xử lý. Vui lòng chờ video hiện tại "
            "hoàn tất rồi tạo video mới."
        )
        return

    topic = " ".join(args)
    logger.info(
        "video_request_received user_id=%s mode=%s command=%s topic=%s",
        user.id,
        mode,
        command_name,
        _shorten(topic, 160),
    )

    # Parse OPC format if provided
    opc_result = parse_opc_prompt(topic)
    topic = opc_result.get("topic", topic)
    opc_quality = opc_result.get("quality", mode)

    # Map OPC quality to video mode if explicitly set
    if opc_quality and opc_quality != "deep":
        mode = opc_quality

    mode_config = get_video_mode(mode)
    credit_cost = get_video_credit_cost(mode)
    account = ensure_user(user.id, _current_username(update), _current_first_name(update))

    if account.package_name == "trial" and count_user_jobs_today(user.id) >= 2:
        await safe_reply_text(
            update,
            context,
            "Gói dùng thử chỉ tạo tối đa 2 video mỗi ngày. "
            "Dùng /pricing để xem gói nạp thêm credit.",
        )
        return

    if account.credit_balance < credit_cost:
        logger.info(
            "video_job_rejected_low_credit user_id=%s balance=%s cost=%s",
            user.id,
            account.credit_balance,
            credit_cost,
        )
        await safe_reply_text(update, context,
            f"Bạn không đủ credit để tạo {mode_config['label']}.\n\n"
            f"Chi phí: {credit_cost} credits\n"
            f"Số dư hiện tại: {account.credit_balance} credits\n\n"
            "Dùng /pricing để xem gói nạp credit."
        )
        return

    job_id = str(uuid.uuid4())[:8]
    logger.info(
        "video_job_queued job_id=%s user_id=%s mode=%s cost=%s",
        job_id,
        user.id,
        mode,
        credit_cost,
    )

    try:
        db_job = create_job(
            job_id=job_id,
            telegram_user_id=user.id,
            chat_id=chat.id,
            topic=topic,
            quality=mode,
            required_credits=credit_cost,
            status="queued",
            estimated_total_seconds=mode_config.get("estimated_duration_sec", 120),
            max_active_jobs_per_user=settings.max_active_job_per_user,
        )
        await enqueue_video_job(
            QueueVideoJob(
                job_id=db_job.job_id,
                telegram_user_id=db_job.telegram_user_id,
                chat_id=db_job.chat_id or chat.id,
                topic=db_job.topic,
                quality=db_job.quality,
                required_credits=db_job.required_credits,
                created_at=db_job.created_at,
            )
        )
    except asyncio.QueueFull:
        mark_job_failed(job_id, "Queue is full")
        await safe_reply_text(
            update,
            context,
            "Hàng đợi đang quá tải. Vui lòng thử lại sau ít phút.",
        )
        return
    except ValueError as exc:
        if str(exc) == "active_job_exists":
            await safe_reply_text(update, context,
                "Bạn đang có một video đang được xử lý. Vui lòng chờ video hiện tại "
                "hoàn tất rồi tạo video mới."
            )
            return
        logger.exception("create_job_rejected job_id=%s error=%s", job_id, exc)
        await safe_reply_text(update, context, "Có lỗi khi tạo job. Vui lòng thử lại sau.")
        return
    except Exception as exc:
        logger.exception("create_or_enqueue_job_failed job_id=%s error=%s", job_id, exc)
        await safe_reply_text(
            update,
            context,
            "Có lỗi khi tạo job. Vui lòng thử lại sau.",
        )
        return

    MAKEVIDEO_COOLDOWNS[user.id] = now
    await safe_reply_text(
        update,
        context,
        "✅ Đã nhận yêu cầu tạo video.\n\n"
        f"Mã job: {job_id}\n"
        "Trạng thái: Đang xếp hàng xử lý.\n\n"
        "Bot sẽ tự gửi video khi hoàn tất.",
    )


async def send_video_with_retry(app, job: QueueVideoJob, video_path: Path, caption: str) -> None:
    attempts = settings.telegram_send_retry_count + 1
    for attempt in range(1, attempts + 1):
        try:
            with open(video_path, "rb") as video_file:
                await app.bot.send_video(
                    chat_id=job.chat_id,
                    video=video_file,
                    caption=caption,
                    width=VIDEO_WIDTH,
                    height=VIDEO_HEIGHT,
                    supports_streaming=True,
                )
            return
        except Exception:
            logger.exception(
                "video_send_attempt_failed job_id=%s attempt=%s/%s",
                job.job_id,
                attempt,
                attempts,
            )
            if attempt >= attempts:
                raise
            await asyncio.sleep(3)


async def process_video_job(app, job: QueueVideoJob, worker_id: int) -> None:
    attempts = settings.job_retry_count + 1
    status = None
    mode_config = get_video_mode(job.quality)

    logger.info(
        "video_job_processing worker_id=%s job_id=%s user_id=%s",
        worker_id,
        job.job_id,
        job.telegram_user_id,
    )
    update_job_status(job.job_id, "processing", progress_percent=1)
    status = await app.bot.send_message(
        chat_id=job.chat_id,
        text=(
            "🎬 Video của bạn đang được xử lý\n\n"
            f"Mã job: {job.job_id}\n"
            "📌 Trạng thái: Đang chuẩn bị"
        ),
    )

    for attempt in range(1, attempts + 1):
        progress = ProgressReporter(
            message=status,
            estimated_total_seconds=estimate_total_seconds(10),
        )
        try:
            if attempt > 1:
                await safe_edit_message(
                    status,
                    f"Đang thử xử lý lại video.\nMã job: {job.job_id}\nLần thử: {attempt}/{attempts}",
                )
                update_job_status(job.job_id, "processing", error_message=None)

            video_path = await generate_video(
                job.topic,
                job.quality,
                progress,
                job_id=job.job_id,
            )

            await progress.update("Kiểm tra chất lượng video", 95, force=True)
            is_valid, errors = validate_video_output(video_path)
            log_quality_check(video_path, is_valid, errors, job_id=job.job_id)

            if not is_valid:
                error_message = format_quality_errors(errors)
                logger.warning(
                    "video_quality_failed job_id=%s errors=%s",
                    job.job_id,
                    "; ".join(errors),
                )
                mark_job_failed(
                    job.job_id,
                    f"Quality validation failed: {'; '.join(errors)}",
                )
                await safe_edit_message(
                    status,
                    f"❌ Video không đáp ứng tiêu chuẩn chất lượng.\n\n{error_message}\n\n"
                    "Credit chưa bị trừ. Vui lòng thử lại.",
                )
                return

            try:
                update_job_state(job.job_id, "output", status="processing", progress_percent=96)
            except Exception as exc:
                logger.exception("job_state_update_failed job_id=%s error=%s", job.job_id, exc)

            await progress.update("Đang gửi video", 97, force=True)
            logger.info("video_send_start job_id=%s user_id=%s path=%s", job.job_id, job.telegram_user_id, video_path)

            account = get_user(job.telegram_user_id)
            current_balance = int(account["credit_balance"]) if account else 0
            if current_balance < job.required_credits:
                mark_job_failed(job.job_id, "Insufficient credits before sending video")
                await safe_edit_message(
                    status,
                    "❌ Số dư credit hiện tại không đủ để gửi video.\n\n"
                    "Credit chưa bị trừ. Vui lòng nạp thêm credit rồi tạo lại video.",
                )
                return

            await send_video_with_retry(
                app,
                job,
                video_path,
                caption=f"{mode_config['label'].title()}: {job.topic}",
            )

            new_balance = deduct_credits(
                job.telegram_user_id,
                job.required_credits,
                description=f"{mode_config['label']}: {job.topic}",
            )
            mark_job_completed(job.job_id, str(video_path))
            await safe_edit_message(
                status,
                f"✅ Hoàn tất. Đã trừ {job.required_credits} credits.\n"
                f"Số dư còn lại: {new_balance} credits.",
            )
            logger.info(
                "video_job_completed job_id=%s user_id=%s cost=%s new_balance=%s",
                job.job_id,
                job.telegram_user_id,
                job.required_credits,
                new_balance,
            )
            return

        except Exception as exc:
            logger.exception(
                "video_job_attempt_failed worker_id=%s job_id=%s attempt=%s/%s error=%s",
                worker_id,
                job.job_id,
                attempt,
                attempts,
                exc,
            )
            if attempt < attempts:
                await asyncio.sleep(5)
                continue

            mark_job_failed(job.job_id, str(exc))
            await safe_edit_message(
                status,
                "❌ Lỗi khi tạo video.\n\n"
                "Credit chưa bị trừ vì video chưa hoàn tất. "
                "Vui lòng thử lại sau hoặc liên hệ admin nếu lỗi lặp lại.",
            )
            await app.bot.send_message(
                chat_id=job.chat_id,
                text=(
                    f"Job {job.job_id} đã thất bại sau {attempts} lần thử.\n"
                    "Credit chưa bị trừ."
                ),
            )
            return


async def makevideo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected_mode_from_menu = context.user_data.get("video_mode")
    selected_quality = context.user_data.get("video_quality")
    selected_mode = selected_mode_from_menu or MENU_QUALITY_MODES.get(selected_quality, "deep")
    selected_label = {
        "quick": "video nhanh",
        "standard": "video tiêu chuẩn",
        "fact": "video tiêu chuẩn",
        "deep": "video chuyên sâu",
        "premium": "video premium",
        "story": "video kể chuyện",
    }.get(selected_mode, "video chuyên sâu")

    await run_video_request(
        update,
        context,
        mode=selected_mode,
        command_name="/makevideo",
        example=f"vì sao người trẻ dễ mất phương hướng sau khi ra trường ({selected_label})",
    )


async def quickvideo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_video_request(
        update,
        context,
        mode="quick",
        command_name="/quickvideo",
        example="3 bài học về kỷ luật cá nhân",
    )


async def storyvideo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_video_request(
        update,
        context,
        mode="story",
        command_name="/storyvideo",
        example="hành trình của một người vượt qua thất bại đầu đời",
    )


async def factvideo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_video_request(
        update,
        context,
        mode="fact",
        command_name="/factvideo",
        example="hố đen hoạt động như thế nào",
    )


async def premiumvideo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_video_request(
        update,
        context,
        mode="premium",
        command_name="/premiumvideo",
        example="một thành phố tương lai nơi con người sống cùng AI",
    )


async def setup_bot_commands(app):
    await app.bot.set_my_commands(
        [
            BotCommand("start", "Mở menu bắt đầu"),
            BotCommand("help", "Hướng dẫn sử dụng"),
            BotCommand("commands", "Xem danh sách lệnh"),
            BotCommand("examples", "Xem ví dụ chủ đề"),
            BotCommand("tips", "Mẹo viết chủ đề"),
            BotCommand("pricing", "Xem bảng giá credit"),
            BotCommand("opc", "Hướng dẫn OPC command"),
            BotCommand("balance", "Xem số dư credit"),
            BotCommand("profile", "Xem tài khoản"),
            BotCommand("myid", "Xem Telegram ID của bạn"),
            BotCommand("myjobs", "Xem video job của bạn"),
            BotCommand("status", "Xem cấu hình bot"),
            BotCommand("makevideo", "Tạo video chuyên sâu"),
            BotCommand("quickvideo", "Tạo video ngắn"),
            BotCommand("storyvideo", "Tạo video kể chuyện"),
            BotCommand("factvideo", "Tạo video giải thích"),
            BotCommand("premiumvideo", "Tạo video premium"),
            BotCommand("buy", "Tạo yêu cầu mua credit"),
            BotCommand("users", "Admin xem danh sách user"),
            BotCommand("user", "Admin xem chi tiết user"),
            BotCommand("balanceof", "Admin xem credit user"),
            BotCommand("jobs", "Admin xem video job gần đây"),
            BotCommand("job", "Admin xem chi tiết job"),
            BotCommand("stats", "Admin xem thống kê hệ thống"),
            BotCommand("lowcredit", "Admin xem user sắp hết credit"),
            BotCommand("broadcast", "Admin gửi thông báo"),
            BotCommand("addcredits", "Admin cộng credit"),
            BotCommand("setcredits", "Admin set credit"),
            BotCommand("setpackage", "Admin set gói"),
        ]
    )
    asyncio.create_task(monitor_resources(), name="resource_monitor")
    await start_video_workers(
        app,
        worker_count=settings.video_worker_count,
        processor=process_video_job,
        max_queue_size=settings.max_queue_size,
    )
    logger.info(
        "bot_initialized monitor_interval_seconds=%s memory_warn_mb=%s "
        "video_worker_count=%s max_queue_size=%s log_file=%s",
        MONITOR_INTERVAL_SECONDS,
        MEMORY_WARN_MB,
        settings.video_worker_count,
        settings.max_queue_size,
        LOG_FILE,
    )


def main():
    setup_logging()
    logger.info("bot_starting")
    init_database()

    app = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .post_init(setup_bot_commands)
        .build()
    )

    app.add_handler(TypeHandler(Update, log_update), group=-1)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("commands", commands_command))
    app.add_handler(CommandHandler("examples", examples_command))
    app.add_handler(CommandHandler("tips", tips_command))
    app.add_handler(CommandHandler("pricing", pricing_command))
    app.add_handler(CommandHandler("opc", opc_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CommandHandler("myjobs", myjobs_command))
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CommandHandler("addcredits", addcredits_command))
    app.add_handler(CommandHandler("users", users_command))
    app.add_handler(CommandHandler("user", user_command))
    app.add_handler(CommandHandler("balanceof", balanceof_command))
    app.add_handler(CommandHandler("jobs", jobs_command))
    app.add_handler(CommandHandler("job", job_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("lowcredit", lowcredit_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("confirm_broadcast", confirm_broadcast_command))
    app.add_handler(CommandHandler("setcredits", setcredits_command))
    app.add_handler(CommandHandler("setpackage", setpackage_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("makevideo", makevideo))
    app.add_handler(CommandHandler("video", makevideo))
    app.add_handler(CommandHandler("quickvideo", quickvideo))
    app.add_handler(CommandHandler("storyvideo", storyvideo))
    app.add_handler(CommandHandler("factvideo", factvideo))
    app.add_handler(CommandHandler("premiumvideo", premiumvideo))
    app.add_handler(CallbackQueryHandler(handle_menu_callback))
    app.add_error_handler(error_handler)

    logger.info("bot_polling_start")
    app.run_polling()


if __name__ == "__main__":
    main()
