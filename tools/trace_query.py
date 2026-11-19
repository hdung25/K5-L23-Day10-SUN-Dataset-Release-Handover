"""Truy vết ticket của team AI về danh sách ảnh (tier_a, tier_b) và nhân sự liên quan (notify).

Cách chạy:
    py -X utf8 tools/trace_query.py <thư_mục_delivery> --out <đường_dẫn_trace.json>

Nguyên tắc hoạt động:
1. Đọc guideline/changelog.md để tìm phiên bản guideline mới nhất (ví dụ v1.3) và tên lớp đối tượng bị đổi quy tắc (ví dụ `cup`).
2. Đọc incoming/ticket.md để trích xuất các mã cảnh (scene_XXX) mà team AI đã phát hiện bằng tay.
3. Đọc jobs.csv để tra phiên bản guideline gốc theo từng job_id (KHÔNG lấy guideline_version trong metadata.json của từng ảnh vì trường đó có thể bị lỗi guideline_mismatch).
4. Lọc các ảnh thuộc job dùng guideline cũ (< newest) và trong tệp nhãn YOLO (labels/*.txt) có ít nhất một box detection thuộc lớp bị đổi quy tắc:
   - tier_a: các ảnh thỏa điều kiện nằm trong những cảnh mà ticket.md đã nêu.
   - tier_b: các ảnh thỏa điều kiện nằm ở các cảnh còn lại trong lô mà chưa ai báo.
   - notify: danh sách mã người gán (annotator) và người kiểm (reviewer) của các job chứa ảnh thuộc tier_a và tier_b.
"""

from __future__ import annotations  # Hỗ trợ cú pháp chú thích kiểu dữ liệu hiện đại.

import argparse  # Phân tích tham số dòng lệnh (thư mục delivery và đường dẫn --out).
import csv  # Đọc bảng phân công công việc jobs.csv.
import json  # Đọc metadata.json, manifest.json và xuất kết quả trace.json.
import re  # Dùng biểu thức chính quy để tách phiên bản, tên lớp từ changelog.md và mã cảnh từ ticket.md.
from pathlib import Path  # Xử lý đường dẫn tệp đa nền tảng.


def parse_changelog(text: str) -> tuple[str, list[str]]:  # Tách phiên bản mới nhất và các lớp đổi quy tắc từ changelog.md.
    versions = re.findall(r"^##\s*(v[\d.]+)", text, flags=re.M)  # Tìm tất cả tiêu đề cấp 2 có dạng "## v1.3", "## v1.2".
    newest = versions[0]  # Phiên bản đứng đầu tệp changelog là phiên bản mới nhất vừa ban hành.
    section = text.split(f"## {newest}", 1)[1].split("\n## ", 1)[0]  # Cắt riêng phần nội dung của phiên bản mới nhất.
    changed = re.findall(r"[Ll]ớp\s+`([^`]+)`", section)  # Tìm tên lớp nằm trong cặp dấu backtick sau chữ "Lớp".
    return newest, changed  # Trả về mã phiên bản mới nhất và danh sách tên lớp bị đổi quy tắc.


