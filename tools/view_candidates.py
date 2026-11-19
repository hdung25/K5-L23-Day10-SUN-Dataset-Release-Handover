"""Day 10: xem ứng viên detection và panoptic, lưu review chung cho nhóm."""

from __future__ import annotations  # Hoãn xử lý chú thích kiểu để các kiểu khai báo sau vẫn dùng được.

import argparse  # Đọc tham số mà người dùng nhập khi chạy lệnh.
import csv  # Đọc và ghi CSV, kể cả ghi chú chứa dấu phẩy.
import hmac  # So sánh mã truy cập với thời gian so sánh ổn định.
import io  # Tạo bộ đệm văn bản để người dùng tải CSV.
import json  # Chuyển đổi dữ liệu JSON giữa tệp, máy chủ và trình duyệt.
import math  # Kiểm tra tọa độ hộp có phải số hữu hạn.
import os  # Lấy kích thước tệp và thay CSV sau khi ghi thành công.
import re  # Kiểm tra định dạng số ID, kích thước và đường dẫn endpoint.
import secrets  # Sinh mã truy cập ngẫu nhiên cho phiên review nhóm.
import shutil  # Truyền từng phần ảnh hoặc mask sang trình duyệt.
import socket  # Tìm địa chỉ IPv4 của máy chạy tool.
import sys  # Gửi lỗi vào luồng lỗi, tách với thông báo khởi động.
import tempfile  # Ghi CSV vào một tệp tạm trước khi thay tệp kết quả.
import threading  # Đồng bộ thao tác lưu khi nhiều người truy cập đồng thời.
from http import HTTPStatus  # Dùng tên chuẩn cho mã trạng thái HTTP.
# Đọc cookie truy cập và xử lý trường hợp cookie sai cú pháp.
from http.cookies import CookieError, SimpleCookie
# Nhận yêu cầu HTTP và phục vụ đồng thời nhiều trình duyệt.
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path  # Thao tác với đường dẫn trên Windows và các hệ điều hành khác.
from urllib.parse import parse_qs, urlsplit  # Tách địa chỉ yêu cầu và đọc các tham số như id, key.


SWAPS = ("class_swap", "category_swap")  # Hai lỗi lệch nhãn này có thể đổi cho nhau trong cùng ứng viên.
# Chỉ đưa các loại lỗi thị giác vào hàng đợi xem ảnh.
TYPES = (*SWAPS, "bbox_drift", "missing_box", "instance_merge")
FIELDS = ("image", "type", "verdict", "note")  # Giữ tên và thứ tự các cột theo đầu vào merge_review.py.
PAGE = Path(__file__).with_name("view_candidates.html")  # Tìm giao diện ngay bên cạnh tệp Python.
PANEL = 640  # Kích thước chuẩn (pixel) cho mỗi khung ảnh khi xuất PNG bằng Pillow.


def read_json(path):  # Đọc một tệp JSON do lab hoặc validator tạo.
    # Chấp nhận UTF-8 có BOM từ một số trình soạn thảo.
    return json.loads(path.read_text(encoding="utf-8-sig"))


def review_key(image, kind):  # Tạo khóa ổn định cho từng ảnh và lỗi cần xem.
    # Gộp hai cách phân loại lệch nhãn (hoặc chuỗi ghép class_swap|category_swap) vào một khóa review.
    return image, SWAPS[0] if kind in (*SWAPS, "class_swap|category_swap") else kind


def candidates_from(path, manifest):  # Chuyển kết quả validator thành hàng đợi gửi cho giao diện.
    rows = read_json(path)  # Nạp danh sách hoặc đối tượng bao quanh các ứng viên.
    if isinstance(rows, dict):  # Nhận diện đầu vào JSON có khóa chứa danh sách.
        # Ưu tiên khóa candidates, hỗ trợ thêm định dạng errors.
        rows = rows.get("candidates", rows.get("errors"))
    if not isinstance(rows, list):  # Dừng sớm nếu cấu trúc đọc được sai định dạng.
        # Báo rõ cấu trúc để sửa ở phần xuất của validator.
        raise ValueError("candidates.json cần danh sách ứng viên hoặc khóa 'candidates'.")

    items = {}  # Giữ thứ tự chèn và loại ứng viên trùng theo khóa.
    for line, row in enumerate(rows, 1):  # Đánh số mục từ 1 để thông báo lỗi dễ tra.
        if not isinstance(row, dict):  # Mỗi mục cần trường ảnh và loại lỗi.
            # Chỉ rõ vị trí của mục có cấu trúc sai.
            raise ValueError(f"Ứng viên số {line} phải là một object.")
        image = row.get("image", row.get("target"))  # Chấp nhận tên trường image hoặc target.
        raw_kind = row.get("type")  # Lấy loại lỗi dự kiến từ validator.
        # Chuẩn hóa trường hợp validator xuất "class_swap|category_swap" cho cặp lệch lớp.
        kind = SWAPS[0] if raw_kind == "class_swap|category_swap" else raw_kind
        # Thử chuẩn hóa nếu giá trị là tên tệp có đuôi hoặc đường dẫn.
        if isinstance(image, str) and image not in manifest:
            image = Path(image).stem  # Bỏ đuôi tệp để khớp ID ảnh trong manifest.
        # Kiểm tra ID ảnh tồn tại và loại lỗi được hỗ trợ.
        if not isinstance(image, str) or image not in manifest or kind not in TYPES:
            # Cho biết mục lỗi cùng hai giá trị đầu vào liên quan.
            raise ValueError(f"Ứng viên số {line} có tên ảnh hoặc loại lỗi không hợp lệ: {image!r}, {raw_kind!r}.")

        # Tìm mô tả gợi ý trong các trường xuất thường gặp.
        hint = row.get("hint") or row.get("reason") or row.get("note") or ""
        if not isinstance(hint, str):  # Giao diện chỉ hiển thị gợi ý dạng văn bản.
            hint = ""  # Bỏ qua gợi ý có kiểu dữ liệu khác.
        key = review_key(image, kind)  # Chuẩn hóa khóa trước khi kiểm tra trùng.
        if key in items:  # Xử lý ứng viên đã xuất hiện cho ảnh và loại lỗi này.
            if hint and hint not in items[key]["hint"].split("\n"):  # Chỉ bổ sung gợi ý có nội dung mới.
                # Ghép các gợi ý thành từng dòng để người xem đọc đủ.
                items[key]["hint"] = "\n".join(filter(None, [items[key]["hint"], hint]))
            continue  # Dùng mục đã có, tránh tạo thêm một lượt xem trùng.
        # Cho phép đổi giữa hai lỗi lệch nhãn, hoặc đổi giữa các loại lỗi gán nhãn khi nhìn ảnh.
        choices = list(SWAPS) if kind in SWAPS else [kind, *[t for t in TYPES if t != kind]]
        items[key] = {  # Tạo dữ liệu tối thiểu mà trình duyệt cần để mở mục.
            "id": len(items) + 1,  # Gán số ID ổn định theo thứ tự xuất hiện.
            "image": image,  # Giữ ID ảnh đúng theo manifest, kể cả số 0 ở đầu.
            "type": kind,  # Hiện loại lỗi ban đầu để người xem đối chiếu.
            "hint": hint,  # Giữ lý do ứng viên bị gắn cờ nếu có.
            "choices": choices,  # Danh sách loại lỗi người xem được chọn khi lưu kết luận.
        }
    # Lập bảng tra theo số ID để endpoint mở nhanh ứng viên.
    return {item["id"]: item for item in items.values()}


