# Công cụ của nhóm (ngoài validator)

Chạy từ thư mục gốc repo. Windows: chạy `$env:PYTHONUTF8=1` một lần trong cửa sổ PowerShell trước.

| Công cụ | Việc | Thư viện |
|---|---|---|
| `validator/validate.py` | lỗi luật (`--out`) + ứng viên đối chiếu (`--candidates`) | chuẩn |
| `tools/view_candidates.py` | vẽ box + viền segment cho từng ứng viên để xem ảnh | Pillow |
| `tools/build_handover.py` | dựng lô v2 từ `errors.json` (không sửa `delivery/`) | chuẩn (+ Pillow để mở kiểm ảnh wrong_hash) |
| `tools/trace_query.py` | `trace.json` từ ticket + changelog + jobs.csv | chuẩn |

## Seed luyện tập (ví dụ 2611)

```powershell
py validator/validate.py runs/r2611/delivery --out runs/r2611/rules.json --candidates runs/r2611/candidates.json
py tools/view_candidates.py runs/r2611/delivery runs/r2611/candidates.json --out runs/r2611/review_img
# mở từng ảnh trong review_img, ghi runs/r2611/review_log.csv (image,type,verdict,note)
py scripts/merge_review.py --rules runs/r2611/rules.json --review runs/r2611/review_log.csv --out runs/r2611/errors.json
py scripts/score_findings.py --run runs/r2611
py scripts/lineage.py record --event decision --release-id <release_id v1> --decision HOLD
py tools/build_handover.py --run runs/r2611
py scripts/pack_release.py runs/r2611/handover/<release_id v1>_v2
py scripts/lineage.py record --event release --release-id <release_id v1>_v2 --parent <release_id v1>
py tools/trace_query.py runs/r2611/delivery --out runs/r2611/trace.json
py scripts/check_handover.py --run runs/r2611
```

## Đề ẩn (40 phút)

```powershell
py validator/validate.py delivery --out submission/de_an/rules.json --candidates submission/de_an/candidates.json
py tools/view_candidates.py delivery submission/de_an/candidates.json --out de_an_review
# chia ảnh trong de_an_review cho cả nhóm, ghi submission/de_an/review_log.csv
py scripts/merge_review.py --rules submission/de_an/rules.json --review submission/de_an/review_log.csv --out submission/de_an/errors.json
py tools/trace_query.py delivery --out submission/de_an/trace.json
```

Khi xem ảnh: ca "lệch lớp" thì ảnh cho biết bên nào sai (detection sai → `class_swap`, panoptic sai → `category_swap`); segment chứa thêm một vật ở xa trong box cùng lớp khác → `instance_merge`; box hụt một phần vật → `bbox_drift`; vật rõ ràng không có box → `missing_box`. Lệch do che khuất, crowd hoặc COCO gán hai nhãn cho một vật → `rejected` kèm lý do.
