from telegram import InlineKeyboardButton, InlineKeyboardMarkup

ADMIN_TELEGRAM_URL = "https://t.me/tungnt201"  # sửa thành username admin thật của bạn


def _admin_url(admin_contact: str | None = None) -> str | None:
    contact = (admin_contact or "").strip()
    if contact and contact.lower() not in {"admin", "chưa cấu hình", "chua cau hinh"}:
        if contact.startswith("http://") or contact.startswith("https://"):
            return contact
        if contact.startswith("@"):
            return f"https://t.me/{contact[1:]}"
        return f"https://t.me/{contact}"

    return ADMIN_TELEGRAM_URL


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 Tạo video", callback_data="create_video"),
            InlineKeyboardButton("💎 Bảng giá", callback_data="pricing"),
        ],
        [
            InlineKeyboardButton("💰 Credit của tôi", callback_data="balance"),
            InlineKeyboardButton("👤 Tài khoản", callback_data="profile"),
        ],
        [
            InlineKeyboardButton("📚 Hướng dẫn", callback_data="guide"),
            InlineKeyboardButton("🛟 Hỗ trợ", callback_data="support"),
        ],
        [
            InlineKeyboardButton("⚙️ Chọn chất lượng", callback_data="quality_menu"),
        ],
    ])


def back_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Quay lại menu", callback_data="main_menu")]]
    )


def video_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Nhanh - 2 credits", callback_data="video_type_quick")],
        [InlineKeyboardButton("🎯 Tiêu chuẩn - 4 credits", callback_data="video_type_standard")],
        [InlineKeyboardButton("🎬 Chuyên sâu - 7 credits", callback_data="video_type_deep")],
        [InlineKeyboardButton("✨ Premium - 10 credits", callback_data="video_type_premium")],
        [InlineKeyboardButton("📖 Kể chuyện - 4 credits", callback_data="video_type_story")],
        [InlineKeyboardButton("⬅️ Quay lại menu", callback_data="main_menu")],
    ])


def pricing_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Mua gói", callback_data="buy_package")],
        [InlineKeyboardButton("⬅️ Quay lại menu", callback_data="main_menu")],
    ])


def support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Liên hệ admin", url=_admin_url())],
        [InlineKeyboardButton("⬅️ Quay lại menu", callback_data="main_menu")],
    ])


def buy_package_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Liên hệ admin", url=_admin_url())],
        [InlineKeyboardButton("⬅️ Quay lại menu", callback_data="main_menu")],
    ])


def quality_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Standard", callback_data="quality_standard"),
            InlineKeyboardButton("Deep", callback_data="quality_deep"),
            InlineKeyboardButton("Premium", callback_data="quality_premium"),
        ],
        [InlineKeyboardButton("⬅️ Quay lại menu", callback_data="main_menu")],
    ])