def main() -> int:  # Hàm chính thực hiện truy vết và ghi tệp trace.json.
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)  # Khởi tạo bộ đọc CLI.
    ap.add_argument("delivery", type=Path, help="Đường dẫn thư mục delivery của lô cần truy vết.")  # Đối số vị trí: thư mục delivery.
    ap.add_argument("--out", type=Path, required=True, help="Đường dẫn tệp trace.json đầu ra.")  # Cờ bắt buộc: đường dẫn trace.json.
    args = ap.parse_args()  # Đọc các tham số người dùng truyền vào.
    d = args.delivery  # Gán biến ngắn đại diện cho thư mục delivery.

    # Bước 1: Đọc changelog.md để lấy phiên bản mới nhất (v1.3) và lớp đổi quy tắc.
    newest, changed = parse_changelog((d / "guideline" / "changelog.md").read_text(encoding="utf-8"))
    # Bước 2: Đọc ticket.md và trích xuất tập hợp các mã cảnh dạng scene_XXX mà team AI đã nêu.
    scenes = set(re.findall(r"scene_\d+", (d / "incoming" / "ticket.md").read_text(encoding="utf-8")))
    # Bước 3: Đọc jobs.csv để lập bảng tra thông tin job (annotator, reviewer, guideline) theo job_id.
    with (d / "jobs.csv").open(encoding="utf-8", newline="") as f:
        jobs = {row["job_id"]: row for row in csv.DictReader(f)}  # Ánh xạ mỗi job_id sang dòng dữ liệu của job đó.
    # Bước 4: Đọc metadata.json và manifest.json để lấy danh sách ảnh, cảnh, job_id và đường dẫn tệp nhãn.
    meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))["items"]
    manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["items"]

    # Bước 5: Đổi tên lớp bị đổi quy tắc sang mã số class_id (0..79) dựa vào classes.txt.
    class_ids: set[int] = set()  # Tập hợp mã số lớp YOLO tương ứng với lớp bị đổi quy tắc.
    for line in (d / "classes.txt").read_text(encoding="utf-8").splitlines():  # Duyệt từng dòng trong classes.txt.
        if line.strip():  # Bỏ qua dòng trống.
            k, v = line.split(maxsplit=1)  # Tách mã số lớp (k) và tên lớp (v).
            if v.strip() in changed:  # Nếu tên lớp nằm trong danh sách lớp bị đổi quy tắc ở changelog.
                class_ids.add(int(k))  # Lưu mã số nguyên của lớp đó để đối chiếu với tệp nhãn YOLO.

    def has_class(image: str) -> bool:  # Kiểm tra ảnh có chứa ít nhất một box detection thuộc lớp bị đổi quy tắc hay không.
        path = d / manifest[image]["label"]  # Lấy đường dẫn tệp nhãn YOLO (labels/<image>.txt) từ manifest.
        if not path.is_file():  # Nếu tệp nhãn không tồn tại thì trả về False.
            return False
        for line in path.read_text(encoding="utf-8").splitlines():  # Duyệt từng box trong tệp nhãn YOLO.
            parts = line.split()  # Tách các cột: class_id x_center y_center width height.
            if parts and int(float(parts[0])) in class_ids:  # Nếu cột đầu tiên trùng với class_id của lớp đổi quy tắc.
                return True  # Ảnh có chứa đối tượng thuộc lớp bị đổi quy tắc.
        return False  # Duyệt hết tệp mà không có box nào thuộc lớp đó.

    # Bước 6: Phân loại ảnh vào tier_a, tier_b và thu thập các job liên quan để tìm người cần thông báo (notify).
    tier_a: list[str] = []  # Danh sách ảnh trong cảnh được ticket báo, thuộc job guideline cũ, có lớp đổi quy tắc.
    tier_b: list[str] = []  # Danh sách ảnh ở các cảnh còn lại nhưng cùng điều kiện (job guideline cũ, có lớp đổi quy tắc).
    jobs_hit: set[str] = set()  # Tập hợp các job_id có ảnh rơi vào tier_a hoặc tier_b.
    for m in meta:  # Duyệt từng bản ghi ảnh trong metadata.json.
        job = jobs.get(m["job_id"])  # Tra thông tin job của ảnh từ bảng jobs.csv.
        # Bỏ qua nếu không tìm thấy job, hoặc job đã dùng guideline mới nhất, hoặc ảnh không có box của lớp đổi quy tắc.
        if job is None or job["guideline"] == newest or not has_class(m["image"]):
            continue
        # Nếu ảnh thuộc cảnh mà team AI đã nêu trong ticket thì đưa vào tier_a, ngược lại đưa vào tier_b.
        (tier_a if m["scene_id"] in scenes else tier_b).append(m["image"])
        jobs_hit.add(m["job_id"])  # Ghi nhận job_id này có ảnh bị ảnh hưởng để trích xuất người gán và người kiểm.

    # Bước 7: Tập hợp mã annotator và reviewer của các job bị ảnh hưởng, sắp xếp tăng dần và loại bỏ trùng lặp.
    notify = sorted({jobs[j]["annotator"] for j in jobs_hit} | {jobs[j]["reviewer"] for j in jobs_hit})
    result = {"tier_a": sorted(tier_a), "tier_b": sorted(tier_b), "notify": notify}  # Đóng gói đúng 3 khóa theo mẫu trace.json.
    args.out.parent.mkdir(parents=True, exist_ok=True)  # Tạo thư mục chứa tệp đầu ra nếu chưa có.
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")  # Ghi tệp JSON chuẩn UTF-8.
    print(f"changed class {changed} (rule from {newest}), scenes {sorted(scenes)}: "
          f"tier_a {len(tier_a)}, tier_b {len(tier_b)}, notify {notify}")  # In tóm tắt kết quả truy vết ra màn hình.
    return 0  # Kết thúc chương trình thành công.


if __name__ == "__main__":  # Chạy hàm main khi gọi trực tiếp tệp từ dòng lệnh.
    raise SystemExit(main())
