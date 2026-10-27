# Update Tools

Update Tools kiểm tra bản stable theo tag `vMAJOR.MINOR.PATCH` của repository
MTB. Push code lên main không tự bật thông báo bản stable mới.

Giữ checkout được pyRevit nạp có `.git`, remote origin trỏ tới MTB, kết nối GitHub
và Git hoạt động trên máy. Khi có stable mới, dùng Update Tools rồi làm theo
hướng dẫn reload/restart của tool. Icon báo cập nhật dựa trên bản stable mới hơn.

Nếu có thay đổi local hoặc file chưa theo dõi, tool dừng để bảo vệ dữ liệu.
Kiểm tra `git status --short`, lưu/commit hoặc chuyển thay đổi sang nơi phát triển
rồi đồng bộ bằng Git. Tool không tự stash, reset, xóa hay ghi đè thay đổi local.
Không xóa `.git` và không copy source thủ công đè lên checkout đang dùng.

Người bảo trì chỉ tạo/push tag stable sau khi kiểm thử và duyệt một đợt thay đổi.
Không di chuyển tag đã phát hành. Tài liệu phát triển và source thử nghiệm được
quản lý riêng, không cần để chạy bản phân phối.
