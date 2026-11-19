"""Validate file integrity, YOLO labels, metadata, and panoptic masks in a Lab 10 delivery."""

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.pngutil import read_rgb


# YOLO coordinates in the delivery are rounded to six decimal places.
COORD_TOLERANCE = 1e-6


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


def index_metadata(metadata):
    if isinstance(metadata, dict):
        return metadata, list(metadata.values())
    by_target = {}
    for item in metadata:
        for key in ("id", "target", "image", "image_id", "file_name"):
            val = item.get(key)
            if val is not None:
                by_target[str(val)] = item
                by_target[Path(str(val)).name] = item
                by_target[Path(str(val)).stem] = item
    return by_target, list(metadata)


def metadata_error(meta_item, jobs):
    job = jobs.get(meta_item["job_id"])
    if job is None:
        return "guideline_mismatch"
    actual = meta_item.get("guideline", meta_item.get("guideline_version"))
    expected = job.get("guideline", job.get("guideline_version"))
    if actual != expected:
        return "guideline_mismatch"
    return None


def scene_leak_errors(metadata_items):
    scene_splits = defaultdict(set)
    for item in metadata_items:
        scene_id = item.get("scene_id")
        split = item.get("split")
        if scene_id and split:
            scene_splits[scene_id].add(split)
    return [
        {"type": "scene_leak", "target": scene_id}
        for scene_id in sorted(scene_splits)
        if len(scene_splits[scene_id]) > 1
    ]


def panoptic_error(mask_path, annotation, valid_category_ids):
    segments = annotation["segments_info"]
    if any(seg["category_id"] not in valid_category_ids for seg in segments):
        return "invalid_category_id"

    _, _, pixels = read_rgb(mask_path)
    counts = Counter(
        r + (g << 8) + (b << 16)
        for r, g, b in zip(pixels[0::3], pixels[1::3], pixels[2::3])
    )
    counts.pop(0, None)

    for seg in segments:
        if counts.get(seg["id"], 0) != seg["area"]:
            return "thing_overlap"
    return None


def validate(delivery):
    manifest, metadata, jobs, _classes, panoptic = load_delivery(delivery)
    metadata_by_target, metadata_items = index_metadata(metadata)
    dimensions = {
        Path(image["file_name"]).name: (image["width"], image["height"])
        for image in panoptic["images"]
    }
    image_id_to_name = {
        image["id"]: Path(image["file_name"]).name
        for image in panoptic["images"]
    }
    annotations_by_image = {
        image_id_to_name[ann["image_id"]]: ann
        for ann in panoptic["annotations"]
        if ann["image_id"] in image_id_to_name
    }
    valid_category_ids = {cat["id"] for cat in panoptic["categories"]}

    errors = []
    for target, item in manifest.items():
        image_path = delivery_file(delivery, item["image"])
        label_path = delivery_file(delivery, item["label"])
        mask_path = delivery_file(delivery, item["mask"])
        image_name = Path(item["image"]).name

        error = file_error(image_path, label_path, mask_path, item)
        if error is None:
            error = detection_error(read_boxes(label_path), *dimensions[image_name])
        if error is None:
            meta_item = (
                metadata_by_target.get(target)
                or metadata_by_target.get(image_name)
                or metadata_by_target.get(Path(image_name).stem)
            )
            if meta_item is not None:
                error = metadata_error(meta_item, jobs)
        if error is None and image_name in annotations_by_image:
            error = panoptic_error(mask_path, annotations_by_image[image_name], valid_category_ids)
        if error is not None:
            errors.append({"type": error, "target": target})

    errors.extend(scene_leak_errors(metadata_items))
    return errors


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("delivery", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--candidates", type=Path, help="Write the candidate envelope for P2")
    args = parser.parse_args()
    if args.candidates is not None and args.candidates.resolve() == args.out.resolve():
        parser.error("--out and --candidates must be different files")
    try:
        errors = validate(args.delivery.resolve())
        write_json(args.out, {"errors": errors})
        if args.candidates is not None:
            # P2 will populate this list with detection/panoptic comparisons.
            write_json(args.candidates, {"candidates": []})
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")


if __name__ == "__main__":
    main()
