# Bảng làm việc của nhóm SUN

Bản gốc (ai có link đều sửa được): **[Day 10 Lab - Phân công nhóm](https://docs.google.com/spreadsheets/d/1HsmcXXUwMi6U5iYGJdgPCHjrDczQjNvcDeE7YtsKsHc/edit?usp=drivesdk)**

Thư mục này là bản chụp nội dung sheet lúc 19/11 18:23, mỗi tab một file CSV (GitHub hiển thị thành bảng). Ô tích được ghi là `x`.

| Tab | File | Nội dung |
|---|---|---|
| Phân công | [01_phan_cong.csv](01_phan_cong.csv) | việc theo pha P0–P6, người phụ trách, người hỗ trợ, trạng thái |
| Tiến độ cá nhân | [02_tien_do_ca_nhan.csv](02_tien_do_ca_nhan.csv) | mỗi người tích việc đã xong, so `release_id` trên máy với lô nhóm |
| Thành viên | [03_thanh_vien.csv](03_thanh_vien.csv) | họ tên, MSHV, vai trò |
| Số liệu | [04_so_lieu.csv](04_so_lieu.csv) | F1 từng seed, số ứng viên lô sạch, QC v1, số liệu lô v2 |
| Log chạy | [05_log_chay.csv](05_log_chay.csv) | lệnh đã chạy, kết quả, lỗi gặp và cách sửa |
| Review ảnh | [06_review_anh.csv](06_review_anh.csv) | từng ứng viên đã xem ảnh: verdict và ghi chú thấy gì |
| Note chung | [07_note_chung.csv](07_note_chung.csv) | quyết định, câu hỏi, việc giao cho từng người |
| Checklist nộp | [08_checklist_nop.csv](08_checklist_nop.csv) | các mục phải kiểm trước khi nộp |

Làm mới bản chụp: tải sheet dạng .xlsx (Tệp > Tải xuống > Microsoft Excel) rồi chạy `py tools/sheet_snapshot.py <file.xlsx>`.
