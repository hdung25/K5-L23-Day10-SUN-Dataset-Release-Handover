Release: lab250_d9d3c58cd7e6_v2
Parent: lab250_d9d3c58cd7e6
Số ảnh: 243
Số nhãn: 1685
Guideline: v1.2 (J01-J03), v1.3 (J04-J10)
QC v1: 15/250 = 6,0%
Kết luận v1: Hold — 6,0% ảnh lỗi, vượt ngưỡng 2%
Kết luận v2: Release — tách 7 ảnh lỗi nhãn detection sang rework, sửa hash, guideline và split ngay trong v2; ảnh lỗi panoptic ở lại vì nhãn detection đúng
Ghi chú: không ghi đè v1: delivery/ giữ nguyên, v2 là bản mới có lô cha lab250_d9d3c58cd7e6; 7 ảnh lỗi nhãn detection hoặc thiếu file tách sang rework_queue.csv, giao lại đúng người gán/người kiểm của job (A01/Q03: 1 ảnh, A02/Q03: 1 ảnh, A03/Q01: 1 ảnh, A04/Q03: 1 ảnh, A05/Q02: 2 ảnh, A05/Q03: 1 ảnh); hash: 1 ảnh wrong_hash đã mở kiểm, ảnh còn nguyên nên giữ lại và ghi sha256 thật trong manifest.csv (000000017899); guideline: truyvet.csv lấy phiên bản theo job trong jobs.csv, không theo metadata ảnh (sửa 1 ảnh: 000000015597); split: 1 cảnh rò train/val (scene_704) đưa cả cảnh về split mà đa số ảnh của cảnh đang dùng; lỗi chỉ ở panoptic, nhãn detection vẫn đúng nên ảnh ở lại v2, báo team panoptic: 000000000776 (thing_overlap), 000000002153 (thing_overlap), 000000005001 (category_swap), 000000018770 (category_swap), 000000025057 (instance_merge)