def class_names(path):  # Đọc bảng ánh xạ ID lớp YOLO sang tên lớp.
    names = {}  # Tạo bảng tra tên theo mã lớp.
    for line in path.read_text(encoding="utf-8-sig").splitlines():  # Duyệt từng dòng của tệp classes.txt.
        parts = line.split(maxsplit=1)  # Tách một lần để giữ dấu cách bên trong tên lớp.
        if len(parts) == 2:  # Chỉ lấy dòng có đủ cả mã và tên lớp.
            index, name = parts  # Tách giá trị số và nhãn văn bản.
            names[int(index)] = name  # Lưu mã dạng số để khớp với nhãn YOLO.
    return names  # Trả bảng tra cho phần dựng hộp.


def box(label, x, y, width, height):  # Chuẩn hóa hình chữ nhật để giao diện vẽ trên ảnh.
    # Dùng góc trên trái và kích thước, theo tọa độ tương đối.
    return {"label": label, "x": x, "y": y, "w": width, "h": height}


class ReviewData:  # Quản lý dữ liệu lô, ứng viên và kết quả review dùng chung.
    def __init__(self, delivery, candidates, output):  # Chuẩn bị các bảng tra một lần khi mở phiên review.
        self.delivery = delivery.resolve()  # Chuẩn hóa thư mục dữ liệu để kiểm tra phạm vi đọc tệp.
        self.output = output.resolve()  # Chuẩn hóa đường dẫn đích để kiểm tra nơi được phép ghi.
        # Yêu cầu CSV nằm ngoài dữ liệu đề để giữ nguyên delivery.
        if self.output.suffix.lower() != ".csv" or self.output.is_relative_to(self.delivery):
            # Chỉ rõ điều kiện của đường dẫn đầu ra.
            raise ValueError("Chọn file .csv đầu ra bên ngoài delivery/.")
        if self.output == candidates.resolve():  # Kiểm tra CSV và danh sách ứng viên là hai tệp riêng.
            # Chặn trường hợp kết quả ghi đè đầu vào.
            raise ValueError("File đầu ra phải khác file ứng viên.")
        # Lấy metadata đường dẫn ảnh, nhãn và mask theo ID ảnh.
        self.manifest = read_json(self.delivery / "manifest.json")["items"]
        # Xác thực danh sách và giữ hàng đợi để phục vụ các lần xem.
        self.items = candidates_from(candidates, self.manifest)
        # Nạp tên lớp để giao diện hiển thị thay cho mã số.
        self.names = class_names(self.delivery / "classes.txt")
        # Đọc thông tin ảnh và segment panoptic do lab giao.
        pano = read_json(self.delivery / "panoptic.json")
        # Tạo bảng tra kích thước theo ID ảnh lấy từ tên tệp.
        self.pan_images = {Path(row["file_name"]).stem: row for row in pano["images"]}
        # Ghép chú thích panoptic với metadata qua image_id.
        self.annotations = {row["image_id"]: row for row in pano["annotations"]}
        # Giải mã category_id của segment sang tên lớp.
        self.categories = {row["id"]: row["name"] for row in pano["categories"]}
        self.lock = threading.Lock()  # Dùng một khóa chung cho mọi thao tác đọc và lưu CSV.
        self.read_reviews()  # Kiểm tra tệp kết quả cũ trước khi phục vụ người xem.

    def asset(self, item, key):  # Tra đường dẫn ảnh, nhãn hoặc mask theo manifest.
        relative = self.manifest[item["image"]].get(key)  # Lấy đường dẫn được khai báo cho ảnh hiện tại.
        # Giới hạn mỗi loại tệp trong thư mục tương ứng.
        folder = {"image": "images", "label": "labels", "mask": "masks"}[key]
        # Giới hạn đuôi tệp phù hợp với loại nội dung.
        extension = {"image": ".jpg", "label": ".txt", "mask": ".png"}[key]
        # Chấp nhận đường dẫn tương đối dạng văn bản từ manifest.
        if not isinstance(relative, str) or Path(relative).is_absolute():
            return None  # Đánh dấu tài nguyên thiếu nếu đường dẫn sai định dạng.
        path = (self.delivery / relative).resolve()  # Giải đường dẫn và liên kết trước khi kiểm tra phạm vi.
        # Chỉ trả tệp có thật, đúng đuôi và nằm trong thư mục được phép.
        if path.is_relative_to(self.delivery / folder) and path.suffix.lower() == extension and path.is_file():
            return path  # Trả đường dẫn đã kiểm tra cho phần đọc nội dung.
        return None  # Cho phép giao diện xử lý khi tài nguyên vắng mặt.

    def detection_boxes(self, path):  # Chuyển hộp YOLO sang hệ tọa độ dùng trên giao diện.
        if path is None:  # Kiểm tra ảnh có kèm tệp nhãn hợp lệ hay chưa.
            return []  # Vẫn cho xem ảnh khi không có hộp YOLO.
        boxes = []  # Giữ các hộp đọc được từ nhãn.
        # Đọc từng dòng; ký tự hỏng sẽ làm dòng đó được bỏ qua khi tách số.
        for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            parts = line.split()  # Tách mã lớp và bốn giá trị giữa các khoảng trắng.
            if len(parts) != 5:  # Chỉ phân tích dòng có đủ đúng năm trường YOLO.
                continue  # Bỏ qua dòng thiếu hoặc thừa trường.
            try:  # Đổi các trường văn bản sang số.
                index = int(parts[0])  # Đọc ID lớp ở đầu dòng.
                # Đọc tâm, chiều rộng và chiều cao theo tỷ lệ YOLO.
                cx, cy, width, height = map(float, parts[1:])
            except ValueError:  # Một trường sai kiểu số sẽ làm dòng không thể vẽ.
                continue  # Tiếp tục dựng hộp từ các dòng còn lại.
            # Đổi tâm sang góc trên trái, giữ chiều rộng và chiều cao.
            edges = (cx - width / 2, cy - height / 2, width, height)
            # Bỏ hộp suy biến hoặc chứa giá trị vô hạn hay NaN.
            if width > 0 and height > 0 and all(map(math.isfinite, edges)):
                # Đính tên lớp, hoặc mã gốc nếu tên lớp chưa có trong bảng.
                boxes.append(box(self.names.get(index, f"ID {index}"), *edges))
        return boxes  # Trả các hộp vẽ được theo thứ tự tệp nhãn.

    def image_detail(self, item):  # Chuẩn bị toàn bộ dữ liệu trực quan cho một ứng viên.
        item_id, name = item["id"], item["image"]  # Lấy số ID endpoint và ID ảnh trong manifest.
        image = self.pan_images.get(name, {})  # Tra thông tin ảnh panoptic, cho phép thiếu bản ghi.
        # Lấy kích thước ảnh để quy đổi bbox từ pixel sang tỷ lệ.
        width, height = image.get("width"), image.get("height")
        # Nối metadata với danh sách segment qua id số.
        annotations = self.annotations.get(image.get("id"), {})
        segments = []  # Giữ các hộp bao segment mà giao diện dùng để chọn vùng.
        if width and height:  # Chỉ tính tỷ lệ khi cả hai chiều đều có giá trị.
            # Duyệt từng segment được khai báo cho ảnh hiện tại.
            for row in annotations.get("segments_info", []):
                if len(row.get("bbox", [])) != 4:  # Kiểm tra bbox panoptic có cấu trúc bốn giá trị.
                    continue  # Bỏ dòng thiếu bbox hợp lệ để những vùng khác vẫn xem được.
                x, y, w, h = row["bbox"]  # Lấy góc trên trái và kích thước trong hệ pixel.
                # Hiện tên lớp panoptic, để lại mã nếu không tìm thấy tên.
                label = self.categories.get(row["category_id"], f"ID {row['category_id']}")
                if row.get("iscrowd"):  # Kiểm tra segment được đánh dấu là nhóm đối tượng.
                    label += " (crowd)"  # Gắn nhãn crowd để người xem nhận biết.
                # Chia theo kích thước ảnh để vẽ đúng khi phóng to.
                segments.append(box(label, x / width, y / height, w / width, h / height))
        return {  # Trả gói dữ liệu một mục cho giao diện.
            # Báo URL ảnh nếu manifest trỏ tới tệp có thật.
            "photo": f"/asset/{item_id}/photo" if self.asset(item, "image") else None,
            # Báo URL mask nếu có thể phục vụ mask.
            "mask": f"/asset/{item_id}/mask" if self.asset(item, "mask") else None,
            "width": width,  # Giữ chiều rộng gốc để giao diện quy đổi vùng.
            "height": height,  # Giữ chiều cao gốc để giao diện quy đổi vùng.
            "boxes": self.detection_boxes(self.asset(item, "label")),  # Đọc hộp YOLO của ảnh tương ứng.
            "segments": segments,  # Gửi các vùng theo panoptic để đối chiếu vị trí và lớp.
        }

    def read_reviews(self):  # Đọc và kiểm tra kết quả từ các phiên review đã lưu.
        # Có thể bắt đầu phiên mới khi chưa có nội dung CSV.
        if not self.output.exists() or not self.output.stat().st_size:
            return {}  # Dùng bảng kết quả rỗng cho phiên chưa có phiếu.
        result = {}  # Lập chỉ mục theo khóa ảnh và loại lỗi.
        # Để bộ đọc CSV tự xử lý các kiểu xuống dòng trong tệp.
        with self.output.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)  # Mỗi dòng trả về từ điển theo tên cột CSV.
            if reader.fieldnames != list(FIELDS):  # Kiểm tra định dạng khớp với đầu vào merge_review.py.
                # Dừng khi tiêu đề sai để tránh làm mất dữ liệu cũ.
                raise ValueError("review_log.csv cần đúng các cột image,type,verdict,note.")
            for row in reader:  # Kiểm tra đầu vào từng dòng trước khi nạp.
                # Tách ID khỏi bản ghi kết quả gửi lên giao diện.
                image, kind = row.pop("image"), row["type"]
                # Phát hiện cột thừa, ID ảnh sai hoặc loại lỗi không được hỗ trợ.
                if None in row or not image or image not in self.manifest or kind not in TYPES:
                    # Hiện số dòng nơi kết quả cần sửa.
                    raise ValueError(f"review_log.csv có ảnh hoặc loại lỗi không hợp lệ (dòng {reader.line_num}).")
                # Kiểm tra đúng hai kết luận của bài và cột ghi chú tồn tại.
                if row["verdict"] not in ("confirmed", "rejected") or row["note"] is None:
                    # Dừng để người dùng sửa verdict hoặc số lượng cột.
                    raise ValueError(f"review_log.csv có verdict hoặc note không hợp lệ (dòng {reader.line_num}).")
                key = review_key(image, kind)  # Dùng cùng quy tắc khóa như khi tạo ứng viên.
                if key in result:  # Một khóa chỉ có một kết quả mới nhất.
                    # Báo trùng để người dùng quyết định giữ dòng nào.
                    raise ValueError(f"review_log.csv có nhiều kết quả cho cùng ứng viên ảnh {image}.")
                result[key] = row  # Lưu dữ liệu từng dòng khi mọi điều kiện đều hợp lệ.
        return result  # Trả chỉ mục kết quả cho các route đọc và ghi.

    def write_reviews(self, reviews):  # Lưu toàn bộ CSV chung qua một lần thay tệp.
        # Tạo thư mục đích để tool chạy được ở đường dẫn mới.
        self.output.parent.mkdir(parents=True, exist_ok=True)
        temp = None  # Chuẩn bị biến theo dõi tệp tạm để dọn dẹp khi có lỗi.
        try:  # Bảo đảm có bước dọn tệp tạm sau khi ghi.
            with tempfile.NamedTemporaryFile(  # Dùng tệp tạm cùng thư mục để bước thay tệp chạy cùng ổ đĩa.
                # Giữ tệp tạm sau khi đóng và để csv quản lý xuống dòng.
                "w", encoding="utf-8", newline="", dir=self.output.parent, delete=False,
            ) as target:  # Mở tệp tạm trong khối with để tự đóng sau khi ghi.
                temp = Path(target.name)  # Lưu đường dẫn; bộ ghi cần đóng tệp trước khi đổi tên.
                writer = csv.DictWriter(target, fieldnames=FIELDS)  # Bảo đảm đúng tập cột và thứ tự yêu cầu.
                writer.writeheader()  # Ghi hàng tiêu đề kể cả khi chưa có kết quả.
                for (image, _), review in reviews.items():  # Duyệt mọi kết quả đã được thêm hoặc cập nhật.
                    # Ghép ID ảnh với type, verdict và note của kết quả.
                    writer.writerow({"image": image, **review})
            os.replace(temp, self.output)  # Thay tệp cũ khi nội dung tạm đã ghi và đóng đầy đủ.
        finally:  # Dọn sau cả trường hợp thành công lẫn lỗi lưu.
            if temp is not None:  # Chỉ thao tác khi thật sự đã tạo tên tệp tạm.
                temp.unlink(missing_ok=True)  # Xóa tệp tạm còn sót; sau khi thay thành công tên này đã mất.

    def initialize_csv(self):  # Chuẩn bị CSV sẵn sàng để script gộp kết quả đọc được.
        # Phát hiện tệp chưa tồn tại hoặc chưa có byte nào.
        if not self.output.exists() or not self.output.stat().st_size:
            self.write_reviews({})  # Tạo CSV chỉ có tiêu đề.
            return  # Kết thúc vì lần ghi đầu đã tạo đúng bảng.
        with self.output.open("rb") as source:  # Kiểm tra byte đầu của CSV hiện có để nhận biết BOM.
            has_bom = source.read(3) == b"\xef\xbb\xbf"  # UTF-8 BOM, nếu có, chiếm đúng ba byte này.
        if has_bom:  # Chỉ chuẩn hóa khi CSV có BOM.
            # Ghi lại dữ liệu hiện có để tạo UTF-8 như script gộp cần.
            self.write_reviews(self.read_reviews())

    def list_items(self):  # Trả hàng đợi kèm trạng thái mới nhất cho các trình duyệt.
        with self.lock:  # Chờ thao tác lưu kết thúc rồi đọc kết quả.
            reviews = self.read_reviews()  # Đọc lại từ CSV để lần mở kế tiếp thấy bản đã lưu.
            return [  # Tạo danh sách trình duyệt có thể duyệt ngay.
                # Ghép ứng viên với kết quả đã lưu, hoặc None khi chưa review.
                {**item, "review": reviews.get(review_key(item["image"], item["type"]))}
                for item in self.items.values()  # Giữ thứ tự ứng viên do validator xuất.
            ]

    def save(self, payload):  # Xác thực yêu cầu và lưu đúng một kết luận của người review.
        # Yêu cầu ID số nguyên và phiên bản cũ để phát hiện xung đột.
        if not isinstance(payload, dict) or type(payload.get("id")) is not int or "previous" not in payload:
            raise ValueError("Dữ liệu review chưa đầy đủ.")  # Trả lỗi đầu vào trước khi đọc hoặc thay CSV.
        item = self.items.get(payload["id"])  # Tìm mục cần cập nhật theo ID mà giao diện gửi.
        # Lấy đủ ba trường sẽ ghi vào nhật ký.
        verdict, kind, note = payload.get("verdict"), payload.get("type"), payload.get("note")
        # Kiểm tra loại lỗi được phép đổi và verdict đúng quy định.
        if not item or kind not in item["choices"] or verdict not in ("confirmed", "rejected"):
            # Báo lỗi để người review sửa lựa chọn trước khi gửi lại.
            raise ValueError("Ứng viên, loại lỗi hoặc kết luận không hợp lệ.")
        # Đếm phần ghi chú thực tế sau khi bỏ khoảng trắng hai đầu.
        if not isinstance(note, str) or not 20 <= len(note.strip()) <= 2000:
            # Giữ ngưỡng tối thiểu của bài và giới hạn độ dài hợp lý.
            raise ValueError("Ghi chú cần từ 20 đến 2000 ký tự.")

        # Xác định bản ghi ổn định kể cả khi đổi giữa hai lỗi lệch nhãn.
        key = review_key(item["image"], kind)
        # Chuẩn bị đúng ba trường trước khi ghép với ID ảnh.
        review = {"type": kind, "verdict": verdict, "note": note.strip()}
        with self.lock:  # Khóa toàn bộ chuỗi đọc, so sánh và ghi để tránh mất cập nhật.
            reviews = self.read_reviews()  # Lấy phiên bản mới nhất từ tệp chung.
            current = reviews.get(key)  # Tìm kết quả hiện hành cho đúng ảnh và loại lỗi.
            # Phát hiện người khác đã lưu một kết quả khác kể từ lúc đọc.
            if current != payload["previous"] and current != review:
                return None  # Báo xung đột để trình duyệt yêu cầu làm mới.
            if current != review:  # Chỉ ghi lại tệp khi dữ liệu thực sự thay đổi.
                reviews[key] = review  # Cập nhật bản ghi duy nhất cho khóa này.
                self.write_reviews(reviews)  # Ghi toàn bộ bảng bằng thao tác thay tệp an toàn.
        return review  # Trả kết quả đã lưu để giao diện làm mới trạng thái.

    def download_csv(self):  # Xuất nội dung CSV mới nhất cho nút tải kết quả.
        with self.lock:  # Đọc dưới cùng khóa dùng khi lưu để lấy bản nhất quán.
            reviews = self.read_reviews()  # Nạp bản ghi hiện hành từ CSV.
            result = io.StringIO(newline="")  # Tạo luồng văn bản tạm trong bộ nhớ.
            writer = csv.DictWriter(result, fieldnames=FIELDS)  # Viết đúng định dạng như tệp lưu hiện có.
            writer.writeheader()  # Thêm tiêu đề để bản tải về dùng được khi bảng trống.
            for (image, _), review in reviews.items():  # Duyệt các kết quả đã lưu theo thứ tự.
                writer.writerow({"image": image, **review})  # Ghi một dòng kèm ID ảnh vào phần tải xuống.
            return result.getvalue().encode("utf-8")  # Đổi văn bản sang byte UTF-8 để gửi qua HTTP.


