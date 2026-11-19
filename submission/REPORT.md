# Báo cáo nhóm SUN

Seed luyện tập 2611, lô v1 `lab250_d9d3c58cd7e6`. Số liệu dưới đây chạy trên máy nhóm bằng `scripts/score_findings.py` (chỉ in F1 làm tròn một chữ số), không đọc `_private/`.

## 1. Số liệu luyện tập

| Lô | F1 lỗi luật | F1 lỗi gán nhãn (cross_check_review) | F1 tổng | Ghi chú |
|---|---|---|---|---|
| r2611 (seed nhóm) | ≈ 1,0 | ≈ 0,9 | ≈ 1,0 | sau khi xem ảnh 9 ứng viên |
| r101 (seed thêm) | ≈ 1,0 | chưa review | | chỉ kiểm luật |
| r202 (seed thêm) | ≈ 1,0 | chưa review | | chỉ kiểm luật |
| clean (`--no-faults`, 50 ảnh calib) | 0 lỗi luật báo ra | 0 ứng viên | | không báo thừa |

- Truy vết trên cả 3 seed: tier_a ≈ 1,0 · tier_b ≈ 1,0 · notify ≈ 1,0.
- Số ứng viên trên lô sạch: **0**. Hàng đợi trên seed 2611: **9 ảnh** (6 confirmed, 3 rejected); r101: 8 ảnh; r202: 11 ảnh.
- Cách chọn ngưỡng (không dùng `_private`): đếm, với mỗi segment thing không crowd, tỉ lệ pixel của segment nằm trong box detection cùng lớp. Trên lô sạch 435/436 segment có tỉ lệ ≥ 0,999; segment duy nhất thấp hơn là một người 299 pixel (0,876). Vì vậy:
  - `SHARE_OK = 0,98`: segment có ≥ 98% pixel trong một box cùng lớp coi là khớp;
  - `MIN_AREA = 300` pixel cho phía segment (vật nhỏ hơn quá ít pixel để kết luận);
  - thêm một vòng kiểm theo phía box, không giới hạn kích thước: box nào không chứa trọn segment cùng lớp thì xem segment khác lớp nằm trong nó (bắt swap trên vật nhỏ / bị che);
  - bỏ qua trường hợp COCO gán hai nhãn cho cùng một vật (cup + wine glass, bus + truck, hot dog + sandwich, bowl + cup, bottle + vase): nếu segment đã có box đúng lớp của nó thì box lớp kia là nhãn kép, không phải swap. Năm ca này lặp lại ở mọi seed.
  - IoU giữa hai bbox không đủ: ca `000000025057` có IoU box/segment 0,9 nhưng 2,4% pixel của segment nằm ngoài box, đúng bằng phần người nhỏ đứng xa bị gộp vào (instance_merge).

## 2. Vì sao báo hết ứng viên làm F1 giảm?

Điểm là F1 trên cặp (type, target), báo thừa bị trừ như bỏ sót. Trên seed 2611, nếu đưa cả 9 ứng viên vào `errors.json` mà không xem ảnh, F1 lỗi gán nhãn chỉ còn **≈ 0,5** (đoán mọi ca lệch lớp là class_swap) hoặc **≈ 0,6** (đoán là category_swap); sau khi xem ảnh là **≈ 0,9**. Có hai lý do:
1. 3/9 ứng viên là lệch tự nhiên của COCO (`000000000872`, `000000001818`, `000000012748`; lặp lại y hệt ở seed 101 và 202), báo vào thành false positive.
2. Khi detection và panoptic bất đồng về lớp, chỉ ảnh mới cho biết bên nào sai: 1 ca detection sai (mèo bị ghi donut → class_swap), 2 ca panoptic sai (người bị ghi keyboard, cà vạt bị ghi train → category_swap). Đoán một loại cho tất cả thì sai type, mất cả TP lẫn thêm FP. Ngoài ra ứng viên `000000025057` do máy gợi ý là bbox_drift, xem ảnh mới thấy là instance_merge.

## 3. Quyết định và lineage

- QC v1: **15/250 = 6,0%** ảnh (hoặc cảnh, với scene_leak) có lỗi, trên ngưỡng 2% của Day 7 ⇒ **HOLD** v1 (`lineage.py record --event decision --decision HOLD`).
- `lineage.py impact` cho `R-021: affected=True action=review_or_retrain`. Model R-021 đã học từ v1, trong đó có box sai lớp, box lệch, vật thiếu box. Sửa dataset thành v2 không thay đổi trọng số đã học, nên R-021 phải được đánh giá lại trên dữ liệu đã sửa, và nếu lỗi ảnh hưởng (ví dụ lớp cup bị bỏ sót, xem mục 5) thì train lại trên v2.
- v2 `lab250_d9d3c58cd7e6_v2` được ghi `release --parent lab250_d9d3c58cd7e6`: 243 ảnh, 1685 nhãn, 7 ảnh sang rework.

## 4. Hash chứng minh gì, không chứng minh gì?

- **Chứng minh:** bytes của từng file trong v2 đúng như lúc đóng gói (manifest.csv + `.sha256` của zip), nên phát hiện được file bị sửa, hỏng hoặc thay sau khi bàn giao; `release_id` v1 (hash của manifest.json + metadata.json) không đổi chứng tỏ nhóm không ghi đè v1. Ảnh `000000017899` có hash trong manifest v1 sai nhưng ảnh mở được và đúng nội dung, nên giữ lại và ghi hash thật.
- **Không chứng minh:** nhãn đúng (một box sai lớp vẫn có hash hợp lệ), ảnh phù hợp để dùng (khuôn mặt, bản quyền), ai đã tạo hay duyệt file, và cũng không chống được người có quyền sửa cả file lẫn manifest rồi tính lại hash: phải giữ `.sha256` ở chỗ riêng và có lineage.

## 5. Truy vết

- Ticket nêu `scene_115`, `scene_704`: model bỏ sót `cup` bị che hoặc ở mép ảnh. Changelog: từ v1.3 lớp `cup` bị che > 50% hoặc cắt mép vẫn phải gán box, v1.2 cho phép bỏ qua.
- Tiêu chí: ảnh thuộc **job** có guideline cũ (v1.2, J01–J03 theo `jobs.csv`) và có ít nhất một box detection lớp `cup` trong `labels/`. Ảnh trong hai cảnh được báo là tier_a (4 ảnh), phần còn lại là tier_b (3 ảnh). notify = người gán và người kiểm của các job đó: A01, Q03.
- Lấy guideline theo job chứ không theo `metadata.json` của ảnh vì giá trị ở ảnh chính là thứ có thể sai: lô này có `guideline_mismatch` ở `000000015597`. Công cụ: `tools/trace_query.py` (đọc ticket và changelog, không gõ tay tên lớp hay cảnh).

## 6. Bug hoặc điểm chưa rõ trong lab

- Windows: `scripts/run_lab.py` gọi script con không kèm `-X utf8`, in tiếng Việt ra console cp1252 nên lỗi `UnicodeEncodeError` và để lại `runs/r<seed>` dở dang. Cách tránh: đặt `$env:PYTHONUTF8=1` trước khi chạy, xoá thư mục dở rồi chạy lại.
- Lệch tự nhiên của COCO trong pool luyện tập lặp lại ở mọi seed (3 ca lệch box/segment và 5 ca nhãn kép), nên nhóm dùng việc "lặp lại ở seed khác" làm một bằng chứng phụ khi ghi `rejected`.
