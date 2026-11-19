"""Validate a Lab 10 delivery: rule errors and detection <-> panoptic candidates.

    python validator/validate.py <delivery> --out <errors.json> [--candidates <candidates.json>]

Only reads the delivery folder passed in. Standard library only, plus the PNG reader
in scripts/pngutil.py (standard library as well). No network, no _private/, no COCO
annotations.

--out gets the rule errors (9 rule types). Labelling errors are never written there:
they go to --candidates and must be confirmed by looking at the image (review_log.csv),
then merged with scripts/merge_review.py.
"""

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pngutil import read_rgb  # noqa: E402


# YOLO coordinates in the delivery are rounded to six decimal places.
COORD_TOLERANCE = 1e-6

# ---- cross-check thresholds (measured on the clean batch, see submission/REPORT.md) ----
# On the clean batch 435/436 thing segments have >= 99.9% of their pixels inside the
# same-class detection box, so anything clearly below that is worth a look.
SHARE_OK = 0.98          # share of segment pixels inside its same-class box for a correct pair
MIN_AREA = 300           # segments smaller than this (pixels) are too small to judge
MATCH_IOU = 0.7          # other-class box this close to the segment = same object, other class
MERGE_SHARE = 0.2        # each of two same-class boxes holds at least this share of one segment
MERGE_MIN_PART = 0.005   # ...or the second box holds a small part and the two boxes hold it all


