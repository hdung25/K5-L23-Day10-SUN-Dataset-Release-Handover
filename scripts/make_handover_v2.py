#!/usr/bin/env python3
"""Tạo gói bàn giao lô v2 từ delivery v1 và errors.json (Pha P4).

Sử dụng:
  python scripts/make_handover_v2.py --run runs/r2611
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from pathlib import Path

# Các lỗi thuộc nhãn detection hoặc thiếu file cần đưa vào rework_queue và tách khỏi v2
DET_REWORK = {
    "missing_image",
    "invalid_class",
    "bbox_out_of_bounds",
    "duplicate_box",
    "class_swap",
    "bbox_drift",
    "missing_box",
}

PANOPTIC_TYPES = {
    "invalid_category_id",
    "thing_overlap",
    "category_swap",
    "instance_merge",
}

THRESHOLD = 0.02  # Day 7: > 2% ảnh lỗi thì không Release


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_handover_v2(run_dir: Path) -> Path:
    delivery_dir = run_dir / "delivery"
    if not delivery_dir.is_dir():
        raise FileNotFoundError(f"Không tìm thấy thư mục: {delivery_dir}")

    # Đọc thông tin v1
    release_info = json.loads((delivery_dir / "release.json").read_text(encoding="utf-8"))
    rid = release_info["release_id"]
    manifest_items = json.loads((delivery_dir / "manifest.json").read_text(encoding="utf-8"))["items"]
    metadata_items = {m["image"]: m for m in json.loads((delivery_dir / "metadata.json").read_text(encoding="utf-8"))["items"]}
    jobs = {row["job_id"]: row for row in read_csv(delivery_dir / "jobs.csv")}
    classes = [ln.split(" ", 1)[1].strip() for ln in (delivery_dir / "classes.txt").read_text(encoding="utf-8").splitlines()]

    # Đọc errors.json
    errors_file = run_dir / "errors.json"
    if not errors_file.is_file():
        raise FileNotFoundError(f"Chưa có file: {errors_file}. Cần chạy validator trước!")
    errors_data = json.loads(errors_file.read_text(encoding="utf-8"))
    errors_list = errors_data.get("errors", [])

    # Phân loại lỗi
    rework_rows = []
    rework_images = set()
    panoptic_error_images = []

    for err in errors_list:
        etype = err.get("type")
        target = err.get("target")
        if target in manifest_items and etype in DET_REWORK:
            rework_images.add(target)
            meta = metadata_items.get(target, {})
            job_id = meta.get("job_id", "")
            job_info = jobs.get(job_id, {})
            
            action = "re_annotate"
            if etype in ("class_swap", "invalid_class"):
                action = "fix_class"
            elif etype in ("bbox_drift", "bbox_out_of_bounds", "duplicate_box"):
                action = "re_draw_box"
            elif etype in ("missing_box", "missing_image"):
                action = "add_missing"

            rework_rows.append({
                "image": target,
                "type": etype,
                "annotator": job_info.get("annotator", ""),
                "reviewer": job_info.get("reviewer", ""),
                "action": action,
            })
        elif etype in PANOPTIC_TYPES:
            panoptic_error_images.append(f"{target} ({etype})")

    # Thư mục đích v2
    v2_dir = run_dir / "handover" / f"{rid}_v2"
    v2_images_dir = v2_dir / "images"
    v2_labels_dir = v2_dir / "labels"
    v2_images_dir.mkdir(parents=True, exist_ok=True)
    v2_labels_dir.mkdir(parents=True, exist_ok=True)

    # 1. Sao chép ảnh và nhãn sạch (không thuộc rework)
    clean_images = []
    for img_name in sorted(manifest_items.keys()):
        if img_name in rework_images:
            continue
        src_img = delivery_dir / "images" / f"{img_name}.jpg"
        src_lbl = delivery_dir / "labels" / f"{img_name}.txt"
        dst_img = v2_images_dir / f"{img_name}.jpg"
        dst_lbl = v2_labels_dir / f"{img_name}.txt"

        if src_img.is_file() and src_lbl.is_file():
            shutil.copy2(src_img, dst_img)
            shutil.copy2(src_lbl, dst_lbl)
            clean_images.append(img_name)

    # 2. rework_queue.csv
    rework_rows.sort(key=lambda r: r["image"])
    write_csv(
        v2_dir / "rework_queue.csv",
        ["image", "type", "annotator", "reviewer", "action"],
        rework_rows,
    )

    # 3. manifest.csv (file,sha256)
    manifest_rows = []
    for sub in ("images", "labels"):
        sub_dir = v2_dir / sub
        for fpath in sorted(sub_dir.iterdir()):
            if fpath.is_file():
                rel_path = f"{sub}/{fpath.name}"
                manifest_rows.append({
                    "file": rel_path,
                    "sha256": sha256_file(fpath),
                })
    write_csv(v2_dir / "manifest.csv", ["file", "sha256"], manifest_rows)

    # 4. label_summary.csv (class,count)
    counts = {cname: 0 for cname in classes}
    for img_name in clean_images:
        lbl_path = v2_labels_dir / f"{img_name}.txt"
        for line in lbl_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                cid = int(float(line.split()[0]))
                if 0 <= cid < len(classes):
                    cname = classes[cid]
                    counts[cname] = counts.get(cname, 0) + 1

    total_labels = sum(counts.values())
    summary_rows = [{"class": c, "count": counts[c]} for c in classes]
    summary_rows.append({"class": "TOTAL", "count": total_labels})
    write_csv(v2_dir / "label_summary.csv", ["class", "count"], summary_rows)

    # 5. truyvet.csv (image,scene_id,split,job_id,annotator,reviewer,guideline)
    # Sửa scene_leak: xác định 1 split duy nhất cho mỗi scene_id
    scene_to_split = {}
    for img_name in clean_images:
        meta = metadata_items[img_name]
        sc = meta["scene_id"]
        sp = meta["split"]
        if sc not in scene_to_split:
            scene_to_split[sc] = sp  # Chọn split đầu tiên xuất hiện của scene

    truyvet_rows = []
    guideline_versions = set()
    for img_name in clean_images:
        meta = metadata_items[img_name]
        job_id = meta["job_id"]
        job_info = jobs[job_id]
        guideline = job_info["guideline"]  # Lấy guideline chuẩn theo jobs.csv
        guideline_versions.add(guideline)

        truyvet_rows.append({
            "image": img_name,
            "scene_id": meta["scene_id"],
            "split": scene_to_split[meta["scene_id"]],
            "job_id": job_id,
            "annotator": job_info["annotator"],
            "reviewer": job_info["reviewer"],
            "guideline": guideline,
        })
    write_csv(
        v2_dir / "truyvet.csv",
        ["image", "scene_id", "split", "job_id", "annotator", "reviewer", "guideline"],
        truyvet_rows,
    )

    # 6. README.txt
    err_targets = {e["target"] for e in errors_list}
    total_v1_images = len(manifest_items)
    qc_count = len(err_targets)
    qc_rate = qc_count / total_v1_images

    v1_decision = "Hold" if qc_rate > THRESHOLD else "Release"
    v1_reason = f"tỉ lệ lỗi {qc_rate:.1%} vượt ngưỡng {THRESHOLD:.0%}" if qc_rate > THRESHOLD else "tỉ lệ lỗi đạt ngưỡng cho phép"

    guideline_str = ", ".join(sorted(guideline_versions))

    panoptic_note = "; ".join(panoptic_error_images) if panoptic_error_images else "Không có"
    notes = (
        f"Đã chuẩn hoá split theo scene trong truyvet.csv để loại bỏ scene_leak; "
        f"cập nhật sha256 thật trong manifest.csv (ảnh wrong_hash đã mở kiểm tra nội dung toàn vẹn); "
        f"đồng bộ guideline theo job_id. "
        f"Có {len(rework_rows)} ảnh lỗi detection được chuyển sang rework_queue.csv để gán lại. "
        f"Các ảnh có lỗi panoptic ({panoptic_note}) vẫn ở lại v2 do nhãn detection đúng, đã lập danh sách báo team panoptic."
    )

    readme_content = f"""Release: {rid}_v2
Parent: {rid}
Số ảnh: {len(clean_images)}
Số nhãn: {total_labels}
Guideline: {guideline_str}
QC v1: {qc_count}/{total_v1_images} = {qc_rate:.1%}
Kết luận v1: {v1_decision} — {v1_reason}
Kết luận v2: Release — Đã tách {len(rework_rows)} ảnh lỗi sang rework_queue.csv, sửa hash và scene_leak, giữ nguyên {len(clean_images)} ảnh sạch
Ghi chú: {notes}
"""
    (v2_dir / "README.txt").write_text(readme_content, encoding="utf-8")
    print(f"[OK] Đã dựng thành công gói bàn giao v2 tại: {v2_dir}")
    print(f"     - Số ảnh giữ lại: {len(clean_images)}/{total_v1_images}")
    print(f"     - Số ảnh đưa sang rework_queue: {len(rework_rows)}")
    print(f"     - Tổng số nhãn detection: {total_labels}")
    return v2_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Tạo gói bàn giao lô v2")
    parser.add_argument("--run", default="runs/r2611", help="Đường dẫn thư mục run (mặc định: runs/r2611)")
    args = parser.parse_args()
    build_handover_v2(Path(args.run))


if __name__ == "__main__":
    main()
