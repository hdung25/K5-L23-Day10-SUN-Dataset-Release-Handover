"""Chụp nội dung Google Sheet của nhóm vào repo (mỗi tab một file CSV).

    py tools/sheet_snapshot.py <file .xlsx tải từ Google Sheet> [--out docs/team_sheet]

Tải sheet: Tệp > Tải xuống > Microsoft Excel (.xlsx). Ô tích ghi là `x`, công thức ghi giá trị.
Cần openpyxl (chỉ cho công cụ này, validator không dùng).
"""

import argparse
import csv
import datetime
from pathlib import Path

import openpyxl

SLUG = {"Phân công": "01_phan_cong", "Tiến độ cá nhân": "02_tien_do_ca_nhan", "Thành viên": "03_thanh_vien",
        "Số liệu": "04_so_lieu", "Log chạy": "05_log_chay", "Review ảnh": "06_review_anh",
        "Note chung": "07_note_chung", "Checklist nộp": "08_checklist_nop"}


def fmt(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "x" if value else ""
    if isinstance(value, datetime.datetime):
        return value.strftime("%d/%m %H:%M")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).replace("\n", " ")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xlsx", type=Path)
    ap.add_argument("--out", type=Path, default=Path("docs/team_sheet"))
    args = ap.parse_args()
    wb = openpyxl.load_workbook(args.xlsx, data_only=True)
    args.out.mkdir(parents=True, exist_ok=True)
    for old in args.out.glob("*.csv"):
        old.unlink()
    for name in wb.sheetnames:
        rows = [[fmt(c) for c in r] for r in wb[name].iter_rows(values_only=True)]
        rows = [r for r in rows if any(r)]
        width = max((max((i + 1 for i, v in enumerate(r) if v), default=0) for r in rows), default=0)
        path = args.out / f"{SLUG.get(name, name)}.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(r[:width] for r in rows)
        print(f"{name}: {len(rows) - 1} dòng -> {path}")


if __name__ == "__main__":
    main()
