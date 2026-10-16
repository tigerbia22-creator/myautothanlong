# Thần Long Auto — LDPlayer

Bản công cụ điều khiển **LDPlayer trên Windows** qua ADB, với hai hồ sơ **Trừng ác** và **Tàng bảo đồ**. Có ghi thao tác, nhận diện nút bằng ảnh, lặp hữu hạn, chạy thử không bấm và nút dừng.

**Trạng thái 0.2.0:** đã phân tích clip mới dài 203 giây và thêm **luồng Trừng ác có xác nhận**, gồm 18 bước, 11 loại ảnh cần gán trên chính LDPlayer và 4 lần chờ người dùng kiểm tra trạng thái. Chưa có luồng Tàng bảo đồ từ clip. Chưa thử trực tiếp với game hoặc LDPlayer thật trong môi trường phát triển. Hồ sơ khởi đầu để trống; dùng nút nạp luồng theo clip nếu muốn thiết lập. Đây là mã nguồn chạy bằng Python, chưa phải tệp `.exe` hay APK.

Hướng dẫn từng bước và những hành vi quan sát trong clip: [Trừng ác theo clip](docs/TRUNG_AC_THEO_CLIP.md). Bản này dùng ảnh mẫu OpenCV; chưa tự đọc tên mục tiêu hoặc hiểu nhiệm vụ bằng AI.

## Chạy trên Windows

