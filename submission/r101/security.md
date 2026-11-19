# Bảo mật khi làm việc

Lô đang làm: `lab250_05ef0c66798d` (seed 101, 250 ảnh COCO val2017, có nhiều ảnh người thật), bản bàn giao `lab250_05ef0c66798d_v2`.

## 1. Ca USB: hết giờ, muốn chép lô về nhà làm tiếp

Không chép lô ra USB. Lô gồm ảnh, mask, metadata và danh sách người gán/kiểm (A01–A05, Q01–Q03): đó là dữ liệu của dự án và của khách hàng, rời khỏi máy công ty là mất kiểm soát (USB rơi, máy nhà nhiễm mã độc, không có nhật ký truy cập). Gửi qua email cá nhân hay nhờ đồng nghiệp chép hộ cũng sai y như vậy: dữ liệu vẫn ra ngoài hệ thống được phép, chỉ đổi đường đi, và người làm hộ còn dùng quyền không phải của họ. Cách đúng: dừng ở mốc đã commit, ghi lại tiến độ trong bảng phân công, mai làm tiếp trên máy công ty; nếu thật sự cần làm từ xa thì xin quyền truy cập từ xa (VPN, máy ảo của dự án) qua người phụ trách.

## 2. Năm việc: được hay không

- Mở job được giao trên máy công ty: **được**, đúng phạm vi công việc và để lại nhật ký truy cập.
- Chụp màn hình ảnh trong lô gửi người quen: **không**, ảnh có người thật (ví dụ 000000011699, 000000005001) và là dữ liệu chưa công bố của dự án.
- Chép lô ra USB: **không**, như mục 1.
- Dán nhãn thật hay ảnh của lô lên chatbot công cộng: **không**, dữ liệu bị gửi sang bên thứ ba và có thể bị lưu lại. Trong lab nhóm chỉ hỏi AI về cách viết code, không dán ảnh hay nhãn của lô (ghi trong prompts.md).
- Đưa tài khoản CVAT cho đồng nghiệp: **không**, mỗi người một tài khoản để truy vết ai gán và kiểm cái gì (chính rework_queue.csv dựa vào mã người gán/người kiểm). Đồng nghiệp cần quyền thì xin người phụ trách cấp.

## 3. Ca khuôn mặt: thấy mặt người rõ trong lô, guideline yêu cầu làm mờ

Ví dụ trong lô của nhóm: ảnh 000000011699 (hai mẹ con đứng ở sân ga, mặt nhìn thẳng ống kính, rất rõ), 000000005001 (đám đông dự lễ cắt băng, nhiều khuôn mặt rõ), 000000025057 (người đàn ông cởi trần cầm đĩa bay, thấy rõ mặt). Việc cần làm: **Hold** phần ảnh này (không bàn giao tiếp, không đưa vào train) và **báo người phụ trách dữ liệu / bảo mật** kèm danh sách ảnh, để họ quyết định quy trình làm mờ hoặc loại ảnh và cập nhật guideline. Người gán không tự làm mờ hay xoá ảnh: tự sửa ảnh làm sha256 trong manifest không còn khớp, phá truy vết giữa v1 và v2, có thể làm mờ sai hoặc sót mặt, và quyết định về dữ liệu cá nhân phải do người có trách nhiệm đưa ra và ghi lại. Trạng thái lô trong lúc chờ: Hold.
