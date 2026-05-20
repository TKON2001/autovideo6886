# SOP Error Handling

## Nguyen Tac

- Loi he thong khong duoc lam mat credit cua user.
- Loi can duoc bao ro bang tieng Viet.
- Khong de user nhin thay traceback dai neu khong can.

## Nhom Loi

### Loi OpenAI quota

Thong bao:

```text
Hệ thống AI đang không đủ quota hoặc billing. Credit chưa bị trừ.
```

### Loi JSON script

Thong bao:

```text
AI trả về kịch bản chưa đúng định dạng. Vui lòng thử lại với chủ đề ngắn và rõ hơn.
```

### Loi tao anh

Duoc phep fallback sang slide chu. Khong can fail ca job neu voice va render van chay.

### Loi voice

Fail job. Khong tru credit.

### Loi render

Fail job. Khong tru credit. Can kiem tra file MP4 co 0 byte hay khong.

### Loi gui Telegram

Khong tru credit neu video chua gui thanh cong.

## Log Can Co

- user id
- topic
- mode
- buoc loi
- error message
- output path neu co
