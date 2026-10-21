# Cập nhật BIM Test

Nút **BIM Test → Update → Update Tools** nhận code từ nhánh `main` của
`https://github.com/duongtuong94/MTB.git`.

## Cài lần đầu trên mỗi máy

- Cài Git for Windows; mở lại Revit nếu vừa cài Git.
- Dùng `git clone` để tải repository và cấu hình pyRevit nạp extension từ thư mục đó.
  Bản tải ZIP không có lịch sử Git nên không dùng được nút cập nhật.
- Nếu repository riêng tư, xác thực GitHub bằng Git trên máy trước.
- Chạy Reload pyRevit sau khi nhận phiên bản có nút Update Tools.

## Sử dụng

1. Bấm **Update Tools** và đợi kết quả.
2. Nếu có phiên bản mới, chạy **pyRevit → Reload** để nạp lại code và ribbon.

Nút dùng `icon.png` mặc định và `icon_hasupdates.png` khi GitHub có commit mới
chưa nằm trong lịch sử local. Kiểm tra nền sau khi nạp/reload pyRevit và mỗi 15 phút,
không tự tải hoặc áp dụng code. File local chưa commit không chặn kiểm tra icon.
Lỗi mạng/xác thực giữ nguyên icon hiện tại, không hiện popup. Do đó icon mặc định
trước lần kiểm tra thành công chưa phải là xác nhận đã ở phiên bản mới nhất.
Sau khi cập nhật thành công, nút trở về `icon.png`.

Tool chỉ nhận cập nhật bằng fast-forward. Không tự commit, push, stash, reset,
ghi đè thay đổi local hoặc giải quyết xung đột. Khi có file chưa commit hoặc commit
local chưa có trên GitHub, cần đồng bộ bằng Git trước. Trên máy phát triển,
tiếp tục dùng quy trình commit/pull/push thông thường.

Mỗi lệnh Git có thời gian chờ tối đa 60 giây. Nếu hết thời gian, kiểm tra kết nối
và `git status` trước khi thử lại. Nút không mở cửa sổ đăng nhập GitHub trong Revit.

Code mới chỉ được phân phối cho máy khác sau khi được commit và push lên `main`.

## Kiểm thử

Chạy `python -m unittest discover -s tests -v` với Python và Git đã cài.
Các kiểm thử dùng repository tạm trên máy, không ghi lên GitHub.
Phần cửa sổ pyRevit và gọi Git qua .NET cần kiểm thử trực tiếp trong Revit.
