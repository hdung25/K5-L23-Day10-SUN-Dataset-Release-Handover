# Nhóm SUN

- Tên team trên trang nộp đề ẩn: `NHOM99` (trang bắt buộc dạng NHOMxx)
- Seed luyện tập: 2611 (`runs/r2611`, release_id v1 `lab250_d9d3c58cd7e6`)
- Repo: https://github.com/hdung25/K5-L23-Day10-SUN-Dataset-Release-Handover
- Bảng phân công và theo dõi tiến độ: [Day 10 Lab - Phân công nhóm](https://docs.google.com/spreadsheets/d/1HsmcXXUwMi6U5iYGJdgPCHjrDczQjNvcDeE7YtsKsHc/edit?usp=drivesdk)

| Họ và tên | MSHV | Tài khoản GitHub | Phần chính |
|---|---|---|---|
| Hà Huy Dũng | 2A202603271 | hdung25 | Trưởng nhóm: chuẩn bị (P0), quyết định + lineage (P3), tích hợp, đề ẩn, nộp bài |
| Triệu Hoàng Hiếu | 2A202603294 | hieuwewe123 | Validator luật (P1-1 đến P1-3): khung `validate.py`, lỗi file và detection (`missing_image`, `wrong_hash`, `invalid_class`, `bbox_out_of_bounds`, `duplicate_box`) |
| Luong Duc Manh | 2A202603155 | ldmanh610 | Validator luật: metadata và panoptic (`scene_leak`, `guideline_mismatch`, `invalid_category_id`, `thing_overlap`); kiểm F1 trên nhiều seed và lô sạch |
| Do Phuong Manh | 2A202603148 | manhtotbung | Đối chiếu detection ↔ panoptic, sinh `candidates.json`, đo lô sạch và chọn ngưỡng |
| Quốc Anh | 2A202603286 | QuocAnh-bit | Công cụ xem ảnh, chia hàng đợi và gộp `review_log.csv`, truy vết ticket (`trace.json`) |
| Nguyen Thi Minh Trang | 2A202603107 | MTrang0702 | Bàn giao lô v2 (rework, manifest, label summary, truyvet, README, đóng gói), bảo mật (`security.md`) |

Cả nhóm cùng xem ảnh ở Pha 2 và ở đề ẩn.
