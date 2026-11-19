"""Validate file integrity and YOLO labels in a Lab 10 delivery."""

import argparse
import csv
import hashlib
import json
import math
from itertools import combinations
from pathlib import Path


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


def validate(delivery):
    manifest, _metadata, _jobs, _classes, panoptic = load_delivery(delivery)
    dimensions = {
        Path(image["file_name"]).name: (image["width"], image["height"])
        for image in panoptic["images"]
    }
    errors = []
    for target, item in manifest.items():
        image_path = delivery_file(delivery, item["image"])
        label_path = delivery_file(delivery, item["label"])
        mask_path = delivery_file(delivery, item["mask"])
        error = file_error(image_path, label_path, mask_path, item)
        if error is None:
            image_name = Path(item["image"]).name
            error = detection_error(read_boxes(label_path), *dimensions[image_name])
        if error is not None:
            errors.append({"type": error, "target": target})
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
