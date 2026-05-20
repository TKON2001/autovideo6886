import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from config import get_settings
from db_service import ensure_user, get_user
from menu import (
    back_menu_keyboard,
    buy_package_keyboard,
    main_menu_keyboard,
    pricing_keyboard,
    quality_keyboard,
    support_keyboard,
    video_type_keyboard,
)


settings = get_settings()
logger = logging.getLogger("ai_video_bot.menu")

MAIN_MENU_TEXT = """
🤖 AI VIDEO BOT

Nhập 1 ý tưởng, bot tự tạo video hoàn chỉnh:

• Viết kịch bản
• Tạo ảnh minh họa
• Tạo voice AI
• Ghép video
• Gửi lại ngay trên Telegram

Chọn chức năng bên dưới:
"""

CREATE_VIDEO_TEXT = """
🎬 TẠO VIDEO

Chọn loại video bạn muốn tạo:

⚡ Video nhanh
• 30–60 giây
• 2 credits
• Phù hợp test ý tưởng

🎯 Video tiêu chuẩn
• 60–90 giây
• 4 credits
• Phù hợp nội dung kiến thức

🎬 Video chuyên sâu
• 90–150 giây
• 7 credits
• Kịch bản sâu hơn

✨ Video premium
• Cinematic hơn
• Chất lượng cao hơn
• 10 credits

📖 Video kể chuyện
• Có mạch câu chuyện
• 4 credits

Sau khi chọn loại, bot sẽ hiện lệnh mẫu để bạn gửi chủ đề.
"""

PRICING_MENU_TEXT = """
💎 BẢNG GIÁ AI VIDEO BOT

Gói Starter – 200.000đ
• 40 credits
• Phù hợp dùng thử nghiêm túc
• Khoảng 10 video tiêu chuẩn

Gói Creator – 500.000đ
• 120 credits
• Phù hợp làm content đều
• Khoảng 30 video tiêu chuẩn

Gói Pro – 1.000.000đ
• 300 credits
• Phù hợp creator / bán hàng
• Ưu tiên xử lý nhanh hơn

Gói Agency – 2.000.000đ
• 700 credits
• Phù hợp team / làm dịch vụ
• Hỗ trợ setup style riêng

Quy đổi:
• Video ngắn: 2 credits
• Video tiêu chuẩn: 4 credits
• Video chuyên sâu: 7 credits
• Video premium: 10 credits
"""

BUY_PACKAGE_TEXT = """
🛒 MUA CREDIT

Vui lòng chuyển khoản theo gói bạn muốn mua.
Sau khi chuyển khoản, gửi ảnh bill cho admin để được cộng credit.

Nội dung chuyển khoản:
AI VIDEO BOT + Telegram username của bạn

Ví dụ:
AI VIDEO BOT @username
"""

GUIDE_TEXT = """
📚 HƯỚNG DẪN DÙNG BOT

Cách tạo video:
/makevideo chủ đề video

Ví dụ tốt:
/makevideo kể chuyện về lòng kiên trì theo phong cách hoạt hình, có chiều sâu

Mẹo:
• Chủ đề càng rõ, video càng hay
• Có thể ghi phong cách: cinematic, hoạt hình, giáo dục, marketing
• Không gửi lại lệnh nhiều lần khi bot đang xử lý
"""

SUPPORT_TEXT = """
🆘 HỖ TRỢ

Nếu cần mua gói, cộng credit hoặc báo lỗi, chọn một trong các cách liên hệ:

📱 Gọi hotline: 0933322969
👍 Facebook: facebook.com/nguyen.john.707903
💬 Hoặc nhắn trực tiếp admin qua Telegram
"""

QUALITY_TEXT = """
⚙️ CHỌN CHẤT LƯỢNG VIDEO

Standard
• Nhanh hơn
• 60–90 giây
• 4 credits

Deep
• Kịch bản sâu hơn
• 90–150 giây
• 7 credits

Premium
• Hình ảnh cinematic
• Chất lượng cao hơn
• 10 credits
"""

