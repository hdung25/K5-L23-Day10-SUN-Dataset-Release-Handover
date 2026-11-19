"""Draw each candidate so a reviewer can decide by looking at the image.

    python tools/view_candidates.py <delivery> <candidates.json> --out <folder>

For every candidate it writes <folder>/<image>_<n>.png with two panels:
  left  = the whole image, every detection box (class name on top), the suspect
          segment outlined in yellow;
  right = a crop around the suspect region, enlarged, same drawing.
Red box = the box the candidate points at. Green boxes = other boxes.

This is a review helper, not part of the validator, so it may use Pillow.
"""

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pngutil import read_rgb  # noqa: E402

PANEL = 640


def load(delivery):
    classes = {}
    for line in (delivery / "classes.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            k, v = line.split(maxsplit=1)
            classes[int(k)] = v
    pan = json.loads((delivery / "panoptic.json").read_text(encoding="utf-8"))
    anns = {Path(a["file_name"]).stem: a for a in pan["annotations"]}
    cats = {c["id"]: c["name"] for c in pan["categories"]}
    manifest = json.loads((delivery / "manifest.json").read_text(encoding="utf-8"))["items"]
    return classes, anns, cats, manifest


def boxes_px(label_path, w, h, classes):
    out = []
    for line in label_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            c, x, y, bw, bh = line.split()
            x, y, bw, bh = map(float, (x, y, bw, bh))
            out.append((classes.get(int(c), f"?{c}"), ((x - bw / 2) * w, (y - bh / 2) * h, (x + bw / 2) * w, (y + bh / 2) * h)))
    return out


def outline(mask_w, mask_h, pixels, seg_id):
    """Pixels on the border of the segment."""
    def sid(i):
        return pixels[3 * i] + (pixels[3 * i + 1] << 8) + (pixels[3 * i + 2] << 16)
    inside = set(i for i in range(mask_w * mask_h) if sid(i) == seg_id)
    edge = []
    for i in inside:
        x, y = i % mask_w, i // mask_w
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if not (0 <= nx < mask_w and 0 <= ny < mask_h) or ny * mask_w + nx not in inside:
                edge.append((x, y))
                break
    return edge


def draw(img, boxes, highlight, edge, scale=1.0, offset=(0, 0)):
    d = ImageDraw.Draw(img)
    ox, oy = offset
    for k, (name, (x0, y0, x1, y1)) in enumerate(boxes):
        color = (255, 40, 40) if k in highlight else (40, 220, 40)
        r = [(x0 - ox) * scale, (y0 - oy) * scale, (x1 - ox) * scale, (y1 - oy) * scale]
        d.rectangle(r, outline=color, width=3 if k in highlight else 1)
        d.text((r[0] + 2, r[1] + 1), f"{k}:{name}", fill=color)
    for x, y in edge:
        px, py = (x - ox) * scale, (y - oy) * scale
        d.rectangle([px, py, px + max(1, scale) - 1, py + max(1, scale) - 1], fill=(255, 230, 0))


def render(delivery, cand, classes, anns, cats, manifest, out_path):
    item = manifest[cand["image"]]
    image = Image.open(delivery / item["image"]).convert("RGB")
    w, h = image.size
    mw, mh, pixels = read_rgb(delivery / item["mask"])
    boxes = boxes_px(delivery / item["label"], w, h, classes)
    highlight = set(cand.get("box_indexes", [])) | ({cand["box_index"]} if "box_index" in cand else set())
    edge = outline(mw, mh, pixels, cand["segment_id"])

    full = image.copy()
    s_full = PANEL / max(w, h)
    full = full.resize((int(w * s_full), int(h * s_full)))
    draw(full, boxes, highlight, edge, s_full)

    x0, y0, x1, y1 = cand["seg_bbox"]
    for k in highlight:
        bx = boxes[k][1]
        x0, y0, x1, y1 = min(x0, bx[0]), min(y0, bx[1]), max(x1, bx[2]), max(y1, bx[3])
    pad = 0.15 * max(x1 - x0, y1 - y0) + 10
    cx0, cy0 = max(0, int(x0 - pad)), max(0, int(y0 - pad))
    cx1, cy1 = min(w, int(x1 + pad)), min(h, int(y1 + pad))
    crop = image.crop((cx0, cy0, cx1, cy1))
    s_crop = PANEL / max(cx1 - cx0, cy1 - cy0)
    crop = crop.resize((max(1, int((cx1 - cx0) * s_crop)), max(1, int((cy1 - cy0) * s_crop))))
    draw(crop, boxes, highlight, edge, s_crop, (cx0, cy0))

    sheet = Image.new("RGB", (full.width + crop.width + 10, max(full.height, crop.height) + 40), (30, 30, 30))
    sheet.paste(full, (0, 40))
    sheet.paste(crop, (full.width + 10, 40))
    title = f"{cand['image']}  {cand['type']}  seg={cand['seg_class']}" + (f"  det={cand['det_class']}" if "det_class" in cand else "")
    ImageDraw.Draw(sheet).text((6, 6), title + "   |  " + cand["reason"], fill=(255, 255, 255))
    sheet.save(out_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("delivery", type=Path)
    ap.add_argument("candidates", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    classes, anns, cats, manifest = load(args.delivery)
    cands = json.loads(args.candidates.read_text(encoding="utf-8"))["candidates"]
    args.out.mkdir(parents=True, exist_ok=True)
    for n, cand in enumerate(cands):
        path = args.out / f"{cand['image']}_{n}.png"
        render(args.delivery, cand, classes, anns, cats, manifest, path)
        print(path)


if __name__ == "__main__":
    main()
