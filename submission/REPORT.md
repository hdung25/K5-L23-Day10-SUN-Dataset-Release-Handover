# Báo cáo nhóm SUN

## 1. Số liệu luyện tập
- F1 theo seed (rule / cross_check / overall): <<seed: ... / ... / ...>>
- Số ứng viên trên lô sạch (`--no-faults`): <<...>>; hàng đợi trên seed luyện tập: <<... ảnh>>
- Ngưỡng đã chọn và cách chọn (không dùng `_private`): <<...>>

## 2. Vì sao báo hết ứng viên làm F1 giảm?
<<Trả lời bằng số của nhóm.>>

## 3. Quyết định và lineage
<<QC v1 a/b, kết luận, vì sao R-021 phải xem lại hoặc train lại.>>

## 4. Hash chứng minh gì, không chứng minh gì?
<<>>

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

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
<<>>