QUALITY_LABELS = {
    "standard": "Standard",
    "deep": "Deep",
    "premium": "Premium",
}

QUALITY_TO_MODE = {
    "standard": "fact",
    "deep": "deep",
    "premium": "premium",
}

VIDEO_TYPE_OPTIONS = {
    "quick": {
        "label": "Video nhanh",
        "mode": "quick",
        "command": "/quickvideo",
        "cost": 2,
        "example": "3 bài học về kỷ luật cá nhân",
        "description": "Phù hợp test ý tưởng nhanh, ít tốn credit.",
    },
    "standard": {
        "label": "Video tiêu chuẩn",
        "mode": "fact",
        "command": "/makevideo",
        "cost": 4,
        "example": "hố đen hoạt động như thế nào",
        "description": "Phù hợp video kiến thức, giải thích, giáo dục.",
    },
    "deep": {
        "label": "Video chuyên sâu",
        "mode": "deep",
        "command": "/makevideo",
        "cost": 7,
        "example": "vì sao người trẻ dễ mất phương hướng sau khi ra trường",
        "description": "Kịch bản sâu hơn, nhiều cảnh hơn, phù hợp nội dung nghiêm túc.",
    },
    "premium": {
        "label": "Video premium",
        "mode": "premium",
        "command": "/makevideo",
        "cost": 10,
        "example": "một thành phố tương lai nơi con người sống cùng AI",
        "description": "Ưu tiên chất lượng cinematic và trải nghiệm cao hơn.",
    },
    "story": {
        "label": "Video kể chuyện",
        "mode": "story",
        "command": "/storyvideo",
        "cost": 4,
        "example": "hành trình của một người vượt qua thất bại đầu đời",
        "description": "Phù hợp nội dung có nhân vật, biến cố và thông điệp.",
    },
}


def _ensure_menu_user(update: Update) -> dict | None:
    user = update.effective_user
    if not user:
        return None
    ensure_user(user.id, user.username, user.first_name)
    return get_user(user.id)


async def _edit_or_reply(update: Update, text: str, reply_markup=None) -> None:
    query = update.callback_query
    if query:
        try:
            await query.edit_message_text(text, reply_markup=reply_markup)
            return
        except BadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return
            logger.warning("menu_edit_failed_fallback_to_reply error=%s", exc, exc_info=True)
            if query.message:
                await query.message.reply_text(text, reply_markup=reply_markup)
                return
        except Exception:
            logger.exception("menu_edit_failed_fallback_to_reply")
            if query.message:
                await query.message.reply_text(text, reply_markup=reply_markup)
                return

    message = update.effective_message
    if message:
        await message.reply_text(text, reply_markup=reply_markup)


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _ensure_menu_user(update)

    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    await _edit_or_reply(update, MAIN_MENU_TEXT, reply_markup=main_menu_keyboard())


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = _ensure_menu_user(update)
    if not user:
        await _edit_or_reply(update, "Không xác định được tài khoản Telegram.")
        return

    await _edit_or_reply(update, _profile_text(user))


def _balance_text(user: dict) -> str:
    return (
        "💰 CREDIT CỦA BẠN\n\n"
        f"Gói hiện tại: {user['package_name']}\n"
        f"Số credit còn lại: {user['credit_balance']} credits"
    )


def _profile_text(user: dict) -> str:
    username = f"@{user['username']}" if user["username"] else "Không có"
    first_name = user["first_name"] or "Không có"
    return (
        "👤 TÀI KHOẢN\n\n"
        f"ID Telegram: {user['telegram_user_id']}\n"
        f"Username: {username}\n"
        f"Tên: {first_name}\n"
        f"Gói: {user['package_name']}\n"
        f"Role: {user['role']}\n"
        f"Credit: {user['credit_balance']}\n"
        f"Ngày tạo: {user['created_at']}"
    )


