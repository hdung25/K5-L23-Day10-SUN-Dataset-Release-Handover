Release: lab250_93c1541682ba_v2
Parent: lab250_93c1541682ba
Số ảnh: 239
Số nhãn: 1638
Guideline: v1.2 (J01-J03), v1.3 (J04-J10)
QC v1: 21/250 = 8,4%
Kết luận v1: Hold — 8,4% ảnh lỗi, vượt ngưỡng 2%
Kết luận v2: Release — tách 11 ảnh lỗi nhãn detection sang rework, sửa hash, guideline và split ngay trong v2; ảnh lỗi panoptic ở lại vì nhãn detection đúng
Ghi chú: không ghi đè v1: delivery/ giữ nguyên, v2 là bản mới có lô cha lab250_93c1541682ba; 11 ảnh lỗi nhãn detection hoặc thiếu file tách sang rework_queue.csv, giao lại đúng người gán/người kiểm của job (A01/Q02: 1 ảnh, A02/Q01: 1 ảnh, A02/Q03: 2 ảnh, A03/Q01: 3 ảnh, A03/Q02: 3 ảnh, A04/Q01: 1 ảnh); hash: 2 ảnh wrong_hash đã mở kiểm, ảnh còn nguyên nên giữ lại và ghi sha256 thật trong manifest.csv (000000007784, 000000010977); guideline: truyvet.csv lấy phiên bản theo job trong jobs.csv, không theo metadata ảnh (sửa 1 ảnh: 000000005529); split: 1 cảnh rò train/val (scene_587) đưa cả cảnh về split mà đa số ảnh của cảnh đang dùng; lỗi chỉ ở panoptic, nhãn detection vẫn đúng nên ảnh ở lại v2, báo team panoptic: 000000006614 (thing_overlap), 000000006763 (thing_overlap), 000000012639 (invalid_category_id), 000000012670 (invalid_category_id), 000000013659 (category_swap), 000000020059 (instance_merge)