1. Cài **Python 3.12 64-bit** từ [python.org](https://www.python.org/downloads/). Chọn cài Python Launcher (`py`).
2. Giải nén toàn bộ phần mềm vào một thư mục có quyền ghi.
3. Mở LDPlayer, bật **ADB debugging** trong phần cài đặt nâng cao của giả lập (tên mục tùy phiên bản), khởi động lại nếu được yêu cầu. Giữ cố định độ phân giải và DPI trong suốt quá trình ghi/chạy.
4. Chạy **`CHAY_TREN_WINDOWS.bat`**. Lần đầu cần mạng để cài thư viện; những lần sau pip tái sử dụng thư viện đã cài. Giữ cửa sổ lệnh mở khi dùng phần mềm.
5. Trong giao diện, chọn đường dẫn **`adb.exe` đi kèm bản LDPlayer đang dùng**, ví dụ `C:\LDPlayer\LDPlayer9\adb.exe`. Đường dẫn có dấu cách được hỗ trợ. Nhấn làm mới thiết bị, chọn đúng phiên có trạng thái `device`. Nếu cần, kết nối địa chỉ ADB mà phiên LDPlayer cung cấp; `127.0.0.1:5555` là giá trị ban đầu, không bảo đảm đúng với mọi phiên. Không quét cổng tự động.
6. Chụp màn hình. Kiểm tra đúng nhân vật và phiên LDPlayer trước khi ghi hoặc bấm chạy.

### Khắc phục kết nối

- **Failed to fetch / Không liên lạc được với máy chủ:** mở lại `CHAY_TREN_WINDOWS.bat`, giữ cửa sổ lệnh mở, rồi Ctrl+F5 trên trình duyệt. Giao diện đã tải có thể còn hiển thị tên thiết bị cũ dù máy chủ đã dừng.
- **10061 / connection refused ở 127.0.0.1:5555:** địa chỉ đó chưa có ADB tiếp nhận. Bấm **Làm mới thiết bị** trước để dùng thiết bị ADB đã có. Nếu chưa có, bật **ADB local / Open local connection** trong cài đặt LDPlayer, lưu và khởi động lại giả lập. Không mặc định mọi phiên dùng cùng cổng.
- Nếu vẫn lỗi, chạy **`KIEM_TRA_KET_NOI.bat`**, gửi tệp **`THONG_TIN_KET_NOI.txt`** vừa tạo. Tệp chỉ chứa phiên bản Python, kết quả HTTP nội bộ và danh sách ADB; không chụp màn hình hoặc thu thập hồ sơ game.

Nếu có nhiều giả lập hoặc cùng một giả lập xuất hiện dưới nhiều serial, phải chọn một serial cụ thể. Thiết bị `offline`/`unauthorized` chưa thể điều khiển. Dùng adb của cùng bản LDPlayer để tránh xung đột phiên bản ADB. Phần mềm không tự khởi động, đóng hoặc chỉnh cấu hình LDPlayer.

## Thiết lập hai nhiệm vụ

Với từng hồ sơ, đưa game về một màn hình bắt đầu có thể lặp lại và chụp ảnh:

Riêng Trừng ác có thể chọn **Nạp luồng Trừng ác từ clip** và gán ảnh vào các bước đã soạn, theo [hướng dẫn này](docs/TRUNG_AC_THEO_CLIP.md). Luồng đó có bốn lần xác nhận, chỉ chạy một vòng; chưa tự xác định đã tới tọa độ, hạ đúng mục tiêu hoặc điểm phù đã lưu.

- **Ghi thao tác:** bật ghi, bấm trên ảnh để gửi lệnh bấm thật và thêm bước tọa độ. Chụp lại sau khi giao diện game thay đổi. Có thể thêm bước chờ, vuốt hoặc phím Back/Enter từ trình biên tập.
- **Nhận diện ảnh:** kéo chọn một vùng nút/biểu tượng đủ đặc trưng trên ảnh, tạo bước **Chạm mẫu ảnh** hoặc **Chờ mẫu ảnh**. Không chọn vùng trơn, hoạt ảnh, con số thay đổi hoặc cả màn hình. Bước bấm ảnh tìm vị trí phù hợp rồi bấm tâm ảnh; ngưỡng mặc định 0,90. Có thể giới hạn vùng tìm bằng trường `region: [x, y, width, height]` trong tệp JSON xuất ra, rồi nhập lại.
- **Hoàn chỉnh một vòng:** thêm các trạng thái mở nhiệm vụ, chờ di chuyển/chiến đấu, nhận kết quả, rồi quay về màn hình bắt đầu. Đặt tên bước theo hành vi thực tế quan sát được. Tàng bảo đồ chỉ nên lặp khi đã xác minh cách xử lý thiếu bản đồ; Trừng ác chỉ nên lặp khi đã xác minh các màn hình kết thúc/nhận nhiệm vụ tiếp. Phần mềm chưa tự suy ra những trạng thái này.
- **Lưu hồ sơ**, chọn số vòng hữu hạn, chạy thử trước. Chạy thử đọc màn hình và nhận diện ảnh nhưng **không gửi bấm/vuốt/phím**, vì thế không tự làm game chuyển sang trạng thái tiếp theo. Để thử toàn luồng, tự thao tác trong giả lập khi bước chờ ảnh yêu cầu. Chạy thử không chứng minh hoàn thành nhiệm vụ trong game.
- Sau khi kiểm tra từng bước, chạy auto một vòng và quan sát. Chỉ tăng số vòng khi chu trình thực sự trở về điểm bắt đầu.

Bước tọa độ dễ sai khi bố cục thay đổi; nên thay các bước quan trọng bằng bấm/chờ ảnh. Chụp lại chỉ cập nhật ảnh xem; không tự chuyển đổi tọa độ và ảnh mẫu đã ghi sang độ phân giải mới. Nếu đổi độ phân giải, cần kiểm tra hoặc ghi lại toàn bộ hồ sơ.

Nhấn **Dừng** để ngừng chu trình. Lệnh ADB đã gửi có thể cần hoàn tất trước khi nút dừng trả về: thông thường tối đa 15 giây; với lệnh vuốt dài, giới hạn là thời lượng vuốt cộng 5 giây. Lệnh vuốt đã gửi có thể vẫn đang chạy trong Android. Không có lệnh bấm mới sau khi yêu cầu dừng hoàn tất. `Ctrl+C` trong cửa sổ lệnh dừng máy chủ và yêu cầu dừng auto. Mất kết nối, sai kích thước màn hình hoặc hết thời gian tìm ảnh đều dừng luồng và ghi lỗi; không tự bấm bỏ qua.

## Lưu và chuyển cấu hình

Thiết lập thiết bị, hồ sơ và ảnh mẫu nằm trong **`.local/`**, không đưa vào Git. Không nhập tài khoản hoặc mật khẩu game vào phần mềm. Xuất hồ sơ tạo JSON chứa cả ảnh mẫu, để nhập lại trên máy khác; ảnh mẫu có thể chứa nội dung màn hình game nên hãy kiểm tra trước khi chia sẻ. Hồ sơ nhập vào thay thế hồ sơ cùng loại; xuất bản cũ trước nếu muốn giữ.

Giới hạn để hồ sơ có thể nhập lại: mỗi ảnh mẫu PNG tối đa 4 MiB và 16 megapixel, tổng ảnh mỗi hồ sơ tối đa 10 MiB, dữ liệu JSON gửi lên tối đa 16 MiB. Nên cắt riêng nút/biểu tượng cần nhận diện.

Máy chủ chỉ lắng nghe trên loopback của máy chạy. Đóng cửa sổ trình duyệt không dừng auto; dùng nút Dừng hoặc `Ctrl+C`. Các tác vụ trừng ác/tàng bảo chạy đúng hay không còn phụ thuộc hồ sơ và giao diện phiên bản game thực tế.

## Phát triển và kiểm thử

```sh
python3 -m venv .venv
# Linux/macOS
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m thanlong
```

Trên Windows dùng `.venv\Scripts\python.exe` thay cho `.venv/bin/python`. Có thể truyền `--adb "đường dẫn adb"`, `--port 8765`, `--data-dir "thư mục dữ liệu"`, `--open`. Cổng mặc định là 8765. Không cần Node.js, quyền root Android hoặc dịch vụ ngoài cho bảng điều khiển.

Các kiểm thử dùng thiết bị/ảnh mô phỏng để kiểm tra lệnh ADB, tìm ảnh, giới hạn đầu vào, dừng, xác nhận từng điểm chờ, vòng lặp, lưu/nhập/xuất và HTTP. Chúng không thay thế việc chạy thử trên LDPlayer thật. Muốn tiếp tục phần Tàng bảo đồ hoặc xác minh những trạng thái khác, cần clip dưới 32 MiB thể hiện thao tác tương ứng.

Đóng gói mã nguồn cho Windows bằng `python scripts/package.py`. ZIP gồm mã nguồn, tệp khởi động và hướng dẫn; không chứa Python, LDPlayer, thư viện đã cài hoặc dữ liệu `.local/`.