class ReviewServer(ThreadingHTTPServer):  # Máy chủ giữ dữ liệu dùng chung cho các kết nối song song.
    def __init__(self, address, data, share):  # Nhận địa chỉ lắng nghe, dữ liệu lô và chế độ chia sẻ.
        super().__init__(address, Handler)  # Khởi tạo bộ xử lý HTTP cho mỗi kết nối.
        self.data = data  # Đặt dữ liệu lô ở máy chủ để các kết nối dùng chung.
        self.page = PAGE.read_bytes()  # Đọc HTML một lần, khi bắt đầu phiên.
        # Tạo mã dùng trong liên kết nếu có người khác truy cập qua LAN.
        self.key = secrets.token_urlsafe(18) if share else None
        # Đặt tên cookie theo cổng để nhiều phiên trên một máy dễ phân biệt.
        self.cookie_name = f"review_{self.server_port}"


class Handler(BaseHTTPRequestHandler):  # Đọc yêu cầu HTTP và điều hướng đến thao tác tương ứng.
    def log_message(self, format, *args):  # Ghi đè nhật ký mặc định của HTTP server.
        pass  # Bỏ log đường dẫn vì query của liên kết có thể chứa mã truy cập.

    # Gửi phần đầu phản hồi trước khi gửi nội dung.
    def headers_for(self, code, content_type, length, **extra):
        self.send_response(code)  # Khai báo mã thành công, lỗi hay chuyển hướng.
        # Báo cho trình duyệt cách đọc byte mà máy chủ sẽ gửi.
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))  # Khai báo số byte để trình duyệt đọc đủ nội dung.
        self.send_header("Cache-Control", "no-store")  # Yêu cầu trình duyệt luôn đọc phiên và dữ liệu mới.
        # Tránh gửi địa chỉ của trang có mã truy cập qua Referer.
        self.send_header("Referrer-Policy", "no-referrer")
        # Yêu cầu trình duyệt giữ đúng kiểu nội dung đã khai báo.
        self.send_header("X-Content-Type-Options", "nosniff")
        # Giới hạn nguồn nội dung trong chính tool, gồm script nội tuyến.
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                         # Cho giao diện tải kiểu dáng nội tuyến và ảnh dựng trong trình duyệt.
                         "style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; "
                         # Chặn nhúng tool vào khung và các loại nội dung thừa.
                         "base-uri 'none'; frame-ancestors 'none'; object-src 'none'")
        for key, value in extra.items():  # Thêm header riêng của yêu cầu, như cookie hoặc tên tệp.
            # Đổi dạng tên đối số Python thành tên header HTTP chuẩn.
            self.send_header(key.replace("_", "-"), value)
        self.end_headers()  # Kết thúc phần đầu để có thể gửi phần thân.

    def send_bytes(self, code, content_type, body, **extra):  # Gửi một phản hồi có sẵn nội dung dạng byte.
        # Tính độ dài từ chính nội dung và chuẩn bị header tương ứng.
        self.headers_for(code, content_type, len(body), **extra)
        self.wfile.write(body)  # Gửi phần thân vào kết nối của trình duyệt.

    def send_json(self, payload, code=HTTPStatus.OK):  # Gửi dữ liệu hoặc thông báo lỗi dưới dạng JSON.
        # Mã hóa UTF-8 để giữ nguyên các ký tự tiếng Việt.
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        # Thông báo kiểu JSON và encoding cho phía trình duyệt.
        self.send_bytes(code, "application/json; charset=utf-8", body)

    def key_matches(self, value):  # So sánh mã mà máy khách gửi với mã phiên hiện tại.
        # So sánh byte bằng hàm tránh lệch thời gian theo tiền tố khớp.
        return hmac.compare_digest(self.server.key.encode(), value.encode())

    def authorized(self):  # Quyết định yêu cầu có được truy cập vào dữ liệu phiên.
        if self.server.key is None:  # Chế độ chỉ dùng trên máy chạy sẽ không cấp mã truy cập.
            return True  # Cho phép kết nối loopback trong chế độ cá nhân.
        try:  # Đọc cookie, có thể gặp giá trị do máy khách gửi sai cú pháp.
            # Chỉ lấy cookie được đặt tên cho phiên này.
            cookie = SimpleCookie(self.headers.get("Cookie", "")).get(self.server.cookie_name)
        except CookieError:  # Xử lý cookie không đọc được như chưa đăng nhập.
            return False  # Từ chối truy cập khi cookie sai cú pháp.
        # Ở chế độ chia sẻ, chỉ cookie khớp mã phiên mới được dùng.
        return bool(cookie and self.key_matches(cookie.value))

    def route(self):  # Tách đường dẫn và tham số của yêu cầu HTTP.
        return urlsplit(self.path)  # Dùng bộ phân tích URL thay vì tách chuỗi thủ công.

    def do_GET(self):  # Xử lý phương thức GET để đọc giao diện, dữ liệu và ảnh.
        try:  # Bao bọc thao tác đọc để bắt lỗi theo loại.
            self.handle_get()  # Thực hiện điều hướng và phục vụ tài nguyên.
        # Trình duyệt có thể ngắt kết nối khi người dùng chuyển ảnh.
        except (BrokenPipeError, ConnectionResetError):
            pass  # Kết thúc yêu cầu đó, các kết nối khác vẫn hoạt động.
        # Xử lý lỗi phát sinh khi đọc lô, CSV hoặc metadata.
        except (OSError, ValueError, KeyError, TypeError) as error:
            # Đưa chi tiết vào terminal để người chạy có thể sửa.
            print(f"Lỗi đọc dữ liệu: {error}", file=sys.stderr)
            # Gửi thông báo dễ hiểu, giữ nội dung lỗi máy ở terminal.
            self.send_json({"error": "Không đọc được dữ liệu. Xem thông báo trên máy chạy."}, 500)

    def handle_get(self):  # Điều hướng GET theo đường dẫn và điều kiện truy cập.
        route = self.route()  # Tách đường dẫn khỏi chuỗi truy vấn.
        query = parse_qs(route.query)  # Giải các tham số truy vấn thành tên và danh sách giá trị.
        # Nhận mã phiên khi mở đúng liên kết gốc được chia sẻ.
        if self.server.key and route.path == "/" and self.key_matches(query.get("key", [""])[0]):
            # Tạo cookie cho trình duyệt, giữ mã ở phía HTTP và giới hạn cách gửi.
            cookie = f"{self.server.cookie_name}={self.server.key}; Path=/; HttpOnly; SameSite=Lax"
            # Lưu cookie và chuyển về địa chỉ gốc gọn hơn.
            self.send_bytes(303, "text/plain; charset=utf-8", b"", Location="/", Set_Cookie=cookie)
            return  # Dừng xử lý vì đã gửi chuyển hướng.
        if not self.authorized():  # Các yêu cầu khác cần qua kiểm tra quyền truy cập.
            # Báo dùng đúng đường dẫn nhóm trưởng đã chia sẻ.
            self.send_bytes(403, "text/plain; charset=utf-8", "Mở đường dẫn đầy đủ do nhóm trưởng gửi.".encode())
            return  # Dừng trước khi đọc dữ liệu lô cho người chưa có quyền.

        data = self.server.data  # Lấy dữ liệu phiên dùng chung từ đối tượng máy chủ.
        if route.path == "/":  # Trang gốc là giao diện review.
            # Trả HTML đã đọc lúc máy chủ khởi động.
            self.send_bytes(200, "text/html; charset=utf-8", self.server.page)
        elif route.path == "/api/items":  # Endpoint này trả hàng đợi và kết luận đã lưu.
            # Gói hàng đợi thành JSON để giao diện dựng danh sách.
            self.send_json({"items": data.list_items()})
        elif route.path == "/api/item":  # Endpoint này trả thông tin trực quan cho một mục.
            candidate_id = query.get("id", [""])[0]  # Lấy ID được chỉ định, rỗng nếu người gọi bỏ qua.
            # Chỉ tra cứu ID gồm tối đa chín chữ số.
            item = data.items.get(int(candidate_id)) if re.fullmatch(r"[0-9]{1,9}", candidate_id) else None
            if item:  # Ứng viên có thật mới có ảnh và hộp để trả.
                self.send_json(data.image_detail(item))  # Gửi URL ảnh, mask và dữ liệu hộp của ứng viên.
            else:  # Xử lý trường hợp ID sai hoặc không có.
                # Trả lỗi HTTP 404 để giao diện báo mục vắng mặt.
                self.send_json({"error": "Không tìm thấy ứng viên."}, 404)
        elif route.path == "/review_log.csv":  # Đường dẫn tải kết quả do giao diện cung cấp.
            # Trả nội dung CSV hiện hành ở dạng UTF-8.
            self.send_bytes(200, "text/csv; charset=utf-8", data.download_csv(),
                            # Gợi ý trình duyệt tải thành tệp review_log.csv.
                            Content_Disposition='attachment; filename="review_log.csv"')
        else:  # Các đường dẫn còn lại chỉ được phục vụ nếu là ảnh hoặc mask.
            # Kiểm tra định dạng URL tài nguyên do tool tạo.
            match = re.fullmatch(r"/asset/([0-9]{1,9})/(photo|mask)", route.path)
            # Chỉ cho tải ảnh hoặc mask thuộc ứng viên hiện có.
            item = data.items.get(int(match[1])) if match else None
            if item:  # Yêu cầu ứng viên hợp lệ trước khi tìm tệp.
                # Chọn khóa manifest và kiểu nội dung tương ứng.
                key, mime = ("image", "image/jpeg") if match[2] == "photo" else ("mask", "image/png")
                path = data.asset(item, key)  # Xác nhận tệp được phép đọc qua metadata của ảnh.
                if path:  # Nếu tệp còn tồn tại, mở và gửi nội dung.
                    with path.open("rb") as source:  # Đọc byte gốc của JPG hoặc PNG.
                        # Lấy kích thước chính xác từ tệp đang mở.
                        self.headers_for(200, mime, os.fstat(source.fileno()).st_size)
                        # Truyền từng phần thay vì nạp cả tệp vào bộ nhớ.
                        shutil.copyfileobj(source, self.wfile)
                    return  # Kết thúc vì ảnh hoặc mask đã được gửi xong.
            # Báo không tìm thấy khi đường dẫn hoặc tài nguyên không hợp lệ.
            self.send_json({"error": "Không tìm thấy dữ liệu."}, 404)

    def do_POST(self):  # Xử lý phương thức POST để lưu một kết quả review.
        if not self.authorized():  # Xác thực trước khi đọc hay ghi dữ liệu.
            # Báo hết quyền truy cập và hướng dẫn mở lại liên kết.
            self.send_json({"error": "Mở lại đường dẫn do nhóm trưởng gửi."}, 403)
            return  # Dừng khi chưa xác thực được phiên.
        if self.route().path != "/api/review":  # Chỉ chấp nhận thao tác ghi tại API review.
            # Báo endpoint không tồn tại nếu có URL khác.
            self.send_json({"error": "Không tìm thấy dữ liệu."}, 404)
            return  # Dừng ghi khi yêu cầu sai đường dẫn.
        # Kiểm tra kiểu dữ liệu mà client khai báo trước khi đọc.
        if self.headers.get_content_type() != "application/json":
            # Báo lỗi khi phần thân gửi lên chưa phải JSON.
            self.send_json({"error": "Dữ liệu gửi lên phải là JSON."}, 415)
            return  # Dừng trước khi đọc nội dung sai kiểu.
        length = self.headers.get("Content-Length", "")  # Lấy số byte do trình duyệt khai báo.
        # Kiểm tra độ dài dạng số và giới hạn nội dung của một lượt review.
        if not re.fullmatch(r"[0-9]{1,5}", length) or not 0 < int(length) <= 32768:
            # Từ chối dữ liệu rỗng, quá lớn hoặc khai báo sai.
            self.send_json({"error": "Kích thước dữ liệu review không hợp lệ."}, 413)
            return  # Dừng trước khi đọc phần thân có kích thước sai.
        try:  # Xử lý riêng lỗi dữ liệu đầu vào và lỗi ghi tệp.
            payload = json.loads(self.rfile.read(int(length)))  # Đọc đúng số byte khai báo rồi giải mã JSON.
            # Xác thực và cập nhật kết quả theo phiên bản trình duyệt gửi.
            review = self.server.data.save(payload)
        except ValueError as error:  # Nhận lỗi từ JSON hoặc các kiểm tra dữ liệu review.
            self.send_json({"error": str(error)}, 400)  # Trả chi tiết để người review sửa nội dung đã gửi.
        except OSError as error:  # Nhận lỗi hệ thống tệp, ví dụ khi Excel đang mở CSV.
            # In lỗi ghi cụ thể ở terminal của người vận hành.
            print(f"Lỗi lưu kết quả: {error}", file=sys.stderr)
            # Hướng dẫn xử lý nguyên nhân ghi CSV thường gặp.
            self.send_json({"error": "Không lưu được CSV. Nếu file đang mở trên máy chạy, hãy đóng file rồi thử lại."}, 500)
        else:  # Chỉ gửi kết quả ghi khi xử lý không ném lỗi.
            if review is None:  # Giá trị None báo xung đột phiên bản.
                # Thông báo làm mới để xem bản người khác vừa lưu.
                self.send_json({"error": "Bạn khác vừa cập nhật ứng viên này. Hãy làm mới để xem kết quả mới nhất."}, 409)
            else:  # Xử lý khi dữ liệu đã lưu hoặc trùng với dữ liệu hiện hành.
                self.send_json({"review": review})  # Trả bản mà giao diện dùng để cập nhật trạng thái.


