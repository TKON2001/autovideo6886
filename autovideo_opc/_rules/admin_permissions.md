# Admin Permissions

## Nguon Quyen Admin

Admin duoc xac dinh bang bien moi truong:

```env
ADMIN_TELEGRAM_IDS=123456789,987654321
```

## Lenh Admin

- `/users`
- `/user <telegram_user_id>`
- `/balanceof <telegram_user_id>`
- `/addcredits <telegram_user_id> <credits>`
- `/setcredits <telegram_user_id> <credits>`
- `/setpackage <telegram_user_id> <package_name>`

## Bao Mat

- User khong nam trong `ADMIN_TELEGRAM_IDS` phai nhan:

```text
Bạn không có quyền dùng lệnh này.
```

- Khong dua token bot hoac OpenAI key vao `.env.example`.
- Khong public database co thong tin user neu chua an danh.
