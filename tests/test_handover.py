import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class HandoverV2Test(unittest.TestCase):
    def test_v2_structure_and_manifest(self):
        v2_dir = ROOT / "submission" / "r2611" / "handover" / "lab250_d9d3c58cd7e6_v2"
        self.assertTrue(v2_dir.is_dir(), "Thư mục bàn giao v2 phải tồn tại")
        
        required_files = [
            "manifest.csv",
            "label_summary.csv",
            "truyvet.csv",
            "README.txt",
            "rework_queue.csv",
        ]
        for f in required_files:
            self.assertTrue((v2_dir / f).is_file(), f"Thiếu file: {f}")

        # Kiểm tra README.txt khớp tên release
        readme = (v2_dir / "README.txt").read_text(encoding="utf-8")
        self.assertIn("Release: lab250_d9d3c58cd7e6_v2", readme)
        self.assertIn("Parent: lab250_d9d3c58cd7e6", readme)
        self.assertIn("Số ảnh: 243", readme)

    def test_security_requirements(self):
        sec_file = ROOT / "submission" / "r2611" / "security.md"
        self.assertTrue(sec_file.is_file(), "Thiếu security.md trong submission")
        sec = sec_file.read_text(encoding="utf-8")
        self.assertIn("## 1. Ca USB", sec)
        self.assertIn("## 2. Năm việc", sec)
        self.assertIn("## 3. Ca khuôn mặt", sec)
        self.assertIn("Hold", sec)


if __name__ == "__main__":
    unittest.main()