def lan_addresses():  # Lấy các địa chỉ LAN để in liên kết gửi cho nhóm.
    try:  # Cho phép tiếp tục dù máy không tìm được địa chỉ.
        # Hỏi hệ điều hành về các địa chỉ IPv4 của máy.
        results = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:  # Xử lý trường hợp truy vấn tên máy thất bại.
        return []  # Không có địa chỉ tự động, người dùng có thể xem bằng ipconfig.
    # Loại loopback, bỏ trùng và sắp xếp các địa chỉ để in.
    return sorted({row[4][0] for row in results if not row[4][0].startswith("127.")})


def load(delivery):  # Đọc dữ liệu classes, panoptic và manifest phục vụ chế độ vẽ ảnh tĩnh bằng Pillow.
    classes = class_names(delivery / "classes.txt")  # Ánh xạ mã lớp YOLO sang tên lớp.
    pan = read_json(delivery / "panoptic.json")  # Đọc tệp chú thích panoptic của lô.
    anns = {Path(a["file_name"]).stem: a for a in pan["annotations"]}  # Tra annotation theo tên gốc của ảnh.
    cats = {c["id"]: c["name"] for c in pan["categories"]}  # Tra tên lớp panoptic theo category_id.
    manifest = read_json(delivery / "manifest.json")["items"]  # Tra đường dẫn ảnh, nhãn, mask theo ID ảnh.
    return classes, anns, cats, manifest  # Trả bộ bảng tra cho hàm render từng ứng viên.