def delivery_file(delivery, relative_path):
    path = (delivery / relative_path).resolve()
    if not path.is_relative_to(delivery):
        raise ValueError(f"Path is outside delivery: {relative_path}")
    return path


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_delivery(delivery):
    manifest = read_json(delivery_file(delivery, "manifest.json"))["items"]
    metadata = read_json(delivery_file(delivery, "metadata.json"))["items"]
    panoptic = read_json(delivery_file(delivery, "panoptic.json"))
    with delivery_file(delivery, "jobs.csv").open(encoding="utf-8", newline="") as handle:
        jobs = {row["job_id"]: row for row in csv.DictReader(handle)}
    classes = {}
    for line in delivery_file(delivery, "classes.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            class_id, name = line.split(maxsplit=1)
            classes[int(class_id)] = name
    return manifest, metadata, jobs, classes, panoptic


# ------------------------------------------------------------------ file + detection rules

def file_error(image_path, label_path, mask_path, item):
    if not image_path.is_file():
        return "missing_image"

    for kind, path in (("image", image_path), ("label", label_path), ("mask", mask_path)):
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if digest != item[f"{kind}_sha256"]:
            return "wrong_hash"
    return None


def read_boxes(label_path):
    boxes = []
    for number, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            class_id, x, y, width, height = line.split()
            boxes.append((int(class_id), *map(float, (x, y, width, height))))
        except ValueError as error:
            raise ValueError(f"Invalid YOLO row in {label_path}:{number}") from error
    return boxes


def out_of_bounds(box):
    _, x, y, width, height = box
    return (
        not all(math.isfinite(value) for value in (x, y, width, height))
        or width <= 0
        or height <= 0
        or min(x - width / 2, y - height / 2) < -COORD_TOLERANCE
        or max(x + width / 2, y + height / 2) > 1 + COORD_TOLERANCE
    )


def detection_error(boxes, image_width, image_height):
    if any(not 0 <= box[0] < 80 for box in boxes):
        return "invalid_class"
    if any(out_of_bounds(box) for box in boxes):
        return "bbox_out_of_bounds"

    # Compare offsets on each pixel axis. Clipping at the edge can reduce an offset to zero.
    for first, second in combinations(boxes, 2):
        class_id, x, y, width, height = first
        other_id, other_x, other_y, other_width, other_height = second
        if (
            class_id == other_id
            and width == other_width
            and height == other_height
            and abs(x - other_x) <= 2 / image_width + COORD_TOLERANCE
            and abs(y - other_y) <= 2 / image_height + COORD_TOLERANCE
        ):
            return "duplicate_box"
    return None


# ------------------------------------------------------------------ metadata rules

def metadata_errors(metadata, jobs):
    """guideline_mismatch per image, scene_leak per scene (target = scene_id)."""
    image_errors = {}
    for item in metadata:
        job = jobs.get(item["job_id"])
        if job is not None and item["guideline_version"] != job["guideline"]:
            image_errors[item["image"]] = "guideline_mismatch"

    splits = defaultdict(set)
    for item in metadata:
        splits[item["scene_id"]].add(item["split"])
    leaked = sorted(scene for scene, values in splits.items() if len(values) > 1)
    return image_errors, leaked


# ------------------------------------------------------------------ panoptic

def read_segments(mask_path):
    """Return width, height and {segment id: [flat pixel indices]} for a panoptic mask."""
    width, height, pixels = read_rgb(mask_path)
    red, green, blue = pixels[0::3], pixels[1::3], pixels[2::3]
    segments = defaultdict(list)
    for index, (r, g, b) in enumerate(zip(red, green, blue)):
        segment = r + (g << 8) + (b << 16)
        if segment:
            segments[segment].append(index)
    return width, height, segments


def panoptic_rule_error(annotation, category_ids, segments):
    if any(info["category_id"] not in category_ids for info in annotation["segments_info"]):
        return "invalid_category_id"
    # thing_overlap: declared area larger than the pixels the segment really owns.
    for info in annotation["segments_info"]:
        if info["area"] > len(segments.get(info["id"], ())):
            return "thing_overlap"
    return None


# ------------------------------------------------------------------ cross-check

def box_pixels(box, width, height):
    _, x, y, w, h = box
    return (x - w / 2) * width, (y - h / 2) * height, (x + w / 2) * width, (y + h / 2) * height


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def share_inside(indices, width, rect):
    """Share of a segment's pixels whose pixel centre lies inside rect (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = rect
    inside = 0
    for index in indices:
        px, py = index % width + 0.5, index // width + 0.5
        if x0 - 1 <= px <= x1 + 1 and y0 - 1 <= py <= y1 + 1:
            inside += 1
    return inside / len(indices) if indices else 0.0


def share_inside_any(indices, width, rects):
    """Share of a segment's pixels inside at least one of the rects."""
    inside = 0
    for index in indices:
        px, py = index % width + 0.5, index // width + 0.5
        if any(x0 - 1 <= px <= x1 + 1 and y0 - 1 <= py <= y1 + 1 for x0, y0, x1, y1 in rects):
            inside += 1
    return inside / len(indices) if indices else 0.0


def pixel_bbox(indices, width):
    xs = [index % width for index in indices]
    ys = [index // width for index in indices]
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def cross_check(image, boxes, classes, annotation, categories, segments, width, height):
    """Candidates for one image. Each candidate names the signal that raised it.

    For every non-crowd thing segment, measure which share of its pixels falls inside each
    detection box. A correct pair keeps (almost) all pixels inside the box of its class.
    """
    dets = [{"index": i, "name": classes.get(box[0], "?"), "rect": box_pixels(box, width, height)}
            for i, box in enumerate(boxes)]
    candidates = []
    for info in annotation["segments_info"]:
        category = categories.get(info["category_id"])
        indices = segments.get(info["id"])
        if category is None or not category["isthing"] or info.get("iscrowd") or not indices:
            continue
        if len(indices) < MIN_AREA:
            continue
        name, bbox = category["name"], pixel_bbox(indices, width)
        same = sorted(((share_inside(indices, width, d["rect"]), iou(bbox, d["rect"]), d)
                       for d in dets if d["name"] == name), key=lambda t: -t[0])
        if same and same[0][0] >= SHARE_OK:
            continue  # explained by a box of the same class
        others = sorted(((iou(bbox, d["rect"]), share_inside(indices, width, d["rect"]), d)
                         for d in dets if d["name"] != name), key=lambda t: -t[0])
        base = {"image": image, "seg_class": name, "segment_id": info["id"], "area": len(indices),
                "seg_bbox": list(bbox)}
        best_same_iou = max((t[1] for t in same), default=0.0)

        # 1. another class sits exactly on the segment: class_swap (detection wrong)
        #    or category_swap (panoptic wrong). Only the image can tell which.
        if others and others[0][0] >= MATCH_IOU and others[0][1] >= SHARE_OK and best_same_iou < 0.5:
            other = others[0][2]
            candidates.append({**base, "type": "class_swap|category_swap",
                               "reason": f"box '{other['name']}' trùng vị trí segment '{name}'",
                               "det_class": other["name"], "box_index": other["index"],
                               "iou": round(others[0][0], 3)})
            continue
        # 2. one segment spread over two boxes of its class: instance_merge.
        #    Either both boxes hold a real part, or the pixels that leave the first box all
        #    land in a second same-class box (two objects relabelled as one segment).
        if len(same) >= 2 and (same[1][0] >= MERGE_SHARE or (
                same[1][0] >= MERGE_MIN_PART
                and share_inside_any(indices, width, [same[0][2]["rect"], same[1][2]["rect"]]) >= SHARE_OK)):
            candidates.append({**base, "type": "instance_merge",
                               "reason": "một segment nằm trong hai box cùng lớp",
                               "box_indexes": [same[0][2]["index"], same[1][2]["index"]],
                               "shares": [round(same[0][0], 3), round(same[1][0], 3)]})
            continue
        # 3. a same-class box near the segment but pixels leak out: bbox_drift
        if same and (same[0][0] > 0 or best_same_iou > 0):
            candidates.append({**base, "type": "bbox_drift",
                               "reason": "box cùng lớp lệch khỏi segment",
                               "box_index": same[0][2]["index"], "share_inside": round(same[0][0], 3),
                               "iou": round(same[0][1], 3)})
            continue
        # 4. no box of this class around the segment: missing_box
        candidates.append({**base, "type": "missing_box",
                           "reason": "segment thing không có box nào cùng lớp"})

    # Box side, no size limit: every detection box should hold a segment of its class.
    # Catches small objects the segment pass skips (MIN_AREA) and swaps on occluded objects.
    flagged = {c["segment_id"] for c in candidates}
    crowd_names = {categories[i["category_id"]]["name"] for i in annotation["segments_info"]
                   if i.get("iscrowd") and i["category_id"] in categories}
    things = []
    for info in annotation["segments_info"]:
        category = categories.get(info["category_id"])
        indices = segments.get(info["id"])
        if category and category["isthing"] and not info.get("iscrowd") and indices:
            things.append((info["id"], category["name"], indices))
    for det in dets:
        if det["name"] in crowd_names:
            continue
        shares = [(share_inside(idx, width, det["rect"]), seg_id, name, idx) for seg_id, name, idx in things]
        same = max((s for s in shares if s[2] == det["name"]), default=None, key=lambda s: s[0])
        if same is not None and same[0] >= SHARE_OK:
            continue
        other = max((s for s in shares if s[2] != det["name"]), default=None, key=lambda s: s[0])
        if (same is None or same[0] < 0.3) and other is not None and other[0] >= 0.95:
            share, seg_id, name, idx = other
            bbox = pixel_bbox(idx, width)
            if seg_id in flagged or iou(bbox, det["rect"]) < 0.5:
                continue
            # COCO sometimes labels one object twice (cup + wine glass, bus + truck). If a box of
            # the segment's own class already holds it, this box is a double label, not a swap.
            if any(d["name"] == name and share_inside(idx, width, d["rect"]) >= SHARE_OK for d in dets):
                continue
            flagged.add(seg_id)
            candidates.append({"image": image, "type": "class_swap|category_swap",
                               "reason": f"box '{det['name']}' không chứa segment cùng lớp, chỉ chứa segment '{name}'",
                               "seg_class": name, "det_class": det["name"], "segment_id": seg_id,
                               "area": len(idx), "seg_bbox": list(bbox), "box_index": det["index"],
                               "iou": round(iou(bbox, det["rect"]), 3)})
        elif same is not None and same[0] >= 0.3 and same[1] not in flagged:
            share, seg_id, name, idx = same
            flagged.add(seg_id)
            candidates.append({"image": image, "type": "bbox_drift",
                               "reason": "box lệch: một phần segment cùng lớp nằm ngoài box",
                               "seg_class": name, "segment_id": seg_id, "area": len(idx),
                               "seg_bbox": list(pixel_bbox(idx, width)), "box_index": det["index"],
                               "share_inside": round(share, 3)})
    return candidates


# ------------------------------------------------------------------ main

def validate(delivery, want_candidates=False):
    manifest, metadata, jobs, classes, panoptic = load_delivery(delivery)
    dimensions = {
        Path(image["file_name"]).name: (image["width"], image["height"])
        for image in panoptic["images"]
    }
    annotations = {Path(a["file_name"]).stem: a for a in panoptic["annotations"]}
    categories = {c["id"]: c for c in panoptic["categories"]}
    meta_errors, leaked_scenes = metadata_errors(metadata, jobs)

    errors, candidates = [], []
    for target, item in manifest.items():
        image_path = delivery_file(delivery, item["image"])
        label_path = delivery_file(delivery, item["label"])
        mask_path = delivery_file(delivery, item["mask"])
        error = file_error(image_path, label_path, mask_path, item)
        boxes = None
        if error is None:
            image_name = Path(item["image"]).name
            boxes = read_boxes(label_path)
            error = detection_error(boxes, *dimensions[image_name])
        if error is None:
            error = meta_errors.get(target)

        annotation = annotations.get(Path(item["mask"]).stem)
        segments = width = height = None
        if annotation is not None and mask_path.is_file():
            width, height, segments = read_segments(mask_path)
            if error is None:
                error = panoptic_rule_error(annotation, categories, segments)

        if error is not None:
            errors.append({"type": error, "target": target})
        elif want_candidates and segments is not None and boxes is not None:
            candidates.extend(cross_check(target, boxes, classes, annotation, categories,
                                          segments, width, height))

    errors.extend({"type": "scene_leak", "target": scene} for scene in leaked_scenes)
    return errors, candidates


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("delivery", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--candidates", type=Path, help="Write detection <-> panoptic candidates (P2)")
    args = parser.parse_args()
    if args.candidates is not None and args.candidates.resolve() == args.out.resolve():
        parser.error("--out and --candidates must be different files")
    try:
        errors, candidates = validate(args.delivery.resolve(), args.candidates is not None)
        write_json(args.out, {"errors": errors})
        if args.candidates is not None:
            write_json(args.candidates, {"candidates": candidates})
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")


if __name__ == "__main__":
    main()
