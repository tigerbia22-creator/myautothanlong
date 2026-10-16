# Trừng Ác tự động bằng OCR AI — 0.3.0 thử nghiệm

Chế độ này dùng **mô hình nhận diện chữ RapidOCR 3.10, các trọng số ONNX đi kèm và ONNX Runtime CPU**. Ảnh được xử lý trên máy tính của bạn. Không cần khóa API và không gửi ảnh đến dịch vụ AI. Đây là chế độ riêng với luồng bán tự động có bốn điểm xác nhận của 0.2.0.

## Cài và chuẩn bị một lần

1. Đóng cửa sổ máy chủ của bản cũ. Giải nén bản mới vào thư mục có quyền ghi.
2. Cài Python 3.12 64-bit nếu chưa có. Mở **`CHAY_TREN_WINDOWS_AI.bat`**. Lần đầu tải thư viện và mô hình qua pip, cần kết nối mạng. Các mô hình nằm trong gói RapidOCR; không phải tự tải trọng số hoặc cung cấp tài khoản game.
3. Giữ cửa sổ lệnh mở. Bật ADB local trong LDPlayer, chọn thiết bị và **Chụp màn hình**. Giữ nguyên độ phân giải trong khi chạy.
4. Chuẩn bị **Trừng Ác Lệnh** và **Bạch sắc định vị phù** trong hai ô vật phẩm nhanh. Phù phải đã lưu gần Ngô Giới ở Tô Châu và còn dùng được. Trong clip, hộp phù không hiển thị điểm đã lưu; phần mềm không thể suy ra điểm đó từ nội dung hộp.
5. Trong panel **Trừng ác · nhận diện OCR AI**, bấm **Chọn trên ảnh** cho từng ô, rồi bấm vào đúng ô vật phẩm trên ảnh chụp. Hai thao tác chọn điểm chỉ lưu vị trí; không gửi bấm vào game. Đây là hai vị trí cần thiết lập ban đầu, không cần gán 11 mẫu chữ như chế độ cũ.
6. Có thể chọn thêm điểm hội thoại Ngô Giới và tâm nút AUTO nếu chữ ở các vị trí này khó đọc. Phần mềm vẫn phải đọc được đúng hộp thoại/trạng thái trước khi tiến hành.
7. Tích xác nhận đã chuẩn bị phù đúng điểm và cho phép sử dụng. Chọn số vòng **1–30**; nên kiểm tra một vòng đầu tiên.
8. Mở hội thoại Ngô Giới hoặc đứng đủ gần để hiện nút hội thoại. Bấm **Kiểm tra OCR** để nạp mô hình và xem chữ nhận diện từ ảnh thật. Nếu tên/nút không đọc rõ, tăng độ rõ màn hình trước khi chạy.
9. **Lưu cấu hình OCR → Chạy Trừng ác tự động**. Giữ cửa sổ lệnh mở. Dùng nút Dừng khi cần.

## Cách tự động điều khiển

Trong lúc chạy không có bốn câu hỏi xác nhận thủ công:

- Tìm đúng Ngô Giới, chọn Nhận nhiệm vụ và đọc tên kẻ truy nã, bản đồ, tọa độ từ lời nhận nhiệm vụ.
- Mở đúng Trừng Ác Lệnh và kiểm tra tọa độ khớp nhiệm vụ đã nhận. Chọn Đến địa điểm. Sau mỗi khoảng chờ, mở lại lệnh để kiểm tra trạng thái; chỉ bấm Triệu hồi khi game đã đổi nút sang Triệu hồi.
- Kiểm tra trạng thái AUTO/Đánh quái, bật auto trong game nếu đang tắt, rồi đọc thông báo đã hạ đúng tên mục tiêu. Kinh nghiệm, rơi vật phẩm, mất mục tiêu hoặc giết quái khác đều không được tính là hoàn thành.
- Tắt auto đánh quái, mở đúng định vị phù và dùng Di chuyển theo chuẩn bị ban đầu. Chờ đọc được Ngô Giới; không dựa riêng vào một khoảng ngủ để bấm Trả nhiệm vụ.
- Chọn Trả nhiệm vụ, kiểm tra chữ Hoàn thành, chọn Ta biết rồi. Nếu còn vòng tiếp theo thì mở lại NPC và đọc nhiệm vụ mới.

Phần mềm dựa vào chữ và trạng thái của giao diện; không tự học tất cả cơ chế game từ video. Các khung tìm chữ dựa trên bố cục quan sát trong clip. Tên mục tiêu được đối chiếu sau khi bỏ dấu và chuẩn hóa khoảng trắng; mô hình vẫn có thể đọc sai, nhất là chữ nhỏ, chữ vàng và khi có thông báo chồng lên nhau.

## Dừng và lỗi

Mỗi giai đoạn có giới hạn thời gian: hộp thoại mặc định 30 giây, đi đường 15 phút, chiến đấu 3 phút, trở về NPC 90 giây. Không đọc rõ, đổi độ phân giải, không đúng tọa độ lệnh hoặc chưa thấy thông báo hạ đúng mục tiêu sẽ dừng luồng, ghi lỗi và không bấm sang bước tiếp.

**Dừng phần mềm ngăn các lệnh mới; AUTO đã bật bên trong game có thể vẫn đang chạy.** Kiểm tra và tắt AUTO trong game nếu bạn dừng giữa trận. Lệnh ADB đã gửi có thể cần hoàn tất. Mất kết nối máy chủ Python: mở lại đúng tệp `.bat` và tải lại trang.

Thiết lập OCR lưu riêng ở `.local/ai_config.json`, gắn với thiết bị và độ phân giải đã chụp. Đổi thiết bị/kích thước sẽ yêu cầu chọn lại vị trí. Dữ liệu `.local/` không được đưa lên GitHub.

## Bằng chứng kiểm thử và giới hạn

Đã chạy **mô hình OCR thật** trên khung hình của clip 203 giây: đọc các nút nhận/trả, đi tới nơi, triệu hồi, dịch chuyển; trích mục tiêu và tọa độ `(280,164)`; đối chiếu tên đó với thông báo hạ mục tiêu. Một số chữ bị nhận sai dấu hoặc thiếu ký tự; bộ kiểm tra dùng ngữ cảnh hộp thoại, vùng nút và điều kiện rõ ràng, không xem mọi chuỗi OCR là lệnh.

Đối chiếu 16 điều kiện trên các ảnh được chọn từ clip đều đạt với mô hình thực, gồm hộp thoại, chữ nút, tọa độ, thông báo hạ mục tiêu và trạng thái auto. Đây là kiểm tra các khung hình riêng lẻ, không phải bằng chứng một vòng điều khiển đã thành công trên game thật. Bộ thư viện đã được phân giải và tải đủ wheel cho Windows 64-bit/Python 3.12; chưa chạy Windows trong môi trường phát triển.

Các kiểm thử tự động dùng giao diện và ADB mô phỏng xác minh luồng một vòng, từ chối quái khác, dừng, sai kích thước, lưu cấu hình và đọc OCR. Chưa xác minh hoàn thành một vòng trên LDPlayer thật từ môi trường phát triển. Video ghi lại một vòng thông thường; chưa đủ để xác nhận mọi tình huống hết lượt, hết vật phẩm, nhân vật chết, popup lạ hoặc phiên bản game đổi bố cục. Khi gặp tình huống chưa đọc được, chế độ thử nghiệm sẽ báo lỗi để kiểm tra tiếp.

Phạm vi bản này là **Trừng Ác** theo yêu cầu hiện tại. Hoạt động Tàng bảo đồ là hoạt động riêng và không nằm trong luồng OCR này.