def boxes_px(label_path, w, h, classes):  # Đổi các hộp YOLO chuẩn hóa (0..1) sang tọa độ pixel trên ảnh.
    out = []  # Danh sách cặp (tên_lớp, (x0, y0, x1, y1)) theo pixel.
    if not label_path.is_file():  # Nếu thiếu tệp nhãn thì trả danh sách rỗng.
        return out  # Không vẽ hộp nào nếu tệp nhãn vắng mặt.
    for line in label_path.read_text(encoding="utf-8-sig").splitlines():  # Duyệt từng dòng trong tệp nhãn YOLO.
        if line.strip():  # Bỏ qua các dòng trống.
            c, x, y, bw, bh = line.split()  # Tách mã lớp và tọa độ tâm, chiều rộng, chiều cao.
            x, y, bw, bh = map(float, (x, y, bw, bh))  # Chuyển các tọa độ sang số thực.
            # Quy đổi từ tâm chuẩn hóa sang góc trên-trái và dưới-phải theo pixel.
            out.append((classes.get(int(c), f"?{c}"), ((x - bw / 2) * w, (y - bh / 2) * h, (x + bw / 2) * w, (y + bh / 2) * h)))
    return out  # Trả danh sách hộp theo thứ tự dòng trong tệp nhãn.


