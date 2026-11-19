"""Trace an AI-team ticket back to images and people.

    python tools/trace_query.py <delivery> --out <trace.json>

Reads incoming/ticket.md (scenes the AI team names) and guideline/changelog.md (newest
version and the class whose rule changed), then:
- tier_a: images in the reported scenes, whose JOB uses an older guideline than the newest,
          and whose detection labels contain at least one box of the changed class;
- tier_b: every other image with the same condition (old-guideline job, has that class);
- notify: annotator and reviewer of the jobs holding tier a and tier b images.
The guideline comes from jobs.csv (per job), never from metadata.json (per image), because
the per-image value can itself be a guideline_mismatch error.
"""

import argparse
import csv
import json
import re
from pathlib import Path


def parse_changelog(text):
    versions = re.findall(r"^##\s*(v[\d.]+)", text, flags=re.M)
    newest = versions[0]
    section = text.split(f"## {newest}", 1)[1].split("\n## ", 1)[0]
    changed = re.findall(r"[Ll]ớp\s+`([^`]+)`", section)
    return newest, changed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("delivery", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    d = args.delivery
    newest, changed = parse_changelog((d / "guideline" / "changelog.md").read_text(encoding="utf-8"))
    scenes = set(re.findall(r"scene_\d+", (d / "incoming" / "ticket.md").read_text(encoding="utf-8")))
    with (d / "jobs.csv").open(encoding="utf-8", newline="") as f:
        jobs = {row["job_id"]: row for row in csv.DictReader(f)}
    meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))["items"]
    manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["items"]
    class_ids = set()
    for line in (d / "classes.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            k, v = line.split(maxsplit=1)
            if v.strip() in changed:
                class_ids.add(int(k))

    def has_class(image):
        path = d / manifest[image]["label"]
        if not path.is_file():
            return False
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if parts and int(float(parts[0])) in class_ids:
                return True
        return False

    tier_a, tier_b, jobs_hit = [], [], set()
    for m in meta:
        job = jobs.get(m["job_id"])
        if job is None or job["guideline"] == newest or not has_class(m["image"]):
            continue
        (tier_a if m["scene_id"] in scenes else tier_b).append(m["image"])
        jobs_hit.add(m["job_id"])
    notify = sorted({jobs[j]["annotator"] for j in jobs_hit} | {jobs[j]["reviewer"] for j in jobs_hit})
    result = {"tier_a": sorted(tier_a), "tier_b": sorted(tier_b), "notify": notify}
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"changed class {changed} (rule from {newest}), scenes {sorted(scenes)}: "
          f"tier_a {len(tier_a)}, tier_b {len(tier_b)}, notify {notify}")


if __name__ == "__main__":
    main()
