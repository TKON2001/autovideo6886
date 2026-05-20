import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    openai_api_key: str
    admin_telegram_ids: tuple[int, ...]
    payment_bank_name: str
    payment_account_number: str
    payment_account_name: str
    payment_admin_contact: str
    payment_transfer_prefix: str
    text_model: str
    tts_model: str
    tts_voice: str
    image_enabled: bool
    image_model: str
    image_size: str
    image_quality: str
    video_worker_count: int
    max_active_job_per_user: int
    max_queue_size: int
    job_retry_count: int
    sqlite_timeout_seconds: int
    telegram_send_retry_count: int
    makevideo_cooldown_seconds: int


def _parse_admin_ids(value: str | None) -> tuple[int, ...]:
    if not value:
        return ()

    admin_ids = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            admin_ids.append(int(item))
        except ValueError:
            raise RuntimeError(f"Invalid ADMIN_TELEGRAM_IDS value: {item}") from None

    return tuple(admin_ids)


def get_admin_ids() -> set[int]:
    return set(_parse_admin_ids(os.getenv("ADMIN_TELEGRAM_IDS")))


def is_admin(user_id: int) -> bool:
    return user_id in get_admin_ids()


def _get_int_env(name: str, default: int, minimum: int | None = None) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default

    try:
        parsed = int(value)
    except ValueError:
        return default

    if minimum is not None and parsed < minimum:
        return default

    return parsed


def get_settings() -> Settings:
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    openai_key = os.getenv("OPENAI_API_KEY")

    if not telegram_token:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN in .env")

    if not openai_key:
        raise RuntimeError("Missing OPENAI_API_KEY in .env")

    return Settings(
        telegram_bot_token=telegram_token,
        openai_api_key=openai_key,
        admin_telegram_ids=_parse_admin_ids(os.getenv("ADMIN_TELEGRAM_IDS")),
        payment_bank_name=os.getenv("PAYMENT_BANK_NAME", "Chưa cấu hình"),
        payment_account_number=os.getenv("PAYMENT_ACCOUNT_NUMBER", "Chưa cấu hình"),
        payment_account_name=os.getenv("PAYMENT_ACCOUNT_NAME", "Chưa cấu hình"),
        payment_admin_contact=os.getenv("PAYMENT_ADMIN_CONTACT", "admin"),
        payment_transfer_prefix=os.getenv("PAYMENT_TRANSFER_PREFIX", "AIVIDEO"),
        text_model=os.getenv("OPENAI_TEXT_MODEL", "gpt-4.1-mini"),
        tts_model=os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
        tts_voice=os.getenv("OPENAI_TTS_VOICE", "alloy"),
        image_enabled=os.getenv("OPENAI_IMAGE_ENABLED", "true").lower() == "true",
        image_model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1-mini"),
        image_size=os.getenv("OPENAI_IMAGE_SIZE", "1024x1536"),
        image_quality=os.getenv("OPENAI_IMAGE_QUALITY", "medium"),
        video_worker_count=_get_int_env("VIDEO_WORKER_COUNT", 2, minimum=1),
        max_active_job_per_user=_get_int_env("MAX_ACTIVE_JOB_PER_USER", 1, minimum=1),
        max_queue_size=_get_int_env("MAX_QUEUE_SIZE", 100, minimum=1),
        job_retry_count=_get_int_env("JOB_RETRY_COUNT", 1, minimum=0),
        sqlite_timeout_seconds=_get_int_env("SQLITE_TIMEOUT_SECONDS", 30, minimum=1),
        telegram_send_retry_count=_get_int_env("TELEGRAM_SEND_RETRY_COUNT", 2, minimum=0),
        makevideo_cooldown_seconds=_get_int_env("MAKEVIDEO_COOLDOWN_SECONDS", 30, minimum=0),
    )