def outline(mask_w, mask_h, pixels, seg_id):  # Tìm tập hợp các pixel nằm trên đường viền của segment_id.
    def sid(i):  # Giải mã ID segment từ 3 byte RGB tại pixel thứ i (R + G*256 + B*256^2).
        return pixels[3 * i] + (pixels[3 * i + 1] << 8) + (pixels[3 * i + 2] << 16)
    inside = {i for i in range(mask_w * mask_h) if sid(i) == seg_id}  # Tập chỉ số các pixel thuộc segment.
    edge = []  # Danh sách tọa độ (x, y) nằm ở biên segment.
    for i in inside:  # Kiểm tra từng pixel bên trong segment.
        x, y = i % mask_w, i // mask_w  # Đổi chỉ số phẳng sang tọa độ cột x, hàng y.
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):  # Xét 4 pixel lân cận trên-dưới-trái-phải.
            # Nếu lân cận ra ngoài ảnh hoặc không thuộc segment thì (x, y) là điểm viền.
            if not (0 <= nx < mask_w and 0 <= ny < mask_h) or ny * mask_w + nx not in inside:
                edge.append((x, y))  # Lưu điểm viền để vẽ màu vàng nổi bật.
                break  # Đã xác nhận là điểm viền thì chuyển sang pixel tiếp theo.
    return edge  # Trả danh sách điểm viền của segment nghi ngờ.


