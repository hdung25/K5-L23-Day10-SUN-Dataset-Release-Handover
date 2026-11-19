# Báo cáo nhóm SUN

Seed luyện tập 2611, lô v1 `lab250_d9d3c58cd7e6`. Số liệu dưới đây chạy trên máy nhóm bằng `scripts/score_findings.py` (chỉ in F1 làm tròn một chữ số), không đọc `_private/`.

## 1. Số liệu luyện tập

| Lô | F1 lỗi luật | F1 lỗi gán nhãn (cross_check_review) | F1 tổng | Hàng đợi review | QC v1 |
|---|---|---|---|---|---|
| r2611 (seed nhóm) | ≈ 1,0 | ≈ 0,9 | ≈ 1,0 | 9 ảnh (6 confirmed / 3 rejected) | 15/250 = 6,0% → HOLD |
| r101 | ≈ 1,0 | ≈ 0,9 | ≈ 1,0 | 8 ảnh (5 / 3) | 19/250 = 7,6% → HOLD |
| r202 | ≈ 1,0 | ≈ 0,9 | ≈ 1,0 | 11 ảnh (8 / 3) | 21/250 = 8,4% → HOLD |
| clean (`--no-faults`, 50 ảnh calib) | 0 lỗi luật báo ra | 0 ứng viên | | 0 | |

Cả ba seed đều qua `check_handover.py` 17/17 và được nộp trong `submission/r2611`, `submission/r101`, `submission/r202`.

**Thử trước đề ẩn.** Đề ẩn đổi tên ảnh, ghi lại file và có thể đổi mức lỗi, nên nhóm tự tạo lô kiểu đó bằng `inject_release.py --opaque` (o301, mức mặc định) và `--opaque --profile` với mức khó hơn mặc định (h302, h303: box lệch chỉ 6–15% thay vì 12–30%, 100% đổi sang lớp dễ nhầm, vật nhỏ tới 400 pixel, nhiều lỗi gán nhãn hơn). Validator giữ F1 lỗi luật ≈ 1,0 trên cả ba lô. Lô h302 review đủ 15 ảnh trong khoảng 15 phút: F1 lỗi gán nhãn ≈ 0,9, F1 tổng ≈ 1,0.

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
- **Nguồn thông tin từ ticket và changelog:**
  - Trong `incoming/ticket.md`, team AI phản ánh model train trên lô này hay bỏ sót đối tượng lớp `cup` bị che khuất hoặc nằm ở mép ảnh, và nêu rõ hai cảnh đã kiểm tra tay là `scene_115` và `scene_704`.
  - Trong `guideline/changelog.md`, phiên bản mới **v1.3** quy định: lớp `cup` dù bị che trên 50% hoặc cắt ở mép ảnh **vẫn phải gán box** (trong khi bản cũ **v1.2** cho phép bỏ qua).
- **Tiêu chí lọc tầng A (`tier_a`), tầng B (`tier_b`) và danh sách cần thông báo (`notify`):**
  - Điều kiện chung của ảnh bị ảnh hưởng: ảnh thuộc **job** được gán theo guideline cũ (**v1.2**, tức các job `J01`, `J02`, `J03` trong `jobs.csv`) **và** tệp nhãn detection (`labels/<image>.txt`) có ít nhất một box thuộc lớp bị đổi quy tắc (`cup`, `class_id = 41`).
  - **`tier_a` (4 ảnh: `000000002157`, `000000002431`, `000000002592`, `000000002685`):** các ảnh thỏa điều kiện chung nằm trong hai cảnh mà team AI đã điểm danh trực tiếp trong ticket (`scene_115`, `scene_704`). Đây là nhóm ảnh xác nhận trực tiếp phản ánh của team AI để ưu tiên gán/kiểm lại ngay.
  - **`tier_b` (3 ảnh: `000000003661`, `000000003845`, `000000003934`):** các ảnh khác trong toàn bộ lô cũng thỏa điều kiện chung (thuộc job theo guideline cũ v1.2 và có box detection lớp `cup`) nhưng nằm ở các cảnh còn lại chưa được team AI báo. Đây là nhóm ảnh mở rộng cần chủ động rà soát để không bỏ sót lỗi cùng nguyên nhân hệ thống.
  - **`notify` (`["A01", "Q03"]`):** tập hợp mã người gán (`annotator`) và người kiểm (`reviewer`) của đúng các job thực sự chứa ảnh thuộc `tier_a` và `tier_b` (không báo tràn lan cho nhân sự của các job v1.2 không có lớp `cup`).
- **Vì sao phải lấy phiên bản guideline theo `job` (`jobs.csv`) chứ không lấy theo từng ảnh (`metadata.json`)?**
  - Phiên bản guideline được ban hành và áp dụng ở cấp độ **đợt giao việc (job)** khi bắt đầu gán nhãn.
  - Trường `guideline_version` ghi ở từng ảnh trong `metadata.json` là dữ liệu metadata của từng ảnh và **chính nó có thể bị ghi sai** (lỗi luật `guideline_mismatch`, ví dụ ảnh `000000015597` trong lô `r2611`). Nếu lọc theo `metadata.json` của ảnh thì sẽ bỏ sót ảnh thuộc job cũ nhưng bị ghi nhầm thành `v1.3`, hoặc báo thừa ảnh thuộc job mới (`v1.3`) nhưng bị ghi nhầm thành `v1.2`.
  - Nhóm tự động hóa bước này bằng script `tools/trace_query.py` (đọc trực tiếp `changelog.md`, `ticket.md`, `jobs.csv`, `metadata.json`, `classes.txt` và `labels/`).

## 6. Bug hoặc điểm chưa rõ trong lab

- Windows: `scripts/run_lab.py` gọi script con không kèm `-X utf8`, in tiếng Việt ra console cp1252 nên lỗi `UnicodeEncodeError` và để lại `runs/r<seed>` dở dang. Cách tránh: đặt `$env:PYTHONUTF8=1` trước khi chạy, xoá thư mục dở rồi chạy lại.
- Lệch tự nhiên của COCO trong pool luyện tập lặp lại ở mọi seed (3 ca lệch box/segment và 5 ca nhãn kép), nên nhóm dùng việc "lặp lại ở seed khác" làm một bằng chứng phụ khi ghi `rejected`.
- Phiên bản Python đổi byte của mask (Quốc Anh phát hiện): Python 3.15 nén PNG bằng zlib-ng nên `mask_sha256`, manifest và `release_id` của lô tạo lại khác với lô của nhóm (tạo bằng Python 3.11/3.12). Khi tạo lại lô để kiểm (`run_lab.py`, `export_submission.py --import`) nên dùng Python 3.11 hoặc 3.12, ví dụ `py -3.12`.
