# Trừng ác theo clip — bản có xác nhận

Đã đọc clip mới dài **203,32 giây**, khung **854×480**. Phần game nằm gần **854×450**, dưới cùng có dải đen. Clip cho thấy một vòng Trừng ác; chưa cho thấy sử dụng Tàng bảo đồ. Bản này ghi lại trình tự và thực hiện các bước bấm đã được gán ảnh trên LDPlayer, với bốn điểm chờ người dùng kiểm tra trạng thái game.

## Trình tự quan sát được

| Thời gian gần đúng | Hành vi trong clip |
| --- | --- |
| 7–10 giây | Mở Ngô Giới → Nhận nhiệm vụ → Ta biết rồi. |
| 11–13 giây | Mở Trừng Ác Lệnh từ ô nhanh → Đến địa điểm. |
| 14–166 giây | Nhân vật tự đi tới khu vực truy nã ở Nam Hải. |
| 167 giây | Mở Trừng Ác Lệnh → Triệu hồi. |
| 168–176 giây | Chiến đấu; xuất hiện thông báo đã giết mục tiêu. |
| 176–180 giây | Auto trong game còn đánh quái khác rồi được tắt. |
| 185–190 giây | Mở Bạch sắc định vị phù → Di chuyển → truyền tống về Tô Châu. |
| 197–203 giây | Mở Ngô Giới → Trả nhiệm vụ → Ta biết rồi. |

Tên và tọa độ truy nã thay đổi theo nhiệm vụ. Phần mềm chưa đọc tên mục tiêu hoặc xác minh việc hạ đúng mục tiêu bằng OCR. Cột nhiệm vụ trái vẫn ghi “Hiện tại không có nhiệm vụ nào” trong clip, nên không dùng cột đó để kết luận đã hoàn thành. Ô vật phẩm nhanh trong clip là ví dụ của nhân vật đó; cần gán đúng ảnh vật phẩm trên máy bạn.

## Chuẩn bị và gán ảnh

1. Kết nối ADB, chọn đúng thiết bị và **Chụp màn hình** thành công. Giữ cửa sổ lệnh Python mở.
2. Chọn **Trừng ác**, bấm **Nạp luồng Trừng ác từ clip**. Thao tác này thay thế hồ sơ Trừng ác sau khi bạn xác nhận; hãy xuất hồ sơ cũ trước nếu cần giữ. Hồ sơ Tàng bảo đồ được giữ nguyên.
3. Kịch bản có **18 bước**, gồm **14 bước ảnh** dùng **11 loại ảnh mẫu** và **4 bước xác nhận**. Ban đầu các ảnh để trống, nên chưa thể bấm Chạy. Nhận diện phải dùng ảnh của chính giả lập, không lấy tọa độ của video nén làm tọa độ ADB.
4. Tự mở lần lượt các hộp thoại/vật phẩm cần thiết trong game. Với từng loại ảnh, chụp màn hình, kéo chọn vùng chứa chữ nút hoặc biểu tượng, rồi bấm **Gán mẫu ảnh đã chọn** ở bước tương ứng. Các bước dùng cùng `calibration_key` nhận cùng một mẫu.
5. Gán đủ các ảnh: **Ngô Giới; Nhận nhiệm vụ; Ta biết rồi; ô Trừng Ác Lệnh; tiêu đề Trừng Ác Lệnh; Đến địa điểm; Triệu hồi; ô Bạch sắc định vị phù; tiêu đề Bạch sắc định vị phù; Di chuyển; Trả nhiệm vụ**.
6. Chọn vùng chữ đặc trưng của nút, không chọn cả khung vàng giống nhau giữa các lựa chọn. Giữ nguyên độ phân giải và DPI sau khi gán ảnh. Lưu hồ sơ.

Việc chuẩn bị ảnh có thể cần bạn tự thực hiện một vòng nhiệm vụ để chụp đủ các trạng thái. **Chạy thử** không gửi thao tác cho game; bạn tự chuyển màn hình khi muốn thử các bước kế tiếp. Lần chạy trên giả lập đầu tiên cần được quan sát.

## Bốn lần xác nhận

1. **Đã đến nơi:** chờ nhân vật đi xong, tự mở Trừng Ác Lệnh, kiểm tra có nút Triệu hồi rồi xác nhận. Bấm xác nhận cho phép phần mềm kiểm tra hộp thoại và bấm Triệu hồi.
2. **Đã hạ đúng mục tiêu:** theo dõi thông báo giết đúng kẻ truy nã và tự tắt auto đánh quái. Xác nhận cho phép mở vật phẩm định vị. Việc mất mục tiêu trên màn hình chưa đủ chứng minh đã xong.
3. **Đúng điểm dịch chuyển:** tự kiểm tra Bạch sắc định vị phù đã lưu gần Ngô Giới ở Tô Châu. Xác nhận cho phép bấm Di chuyển và dùng phù. Nếu sai điểm hoặc thiếu vật phẩm, dùng Dừng.
4. **Đã trở về NPC:** chờ chuyển bản đồ xong, tự mở hội thoại Ngô Giới rồi xác nhận. Phần mềm kiểm tra tiêu đề, bấm Trả nhiệm vụ và Ta biết rồi.

Mỗi điểm chờ có giới hạn 15 phút. Nút Dừng hủy chờ; không xác nhận hộ các bước chưa kiểm tra. Kịch bản mặc định chỉ cho **một vòng**, vì clip chưa chứng minh được vòng nhận nhiệm vụ kế tiếp hoặc cách xử lý hết lượt, thiếu lệnh, hết phù và mục tiêu khác. Muốn chạy vòng tiếp theo, kiểm tra kết quả và đưa game về hộp thoại Ngô Giới rồi bắt đầu lại.

## Tàng bảo đồ

Clip có thông báo nhận một bản đồ sau khi hạ mục tiêu và chat thế giới nhắc tới tàng bảo. Chưa có hình ảnh mở, sử dụng, tìm vị trí hoặc nhận thưởng từ bản đồ. Vì vậy chưa có kịch bản Tàng bảo đồ dựng từ clip này; cần đoạn thể hiện thao tác đó.