def draw(img, boxes, highlight, edge, scale=1.0, offset=(0, 0)):  # Vẽ hộp detection và viền segment lên ảnh Pillow.
    from PIL import ImageDraw  # Nạp ImageDraw khi dùng chế độ xuất ảnh tĩnh.
    d = ImageDraw.Draw(img)  # Tạo đối tượng vẽ trên khung ảnh đích.
    ox, oy = offset  # Độ dịch gốc tọa độ (dùng khi vẽ lên vùng ảnh đã cắt crop).
    for k, (name, (x0, y0, x1, y1)) in enumerate(boxes):  # Duyệt từng hộp detection theo chỉ số k.
        color = (255, 40, 40) if k in highlight else (40, 220, 40)  # Hộp nghi ngờ tô đỏ, hộp khác tô xanh lá.
        r = [(x0 - ox) * scale, (y0 - oy) * scale, (x1 - ox) * scale, (y1 - oy) * scale]  # Đổi sang tọa độ khung vẽ.
        d.rectangle(r, outline=color, width=3 if k in highlight else 1)  # Vẽ khung chữ nhật của hộp detection.
        d.text((r[0] + 2, r[1] + 1), f"{k}:{name}", fill=color)  # Ghi chỉ số hộp và tên lớp ở góc trên trái.
    for x, y in edge:  # Duyệt từng điểm trên đường viền segment panoptic.
        px, py = (x - ox) * scale, (y - oy) * scale  # Quy đổi điểm viền theo tỷ lệ phóng và độ dịch crop.
        d.rectangle([px, py, px + max(1, scale) - 1, py + max(1, scale) - 1], fill=(255, 230, 0))  # Vẽ điểm viền màu vàng.


def render(delivery, cand, classes, anns, cats, manifest, out_path):  # Xuất ảnh ghép 2 khung (toàn cảnh + phóng to vùng cắt).
    from PIL import Image, ImageDraw  # Dùng Pillow để mở, cắt, phóng to và ghép ảnh review.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))  # Thêm thư mục scripts để nạp pngutil.
    from pngutil import read_rgb  # Dùng hàm đọc mask PNG RGB của bài lab.

    item = manifest[cand["image"]]  # Lấy đường dẫn image, label, mask của ảnh ứng viên.
    image = Image.open(delivery / item["image"]).convert("RGB")  # Mở ảnh gốc ở chế độ màu RGB.
    w, h = image.size  # Lấy chiều rộng và chiều cao ảnh gốc.
    mw, mh, pixels = read_rgb(delivery / item["mask"])  # Đọc kích thước và mảng byte RGB của mask panoptic.
    boxes = boxes_px(delivery / item["label"], w, h, classes)  # Đọc danh sách hộp YOLO theo tọa độ pixel.
    # Tập các chỉ số hộp được ứng viên chỉ định để tô đỏ nổi bật.
    highlight = set(cand.get("box_indexes", [])) | ({cand["box_index"]} if "box_index" in cand else set())
    edge = outline(mw, mh, pixels, cand["segment_id"]) if "segment_id" in cand else []  # Tính viền segment nếu có segment_id.

    full = image.copy()  # Tạo bản sao ảnh gốc cho khung toàn cảnh bên trái.
    s_full = PANEL / max(w, h)  # Tính tỷ lệ thu/phóng để cạnh dài nhất vừa khung PANEL (640px).
    full = full.resize((int(w * s_full), int(h * s_full)))  # Đổi kích thước khung toàn cảnh.
    draw(full, boxes, highlight, edge, s_full)  # Vẽ toàn bộ hộp và viền segment lên khung bên trái.

    x0, y0, x1, y1 = cand.get("seg_bbox", [0, 0, w, h])  # Lấy hộp bao quanh segment nghi ngờ làm vùng cắt cơ sở.
    for k in highlight:  # Mở rộng vùng cắt để bao trọn cả các hộp detection đang đối chiếu.
        if 0 <= k < len(boxes):  # Kiểm tra chỉ số hộp hợp lệ.
            bx = boxes[k][1]  # Lấy tọa độ pixel của hộp detection.
            x0, y0, x1, y1 = min(x0, bx[0]), min(y0, bx[1]), max(x1, bx[2]), max(y1, bx[3])  # Hợp nhất vùng bao.
    pad = 0.15 * max(x1 - x0, y1 - y0) + 10  # Thêm lề 15% xung quanh vật để dễ quan sát ngữ cảnh.
    cx0, cy0 = max(0, int(x0 - pad)), max(0, int(y0 - pad))  # Giới hạn góc trên-trái vùng cắt trong phạm vi ảnh.
    cx1, cy1 = min(w, int(x1 + pad)), min(h, int(y1 + pad))  # Giới hạn góc dưới-phải vùng cắt trong phạm vi ảnh.
    crop = image.crop((cx0, cy0, cx1, cy1))  # Cắt vùng ảnh quanh đối tượng nghi ngờ.
    s_crop = PANEL / max(1, max(cx1 - cx0, cy1 - cy0))  # Tính tỷ lệ phóng to vùng cắt lên kích thước PANEL.
    crop = crop.resize((max(1, int((cx1 - cx0) * s_crop)), max(1, int((cy1 - cy0) * s_crop))))  # Phóng to vùng cắt.
    draw(crop, boxes, highlight, edge, s_crop, (cx0, cy0))  # Vẽ hộp và viền segment lên khung phóng to bên phải.

    # Tạo tấm ảnh nền tối ghép khung toàn cảnh (trái) và khung phóng to (phải) cùng thanh tiêu đề phía trên.
    sheet = Image.new("RGB", (full.width + crop.width + 10, max(full.height, crop.height) + 40), (30, 30, 30))
    sheet.paste(full, (0, 40))  # Dán khung toàn cảnh vào bên trái.
    sheet.paste(crop, (full.width + 10, 40))  # Dán khung cắt phóng to vào bên phải.
    title = f"{cand['image']}  {cand['type']}  seg={cand.get('seg_class', '?')}" + (
        f"  det={cand['det_class']}" if "det_class" in cand else ""
    )  # Tạo chuỗi tiêu đề tóm tắt ứng viên.
    ImageDraw.Draw(sheet).text((6, 6), title + "   |  " + cand.get("reason", ""), fill=(255, 255, 255))  # Ghi tiêu đề lên đầu ảnh.
    sheet.save(out_path)  # Lưu tệp PNG kết quả ra thư mục đích.


