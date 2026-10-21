# Phát hành và cập nhật BIM Test

Nút **BIM Test → Update → Update Tools** chỉ nhận bản phát hành theo tag ổn định
`vMAJOR.MINOR.PATCH` trong repository `duongtuong94/MTB`.
Push commit lên `main` để làm việc giữa máy nhà và công ty không báo cập nhật.

## Phát triển giữa các máy

Tiếp tục dùng Git trên nhánh main để pull/commit/push code trong lúc sửa.
Update Tools là kênh nhận bản phát hành, không thay thế Git cho việc phát triển.

## Phát hành sau một đợt fix

Sau khi kiểm tra code, commit và push thay đổi lên main. Chọn số phiên bản mới,
ví dụ dưới đây là **v1.1.0**:

```powershell
git switch main
git pull --rebase origin main
# Sửa code, kiểm thử và commit xong trước bước push
git push origin main
git tag -a v1.1.0 -m "Fix UI cho màn hình DPI cao"
git push origin v1.1.0
```

Push tag là thao tác phát hành. Không cần tạo GitHub Release trên website.
Không di chuyển/ghi đè tag đã phát hành; sửa tiếp thì tạo phiên bản cao hơn.
Tool so sánh phiên bản bằng số (v1.10.0 cao hơn v1.9.0), không dựa vào ngày tạo.
Tag thử nghiệm như `v1.2.0-beta.1`, `v1.2.0-rc.1` hoặc tên tùy ý bị bỏ qua.

## Chuyển các máy đã cài updater cũ sang cơ chế mới

Cần nhận code updater mới **một lần** bằng Git trong đúng thư mục extension
Revit đang nạp, sau khi code này đã được commit/push:

```powershell
cd "$env:APPDATA\pyRevit\Extensions\MTB.extension"
git status
git pull --ff-only origin main
```

Nếu có thay đổi local, lưu và đồng bộ chúng bằng Git trước. Sau đó Reload pyRevit.
Từ lần này, icon và nút chỉ theo dõi tag phát hành. Khi chưa có tag ổn định,
icon mặc định được giữ và nút báo “Chưa có bản phát hành”, không tải code main.

## Cài mới máy sử dụng tool

Cài Git for Windows, xác thực GitHub nếu repo riêng tư, rồi clone đúng tag đã
phát hành. Ví dụ **chỉ sau khi v1.1.0 đã được push**:

```powershell
git clone --branch v1.1.0 https://github.com/duongtuong94/MTB.git MTB.extension
cd MTB.extension
git switch -c main
```

Clone theo tag tạo detached HEAD; lệnh thứ hai tạo nhánh main để Update Tools
có thể fast-forward tới các bản phát hành sau. Đặt thư mục extension trong đường
dẫn pyRevit sử dụng rồi Reload. Không dùng bản ZIP (không có lịch sử Git).
Không dùng shallow clone. Máy phát triển có thể clone main bình thường.

## Icon và cập nhật

- `icon_hasupdates.png`: tag ổn định mới nhất trỏ tới commit chưa nằm trong lịch sử local.
- `icon.png`: đã có commit phát hành mới nhất, hoặc chưa có bản phát hành.
- Kiểm tra nền khi nạp/reload pyRevit và mỗi 15 phút; không tự áp dụng code.
- Lỗi mạng/xác thực giữ nguyên icon, không hiện popup. Icon trước lần kiểm tra
  thành công chưa phải xác nhận đã cập nhật.
- Bấm Update Tools để tải đúng tag rồi fast-forward nhánh main đến commit đó.
  Các commit main phía sau tag không được nhận qua nút.
- Sau khi cập nhật, chạy **pyRevit → Reload**. Icon trở về bình thường.
- Nếu máy phát triển đã đi xa hơn bản phát hành, không báo cập nhật và không
  hạ phiên bản. Nếu lịch sử phân nhánh, nút dừng để bạn xử lý bằng Git.

Tool không tự commit, push, stash, reset hay ghi đè thay đổi local.
Kiểm tra icon vẫn hoạt động khi có file chưa commit; áp dụng bản mới yêu cầu
working tree sạch. Mỗi lệnh Git có thời gian chờ tối đa 60 giây.
Nút không mở cửa sổ đăng nhập GitHub trong Revit.

## Kiểm thử

Chạy `python -m unittest discover -s tests -v` với Python và Git đã cài.
Các kiểm thử dùng repository tạm trên máy, không ghi lên GitHub.
Phần cửa sổ pyRevit và gọi Git qua .NET cần kiểm thử trực tiếp trong Revit.
