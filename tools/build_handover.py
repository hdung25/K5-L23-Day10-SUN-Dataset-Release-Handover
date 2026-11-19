"""Build the v2 handover folder from a v1 delivery and the team's errors.json.

    python tools/build_handover.py --run runs/r2611

Never touches delivery/ (v1 stays as delivered). Writes runs/<run>/handover/<release_id>_v2/:
images/, labels/ (unchanged v1 files, minus images sent to rework), rework_queue.csv,
manifest.csv, label_summary.csv, truyvet.csv, README.txt.

Rules (GUIDE pha 4):
- detection-label errors and missing files -> rework_queue.csv, image leaves v2;
- wrong_hash: if only the image hash is wrong and the image opens fine, keep it and write the
  real hash; if the label or mask file changed, or the image is broken -> rework;
- guideline_mismatch -> truyvet.csv takes the guideline of the job;
- scene_leak -> the whole scene goes to the split most of its images use;
- panoptic-only errors -> image stays in v2, listed in README for the panoptic team.
"""

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path

DET_REWORK = {"missing_image", "invalid_class", "bbox_out_of_bounds", "duplicate_box",
              "class_swap", "bbox_drift", "missing_box"}
PANOPTIC_ONLY = {"invalid_category_id", "thing_overlap", "category_swap", "instance_merge"}
ACTION = {
    "missing_image": "giao lại file ảnh rồi kiểm lại nhãn",
    "wrong_hash": "file đã đổi sau khi gán: kiểm và gán lại",
    "invalid_class": "sửa class_id ngoài 0-79",
    "bbox_out_of_bounds": "kéo box về trong ảnh",
    "duplicate_box": "xoá box bị lặp",
    "class_swap": "sửa lớp của box theo ảnh",
    "bbox_drift": "chỉnh box ôm sát vật",
    "missing_box": "thêm box cho vật bị thiếu",
}
THRESHOLD = 0.02


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image_opens(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            im.load()
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, type=Path)
    args = ap.parse_args()
    run = args.run
    d = run / "delivery"
    rid = json.loads((d / "release.json").read_text(encoding="utf-8"))["release_id"]
    man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["items"]
    meta = {m["image"]: m for m in json.loads((d / "metadata.json").read_text(encoding="utf-8"))["items"]}
    with (d / "jobs.csv").open(encoding="utf-8", newline="") as f:
        jobs = {row["job_id"]: row for row in csv.DictReader(f)}
    names = {}
    for line in (d / "classes.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            k, v = line.split(maxsplit=1)
            names[int(k)] = v
    errors = json.loads((run / "errors.json").read_text(encoding="utf-8"))["errors"]

    per_image = {e["target"]: e["type"] for e in errors if e["target"] in man}
    leaked = sorted(e["target"] for e in errors if e["type"] == "scene_leak")

    rework, kept_hash_fix, broken_hash = [], [], []
    for image, kind in sorted(per_image.items()):
        if kind == "wrong_hash":
            item = man[image]
            label_ok = sha(d / item["label"]) == item["label_sha256"]
            mask_ok = sha(d / item["mask"]) == item["mask_sha256"]
            if label_ok and mask_ok and image_opens(d / item["image"]):
                kept_hash_fix.append(image)
                continue
            broken_hash.append(image)
        elif kind not in DET_REWORK:
            continue
        job = jobs[meta[image]["job_id"]]
        rework.append({"image": image, "type": kind, "annotator": job["annotator"],
                       "reviewer": job["reviewer"], "action": ACTION.get(kind, "kiểm lại")})
    out_images = {r["image"] for r in rework}

    # split per scene: majority vote for leaked scenes, as delivered otherwise
    by_scene = defaultdict(list)
    for m in meta.values():
        by_scene[m["scene_id"]].append(m["split"])
    scene_split = {}
    for scene, splits in by_scene.items():
        top = Counter(splits).most_common()
        scene_split[scene] = top[0][0] if scene in leaked else splits[0]
        if scene in leaked and len(top) > 1 and top[0][1] == top[1][1]:
            scene_split[scene] = "train"  # tie: keep the scene out of val

    v2 = run / "handover" / f"{rid}_v2"
    if v2.exists():
        shutil.rmtree(v2)
    (v2 / "images").mkdir(parents=True)
    (v2 / "labels").mkdir()
    kept = [s for s in sorted(man) if s not in out_images]
    for s in kept:
        shutil.copy2(d / man[s]["image"], v2 / "images" / f"{s}.jpg")
        shutil.copy2(d / man[s]["label"], v2 / "labels" / f"{s}.txt")

    with (v2 / "rework_queue.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["image", "type", "annotator", "reviewer", "action"])
        w.writeheader()
        w.writerows(rework)

    with (v2 / "manifest.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "sha256"])
        for sub in ("images", "labels"):
            for p in sorted((v2 / sub).iterdir()):
                w.writerow([f"{sub}/{p.name}", sha(p)])

    counts = Counter()
    for s in kept:
        for line in (v2 / "labels" / f"{s}.txt").read_text(encoding="utf-8").splitlines():
            if line.strip():
                counts[int(line.split()[0])] += 1
    with (v2 / "label_summary.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["class", "count"])
        for c in sorted(counts):
            w.writerow([names[c], counts[c]])
        w.writerow(["TOTAL", sum(counts.values())])

    with (v2 / "truyvet.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["image", "scene_id", "split", "job_id", "annotator", "reviewer", "guideline"])
        for s in kept:
            m = meta[s]
            job = jobs[m["job_id"]]
            w.writerow([s, m["scene_id"], scene_split[m["scene_id"]], m["job_id"],
                        job["annotator"], job["reviewer"], job["guideline"]])

    err_targets = {e["target"] for e in errors}
    rate = len(err_targets) / len(man)
    by_version = defaultdict(list)
    for job_id, job in sorted(jobs.items()):
        by_version[job["guideline"]].append(job_id)
    guideline = ", ".join(f"{v} ({ids[0]}-{ids[-1]})" for v, ids in sorted(by_version.items()))
    gm = sorted(i for i, k in per_image.items() if k == "guideline_mismatch")
    pan = sorted(f"{i} ({k})" for i, k in per_image.items() if k in PANOPTIC_ONLY)
    owners = Counter(f"{r['annotator']}/{r['reviewer']}" for r in rework)
    v1_word = "Hold" if rate > THRESHOLD else "Release"
    notes = [
        f"không ghi đè v1: delivery/ giữ nguyên, v2 là bản mới có lô cha {rid}",
        f"{len(rework)} ảnh lỗi nhãn detection hoặc thiếu file tách sang rework_queue.csv, giao lại đúng người gán/người kiểm của job ("
        + ", ".join(f"{k}: {v} ảnh" for k, v in sorted(owners.items())) + ")",
        "hash: " + (f"{len(kept_hash_fix)} ảnh wrong_hash đã mở kiểm, ảnh còn nguyên nên giữ lại và ghi sha256 thật trong manifest.csv ({', '.join(kept_hash_fix)})" if kept_hash_fix else "không có ảnh wrong_hash giữ lại")
        + (f"; {len(broken_hash)} ảnh có file đổi hoặc hỏng đưa vào rework ({', '.join(broken_hash)})" if broken_hash else ""),
        "guideline: truyvet.csv lấy phiên bản theo job trong jobs.csv, không theo metadata ảnh" + (f" (sửa {len(gm)} ảnh: {', '.join(gm)})" if gm else ""),
        "split: " + (f"{len(leaked)} cảnh rò train/val ({', '.join(leaked)}) đưa cả cảnh về split mà đa số ảnh của cảnh đang dùng" if leaked else "không có cảnh rò"),
        "lỗi chỉ ở panoptic, nhãn detection vẫn đúng nên ảnh ở lại v2, báo team panoptic: " + (", ".join(pan) if pan else "không có"),
    ]
    readme = [
        f"Release: {rid}_v2",
        f"Parent: {rid}",
        f"Số ảnh: {len(kept)}",
        f"Số nhãn: {sum(counts.values())}",
        f"Guideline: {guideline}",
        f"QC v1: {len(err_targets)}/{len(man)} = {rate:.1%}".replace(".", ","),
        f"Kết luận v1: {v1_word} — {rate:.1%} ảnh lỗi, {'vượt' if rate > THRESHOLD else 'không vượt'} ngưỡng 2%".replace(".", ","),
        f"Kết luận v2: Release — tách {len(rework)} ảnh lỗi nhãn detection sang rework, sửa hash, guideline và split ngay trong v2; ảnh lỗi panoptic ở lại vì nhãn detection đúng",
        "Ghi chú: " + "; ".join(notes),
    ]
    (v2 / "README.txt").write_text("\n".join(readme) + "\n", encoding="utf-8")
    print(f"{v2}: {len(kept)} ảnh, {sum(counts.values())} nhãn, rework {len(rework)}, QC v1 {len(err_targets)}/{len(man)}")


if __name__ == "__main__":
    main()