def main():  # Đọc tham số, hỗ trợ cả chế độ xuất ảnh PNG (--out) và chế độ mở web review chung (--share).
    parser = argparse.ArgumentParser(description=__doc__)  # Dùng mô tả đầu tệp làm tiêu đề trợ giúp CLI.
    # Nhận đường dẫn thư mục ảnh, nhãn, mask và metadata.
    parser.add_argument("delivery", type=Path, help="Thư mục delivery của đề.")
    # Hỗ trợ truyền candidates.json dạng đối số vị trí thứ hai (như trong tools/README.md) hoặc qua cờ --candidates.
    parser.add_argument("candidates_pos", nargs="?", type=Path, help="File candidates.json (tùy chọn nếu đã dùng --candidates).")
    parser.add_argument("--candidates", dest="candidates_opt", type=Path, help="File candidates.json do validator tạo.")
    # Nếu người dùng truyền --out <thư_mục>, chạy chế độ Pillow xuất ảnh PNG 2 khung (toàn cảnh + crop phóng to).
    parser.add_argument("--out", type=Path, help="Thư mục xuất ảnh PNG 2 khung (toàn cảnh + phóng to) bằng Pillow.")
    # Cho phép chỉ định đường dẫn CSV kết quả riêng khi chạy chế độ web server.
    parser.add_argument("--output", type=Path, help="CSV chung khi mở web review, mặc định cạnh file candidates.json.")
    # Lắng nghe ở cổng 8765 mặc định; có thể đổi khi trùng cổng.
    parser.add_argument("--port", type=int, default=8765)
    # Chỉ mở cho máy khác truy cập khi người dùng chọn chia sẻ.
    parser.add_argument("--share", action="store_true", help="Cho nhóm truy cập qua mạng nội bộ bằng link có mã.")
    args = parser.parse_args()  # Phân tích tham số; hỗ trợ xem cách dùng bằng --help.
    candidates_path = args.candidates_opt or args.candidates_pos  # Lấy đường dẫn candidates.json từ cờ hoặc đối số vị trí.
    if candidates_path is None:  # Báo lỗi rõ ràng nếu thiếu cả hai cách truyền candidates.json.
        parser.error("Cần truyền đường dẫn candidates.json (qua đối số vị trí hoặc --candidates).")
    if args.out is not None:  # Chế độ 1: Xuất hàng loạt ảnh PNG 2 khung (toàn cảnh + crop phóng to) vào thư mục --out.
        classes, anns, cats, manifest = load(args.delivery)  # Nạp bảng lớp, panoptic và manifest.
        cands = read_json(candidates_path).get("candidates", [])  # Đọc danh sách ứng viên từ tệp JSON.
        args.out.mkdir(parents=True, exist_ok=True)  # Tạo thư mục đầu ra nếu chưa tồn tại.
        for n, cand in enumerate(cands):  # Duyệt từng ứng viên theo thứ tự để xuất ảnh.
            path = args.out / f"{cand['image']}_{n}.png"  # Đặt tên tệp PNG theo mã ảnh và số thứ tự ứng viên.
            render(args.delivery, cand, classes, anns, cats, manifest, path)  # Vẽ và lưu ảnh PNG 2 khung.
            print(path)  # In đường dẫn ảnh vừa xuất ra màn hình.
        return 0  # Kết thúc chế độ xuất ảnh tĩnh thành công.
    try:  # Chế độ 2: Mở máy chủ web tương tác để cả nhóm cùng xem ảnh và lưu review_log.csv.
        # Mặc định đặt nhật ký cạnh candidates.json.
        output = args.output or candidates_path.with_name("review_log.csv")
        # Nạp và kiểm tra dữ liệu trước khi mở cổng.
        data = ReviewData(args.delivery, candidates_path, output)
        # Chia sẻ trên các giao diện mạng khi bật --share, mặc định chỉ máy này.
        host = "0.0.0.0" if args.share else "127.0.0.1"
        # Đóng socket đúng cách khi kết thúc khối chạy máy chủ.
        with ReviewServer((host, args.port), data, args.share) as server:
            data.initialize_csv()  # Tạo hoặc chuẩn hóa CSV trước khi nhận yêu cầu đầu tiên.
            # In số ứng viên và vị trí tệp kết quả để kiểm tra đúng lô.
            print(f"{len(data.items)} ứng viên | CSV chung: {data.output}", flush=True)
            # Chế độ chia sẻ cần mã trong liên kết mở phiên.
            suffix = f"/?key={server.key}" if args.share else "/"
            # In địa chỉ người chạy có thể mở ngay trong trình duyệt.
            print(f"Mở trên máy này: http://127.0.0.1:{server.server_port}{suffix}", flush=True)
            if args.share:  # Chỉ hiển thị liên kết LAN khi người dùng mở chia sẻ.
                addresses = lan_addresses()  # Tìm các địa chỉ IPv4 có thể truy cập từ máy cùng mạng.
                for address in addresses:  # In một liên kết cho mỗi địa chỉ tìm được.
                    # Giữ nguyên cổng và mã để máy khác truy cập đúng phiên.
                    print(f"Link gửi nhóm: http://{address}:{server.server_port}{suffix}", flush=True)
                if not addresses:  # Trường hợp không tự nhận diện được địa chỉ mạng.
                    # Chỉ cách xem IPv4 thủ công và lắp vào liên kết.
                    print("Chạy ipconfig, lấy IPv4 của Wi-Fi hoặc Ethernet để thay 127.0.0.1 trong link.", flush=True)
            # Cho biết cửa sổ nào phải giữ mở khi nhóm đang review.
            print("Giữ cửa sổ này mở trong lúc review. Ctrl+C để dừng.", flush=True)
            server.serve_forever()  # Bắt đầu phục vụ nhiều người cho tới khi người dùng dừng.
    except KeyboardInterrupt:  # Xử lý Ctrl+C như yêu cầu kết thúc chủ động.
        return 0  # Thoát thành công khi người dùng chủ động dừng.
    # Bắt lỗi tệp, dữ liệu JSON sai hoặc tham số ngoài giới hạn.
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
        # Hiện nguyên nhân ở terminal để người dùng dễ khắc phục.
        print(f"Không khởi động được: {error}", file=sys.stderr)
        return 1  # Trả mã lỗi cho shell khi chuẩn bị dữ liệu hoặc máy chủ thất bại.
    return 0  # Trả mã thành công khi phiên review kết thúc bình thường.


if __name__ == "__main__":  # Chỉ mở máy chủ khi tệp được chạy trực tiếp.
    raise SystemExit(main())  # Chuyển kết quả của main thành mã thoát của lệnh.