async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    try:
        await query.answer()
    except Exception:
        pass

    user = _ensure_menu_user(update)
    if not user:
        await _edit_or_reply(
            update,
            "Không tìm thấy tài khoản. Vui lòng bấm /start để khởi tạo lại.",
            reply_markup=back_menu_keyboard(),
        )
        return

    data = query.data

    try:
        if data == "main_menu":
            await _edit_or_reply(update, MAIN_MENU_TEXT, reply_markup=main_menu_keyboard())
            return

        if data == "create_video":
            await _edit_or_reply(update, CREATE_VIDEO_TEXT, reply_markup=video_type_keyboard())
            return

        if data.startswith("video_type_"):
            video_type = data.replace("video_type_", "", 1)
            option = VIDEO_TYPE_OPTIONS.get(video_type)
            if not option:
                await _edit_or_reply(update, "Loại video không hợp lệ.", reply_markup=video_type_keyboard())
                return

            context.user_data["video_type"] = video_type
            context.user_data["video_mode"] = option["mode"]
            context.user_data["video_quality"] = (
                "standard" if option["mode"] == "fact" else option["mode"]
            )

            await _edit_or_reply(
                update,
                (
                    f"✅ Đã chọn: {option['label']}\n\n"
                    f"Chi phí: {option['cost']} credits\n"
                    f"Ghi chú: {option['description']}\n\n"
                    "Gửi lệnh theo mẫu:\n"
                    f"{option['command']} chủ đề của bạn\n\n"
                    "Ví dụ:\n"
                    f"{option['command']} {option['example']}\n\n"
                    "Mẹo: chủ đề càng rõ, video càng hay."
                ),
                reply_markup=video_type_keyboard(),
            )
            return

        if data == "pricing":
            await _edit_or_reply(update, PRICING_MENU_TEXT, reply_markup=pricing_keyboard())
            return

        if data == "buy_package":
            await _edit_or_reply(
                update,
                BUY_PACKAGE_TEXT,
                reply_markup=buy_package_keyboard(),
            )
            return

        if data == "balance":
            if not user:
                await _edit_or_reply(update, "Không xác định được tài khoản Telegram.")
                return
            await _edit_or_reply(update, _balance_text(user), reply_markup=back_menu_keyboard())
            return

        if data == "profile":
            if not user:
                await _edit_or_reply(update, "Không xác định được tài khoản Telegram.")
                return
            await _edit_or_reply(update, _profile_text(user), reply_markup=back_menu_keyboard())
            return

        if data == "guide":
            await _edit_or_reply(update, GUIDE_TEXT, reply_markup=back_menu_keyboard())
            return

        if data == "support":
            await _edit_or_reply(
                update,
                SUPPORT_TEXT,
                reply_markup=support_keyboard(),
            )
            return

        if data == "quality_menu":
            await _edit_or_reply(update, QUALITY_TEXT, reply_markup=quality_keyboard())
            return

        if data.startswith("quality_"):
            quality = data.replace("quality_", "", 1)
            if quality not in QUALITY_LABELS:
                await _edit_or_reply(update, "Chất lượng không hợp lệ.", reply_markup=back_menu_keyboard())
                return

            context.user_data["video_quality"] = quality
            context.user_data["video_mode"] = QUALITY_TO_MODE[quality]
            await _edit_or_reply(
                update,
                (
                    f"✅ Đã chọn chất lượng: {QUALITY_LABELS[quality]}\n\n"
                    "Bây giờ bạn có thể tạo video bằng lệnh:\n\n"
                    "/makevideo chủ đề video của bạn"
                ),
                reply_markup=back_menu_keyboard(),
            )
            return

        await _edit_or_reply(update, "Chức năng này chưa được hỗ trợ.", reply_markup=back_menu_keyboard())
    except Exception:
        logger.exception("menu_callback_failed data=%s", data)
        await _edit_or_reply(
            update,
            "Có lỗi khi xử lý menu. Vui lòng thử lại hoặc bấm /start.",
            reply_markup=back_menu_keyboard(),
        )
