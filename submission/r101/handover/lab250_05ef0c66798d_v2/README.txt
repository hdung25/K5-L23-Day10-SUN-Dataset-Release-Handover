Release: lab250_05ef0c66798d_v2
Parent: lab250_05ef0c66798d
Số ảnh: 242
Số nhãn: 1679
Guideline: v1.2 (J01-J04), v1.3 (J05-J10)
QC v1: 19/250 = 7,6%
Kết luận v1: Hold — 7,6% ảnh lỗi, vượt ngưỡng 2%
Kết luận v2: Release — tách 8 ảnh lỗi nhãn detection sang rework, sửa hash, guideline và split ngay trong v2; ảnh lỗi panoptic ở lại vì nhãn detection đúng
Ghi chú: không ghi đè v1: delivery/ giữ nguyên, v2 là bản mới có lô cha lab250_05ef0c66798d; 8 ảnh lỗi nhãn detection hoặc thiếu file tách sang rework_queue.csv, giao lại đúng người gán/người kiểm của job (A01/Q01: 1 ảnh, A01/Q03: 1 ảnh, A03/Q01: 1 ảnh, A03/Q02: 1 ảnh, A04/Q03: 1 ảnh, A05/Q01: 1 ảnh, A05/Q03: 2 ảnh); hash: 2 ảnh wrong_hash đã mở kiểm, ảnh còn nguyên nên giữ lại và ghi sha256 thật trong manifest.csv (000000021879, 000000024919); guideline: truyvet.csv lấy phiên bản theo job trong jobs.csv, không theo metadata ảnh (sửa 2 ảnh: 000000001675, 000000007108); split: 1 cảnh rò train/val (scene_752) đưa cả cảnh về split mà đa số ảnh của cảnh đang dùng; lỗi chỉ ở panoptic, nhãn detection vẫn đúng nên ảnh ở lại v2, báo team panoptic: 000000006213 (instance_merge), 000000009590 (invalid_category_id), 000000012062 (thing_overlap), 000000012670 (category_swap), 000000018193 (thing_overlap), 000000018575 (category_swap)
