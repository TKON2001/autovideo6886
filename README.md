# AI Video Telegram Bot

MVP Telegram bot tao video ngan theo pipeline:

Telegram command -> OpenAI script -> OpenAI voice -> Pillow slides -> MoviePy MP4 -> Telegram video.

## Cai dat

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Neu dang dung `cmd.exe` thay vi PowerShell:

```cmd
copy .env.example .env
```

Mo `.env` va dien:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_openai_api_key
ADMIN_TELEGRAM_IDS=123456789
PAYMENT_BANK_NAME=Ten ngan hang
PAYMENT_ACCOUNT_NUMBER=So tai khoan
PAYMENT_ACCOUNT_NAME=Ten chu tai khoan
PAYMENT_ADMIN_CONTACT=@admin_username
PAYMENT_TRANSFER_PREFIX=AIVIDEO
```

Lay Telegram ID bang lenh `/myid`, sau do them ID admin vao `.env`.
Neu co nhieu admin, ngan cach bang dau phay:

```env
ADMIN_TELEGRAM_IDS=123456789,987654321
```

## Chay bot

```powershell
.venv\Scripts\python main.py
```

Trong Telegram:

```text
/start
/quickvideo lich su hinh thanh trai dat
```

`/start` se mo menu nut bam:

```text
🎬 Tạo Video
💎 Bảng Giá
💰 Credit Của Tôi
👤 Tài Khoản
📚 Hướng Dẫn
🆘 Hỗ Trợ
⚙️ Chọn Chất Lượng Video
```

Nut `🎬 Tạo Video` se mo tiep menu chon loai video:

```text
⚡ Nhanh - 2 credits
🎯 Tiêu chuẩn - 4 credits
🎬 Chuyên sâu - 7 credits
✨ Premium - 10 credits
📖 Kể chuyện - 4 credits
```

Sau khi chon loai video, bot luu lua chon vao session Telegram cua user va hien
lenh mau de gui chu de.

Nut chon chat luong se luu vao session Telegram cua user. Sau khi chon Standard,
Deep hoac Premium, user co the dung `/makevideo <chu de>` va bot se dung chat
luong da chon.

## Lenh Telegram

Lenh huong dan:

```text
/start
/help
/commands
/examples
/tips
/pricing
/balance
/profile
/myid
/status
```

Lenh tao video:

```text
/makevideo <chu de>
/video <chu de>
/quickvideo <chu de>
/storyvideo <chu de>
/factvideo <chu de>
/premiumvideo <chu de>
```

Y nghia tung lenh:

- `/makevideo`: tao video chuyen sau, 8-12 canh, phu hop video 90-150 giay.
- `/video`: alias cua `/makevideo`.
- `/quickvideo`: tao video ngan, 4-6 canh, tiet kiem quota hon.
- `/storyvideo`: tao video co cau truc ke chuyen, phu hop hanh trinh, bien co, bai hoc.
- `/factvideo`: tao video giai thich kien thuc, lich su, khoa hoc, xa hoi.
- `/premiumvideo`: tao video premium dien anh, ton nhieu credit hon.

Chi phi credit:

- Video ngan `/quickvideo`: 2 credits.
- Video tieu chuan `/factvideo`, `/storyvideo`: 4 credits.
- Video chuyen sau `/makevideo`, `/video`: 7 credits.
- Video premium `/premiumvideo`: 10 credits.

Lenh credit va thanh toan:

```text
/pricing
/balance
/buy starter
/buy creator
/buy pro
/buy agency
/addcredits <telegram_user_id> <credits>
```

`/addcredits` chi dung duoc voi admin nam trong `ADMIN_TELEGRAM_IDS`.
Hien tai chua tich hop cong thanh toan that. Bot chi hien huong dan:
"Chuyen khoan xong gui anh bill cho admin de cong credit."

Thong tin chuyen khoan hien trong `/buy` va `/pricing` lay tu `.env`:

```env
PAYMENT_BANK_NAME=Ten ngan hang
PAYMENT_ACCOUNT_NUMBER=So tai khoan
PAYMENT_ACCOUNT_NAME=Ten chu tai khoan
PAYMENT_ADMIN_CONTACT=@admin_username
PAYMENT_TRANSFER_PREFIX=AIVIDEO
```

Neu nguoi dung chi bam `/buy`, bot se hien danh sach goi va thong tin chuyen
khoan chung. Neu dung `/buy starter`, `/buy creator`, `/buy pro` hoac
`/buy agency`, bot se tao ma don va hien noi dung chuyen khoan rieng.

Lenh admin:

```text
/users
/user <telegram_user_id>
/balanceof <telegram_user_id>
/addcredits <telegram_user_id> <credits>
/setcredits <telegram_user_id> <credits>
/setpackage <telegram_user_id> <package_name>
```

Vi du:

```text
/users
/user 123456789
/balanceof 123456789
/addcredits 123456789 40
/setcredits 123456789 40
/setpackage 123456789 starter
```

Package hop le:

```text
trial
starter
creator
pro
agency
```

User khong nam trong `ADMIN_TELEGRAM_IDS` se nhan:

```text
Bạn không có quyền dùng lệnh này.
```

Vi du:

```text
/quickvideo 5 sai lam khien nguoi tre mat dong luc
/makevideo vi sao nen van minh La Ma sup do
/storyvideo hanh trinh cua mot nguoi tu that bai den ky luat
/factvideo ho den hoat dong nhu the nao
/premiumvideo mot thanh pho tuong lai noi con nguoi song cung AI
/makevideo vi sao AI dang thay doi cach con nguoi lam viec
```

## Bang gia

- Starter: 200.000đ = 40 credits.
- Creator: 500.000đ = 120 credits.
- Pro: 1.000.000đ = 300 credits.
- Agency: 2.000.000đ = 700 credits.

Nguoi dung moi duoc tang 2 trial credits khi dung `/start` lan dau.

## Cach viet chu de hay

Nen viet ro goc nhin va doi tuong nguoi xem.

Chua tot:

```text
/makevideo thanh cong
```

Tot hon:

```text
/makevideo vi sao nguoi tre de mat phuong huong sau khi ra truong
```

Cong thuc goi y:

```text
/makevideo vi sao <van de> xay ra va no thay doi <doi tuong> nhu the nao
/factvideo <khai niem> hoat dong nhu the nao va vi sao no quan trong
/storyvideo hanh trinh cua <nhan vat/nhom nguoi> vuot qua <bien co>
```

## File chinh

- `main.py`: Telegram polling, command `/start`, `/makevideo`.
- `menu.py`: Inline keyboard cho menu nut bam.
- `handlers_menu.py`: callback handlers cho cac man hinh menu.
- `ai_service.py`: tao video plan va voice bang OpenAI API.
- `video_service.py`: tao slide bang Pillow va ghep MP4 bang MoviePy.
- `db_service.py`: SQLite users, purchases, credit logs, package va credit balance.
- `progress.py`: hien tien trinh va ETA khi tao video.
- `config.py`: doc `.env` va validate token.

Video tao ra nam trong `output/<job_id>/final_video.mp4`.
Anh AI nam trong `output/<job_id>/images/`.
Slide da render nam trong `output/<job_id>/slides/`.
Database nam trong `bot_data.sqlite3`.

## Tao anh AI

Mac dinh bot se thu tao anh AI cho tung canh bang `image_prompt`, sau do phu
caption len anh. Neu tao anh loi, bot fallback ve slide chu.

Tuy chinh trong `.env`:

```env
OPENAI_IMAGE_ENABLED=true
OPENAI_IMAGE_MODEL=gpt-image-1-mini
OPENAI_IMAGE_SIZE=1024x1536
OPENAI_IMAGE_QUALITY=medium
```

Neu muon quay ve slide chu de tiet kiem quota:

```env
OPENAI_IMAGE_ENABLED=false
```

## Chat luong video

Bot render video doc 9:16 cho TikTok/Reels/Shorts:

- Resolution: 1080x1920.
- FPS: 30.
- Codec: H.264 `libx264`.
- Audio: AAC.
- Bitrate:
  - standard: 5000k.
  - deep: 8000k.
  - premium: 10000k.

Moi canh co slow zoom va fade in/out nhe de tranh cam giac anh tinh.
Caption duoc dat o lower third voi nen toi ban trong suot va shadow de de doc.

Neu muon them nhac nen, dat file tai:

```text
assets/background_music.mp3
```

Bot se tu dong tron nhac nen o muc am luong thap. Neu file khong ton tai,
bot bo qua ma khong bao loi.

## Tien trinh tao video

Khi user chay lenh tao video, bot se cap nhat cung mot tin nhan theo cac buoc:

- Dang phan tich chu de.
- Dang viet kich ban.
- Dang tao anh minh hoa.
- Dang tao giong doc.
- Dang render video.
- Dang gui video.

ETA chi la uoc tinh, khong phai thoi gian chinh xac. Cong thuc mac dinh:

```text
20 giay script + 20 giay moi canh tao anh + 8 giay moi canh tao voice
+ thoi gian render uoc tinh theo so canh + 10 giay gui video
```

Render 1080x1920 tren may local Windows co the cham hon ETA neu CPU yeu.
"# AutoVideo" 
