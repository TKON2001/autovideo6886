# AutoVideo OPC

AutoVideo OPC la he dieu hanh van hanh cho Telegram AI Video Bot. Thu muc nay dong vai tro nhu bo nao quy trinh cua mot xuong san xuat video tu dong: tiep nhan yeu cau, dinh huong kich ban, tao hinh, tao voice, render video, kiem tra chat luong, tinh credit va ho tro user.

OPC khong thay the code bot. OPC la lop tai lieu dieu hanh giup bot va founder co cung mot chuan lam viec.

## Founder Van Hanh Bot Nhu Mot Xuong Video Tu Dong

Founder khong nen xem bot chi la cong cu tao video. Bot can duoc van hanh nhu mot day chuyen san xuat:

1. User gui y tuong.
2. Intake chuan hoa yeu cau.
3. Script Director bien y tuong thanh kich ban co cau truc.
4. Visual Director tao prompt hinh anh dung chuan.
5. Voice Director kiem soat giong doc.
6. Video Editor ghep hinh, subtitle, voice va nhac nen.
7. Quality Controller kiem tra video truoc khi gui.
8. Billing Admin quan ly credit va goi mua.
9. Support xu ly loi, bill va cau hoi.

## AI Workers

- Intake: lam ro y tuong, doi tuong xem, phong cach, muc tieu.
- Script: tao hook, canh, narration, caption va thong diep.
- Visual: tao prompt hinh doc 9:16, cinematic, khong co chu trong anh.
- Voice: dieu chinh nhac doc, cam xuc, do dai cau.
- Editor: render video doc, subtitle de doc, audio can bang.
- QC: kiem tra file, dinh dang, mobile layout, credit, loi.
- Billing: tao don, xac nhan bill, cong credit.
- Support: huong dan user, xu ly loi va chuyen cap khi can.

## KWSR Structure

AutoVideo OPC dung cau truc KWSR:

- Knowledge: kien thuc cot loi ve thuong hieu, gia, chat luong, style va khach hang.
- Workflow: SOP tung quy trinh van hanh.
- Skill/Agent: vai tro va trach nhiem cua tung worker.
- Rule: quy tac bat buoc de bot van hanh on dinh.

## SOP State Machine

Moi job video di qua cac trang thai:

```text
template -> input -> processing -> output -> archive
```

- template: mau quy trinh chuan.
- input: yeu cau user da duoc nhan.
- processing: bot dang tao script, anh, voice, render.
- output: video da render xong va san sang gui.
- archive: job da hoan tat, co the tra cuu lai.

## Cach OPC Cai Thien Chat Luong

OPC giup video tot hon vi moi thanh phan deu co chuan rieng:

- Kich ban co hook, cau truc va thong diep.
- Image prompt co bo cuc doc, anh sang, cam xuc va do chi tiet.
- Caption nam trong mobile safe zone, khong sat mep.
- Video khong co logo, watermark hoac badge canh.
- QC ngan viec gui file hong, file 0 byte, sai dinh dang.
- Billing va support co quy trinh ro, tranh cong credit nham.

## Nguyen Tac Van Hanh

- Lam video dung chuan 9:16 truoc khi them tinh nang moi.
- Khong tru credit neu video loi.
- Khong hua ETA chinh xac, chi hien uoc tinh.
- Khong gui video neu file chua qua QC.
- Khong sua gia, credit, package ma khong cap nhat pricing policy.
