# Công cụ của nhóm (ngoài validator)

Chạy từ thư mục gốc repo. Windows: chạy `$env:PYTHONUTF8=1` một lần trong cửa sổ PowerShell trước.
Dùng Python 3.11 hoặc 3.12 (`py -3.12`): Python 3.15 nén mask PNG khác byte nên `release_id` của lô tạo lại không khớp với lô của nhóm.

| Công cụ | Việc | Thư viện |
|---|---|---|
| `validator/validate.py` | lỗi luật (`--out`) + ứng viên đối chiếu (`--candidates`) | chuẩn |
| `tools/view_candidates.py` | vẽ box + viền segment cho từng ứng viên (xuất ảnh PNG 2 khung bằng `--out` hoặc mở web review nhóm bằng `--share`) | Pillow / chuẩn |
| `tools/build_handover.py` | dựng lô v2 từ `errors.json` (không sửa `delivery/`) | chuẩn (+ Pillow để mở kiểm ảnh wrong_hash) |
| `tools/trace_query.py` | `trace.json` từ ticket + changelog + jobs.csv | chuẩn |
| `tools/sheet_snapshot.py` | chụp Google Sheet của nhóm vào `docs/team_sheet/` (mỗi tab một CSV) | openpyxl |

## Seed luyện tập (ví dụ 2611)

```powershell
$env:PYTHONUTF8=1
py validator/validate.py runs/r2611/delivery --out runs/r2611/rules.json --candidates runs/r2611/candidates.json
# Cách 1: Xuất ảnh PNG 2 khung (toàn cảnh + crop phóng to) vào thư mục review_img
py tools/view_candidates.py runs/r2611/delivery runs/r2611/candidates.json --out runs/r2611/review_img
# Cách 2: Mở giao diện web chia sẻ qua LAN/Wi-Fi để cả nhóm cùng xem và lưu trực tiếp review_log.csv
py -X utf8 tools/view_candidates.py runs/r2611/delivery --candidates runs/r2611/candidates.json --share
# Sau khi có runs/r2611/review_log.csv (image,type,verdict,note):
py scripts/merge_review.py --rules runs/r2611/rules.json --review runs/r2611/review_log.csv --out runs/r2611/errors.json
py scripts/score_findings.py --run runs/r2611
py scripts/lineage.py record --event decision --release-id <release_id v1> --decision HOLD
py tools/build_handover.py --run runs/r2611
py scripts/pack_release.py runs/r2611/handover/<release_id v1>_v2
py scripts/lineage.py record --event release --release-id <release_id v1>_v2 --parent <release_id v1>
py tools/trace_query.py runs/r2611/delivery --out runs/r2611/trace.json
py scripts/check_handover.py --run runs/r2611
```

## Đề ẩn (40 phút) & Cách chia hàng đợi cho 6 thành viên

```powershell
$env:PYTHONUTF8=1
py validator/validate.py delivery --out submission/de_an/rules.json --candidates submission/de_an/candidates.json
# Xuất ảnh PNG 2 khung để xem nhanh hoặc mở web server chia sẻ cho cả nhóm:
py tools/view_candidates.py delivery submission/de_an/candidates.json --out de_an_review
py -X utf8 tools/view_candidates.py delivery --candidates submission/de_an/candidates.json --share
# Song song: chạy truy vết tự động cho đề ẩn
py tools/trace_query.py delivery --out submission/de_an/trace.json
# Sau khi cả nhóm chốt xong submission/de_an/review_log.csv:
py scripts/merge_review.py --rules submission/de_an/rules.json --review submission/de_an/review_log.csv --out submission/de_an/errors.json
```

### Quy tắc chia hàng đợi đề ẩn (6 người)
- Ngay khi có `submission/de_an/candidates.json` (gồm $N$ ứng viên, đánh số từ `1` đến `N` theo thứ tự trong file / trên giao diện web hoặc trong tab **Review ảnh**):
  1. `hdung25`: mục `1 .. ceil(N/6)`
  2. `hieuwewe123`: đoạn kế tiếp
  3. `ldmanh610`: đoạn kế tiếp
  4. `manhtotbung`: đoạn kế tiếp
  5. `QuocAnh-bit`: đoạn kế tiếp
  6. `MTrang0702`: đoạn cuối
- Khi xem ảnh: ca "lệch lớp" thì ảnh cho biết bên nào sai (detection sai → `class_swap`, panoptic sai → `category_swap`); segment chứa thêm một vật ở xa trong box cùng lớp khác → `instance_merge`; box hụt một phần vật → `bbox_drift`; vật rõ ràng không có box → `missing_box`. Lệch do che khuất, crowd hoặc COCO gán hai nhãn cho một vật → `rejected` kèm lý do (mọi ghi chú `note` phải ≥ 20 ký tự, mô tả cụ thể nhìn thấy gì trong ảnh).
