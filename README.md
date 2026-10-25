# BIM Test — pyRevit Tools

BIM Test là bộ công cụ hỗ trợ thao tác trong Autodesk Revit, tổ chức thành một
extension pyRevit với các nhóm Filters, Geometry, 2DView, 3DView và Update.
Môi trường đích hiện tại là **Revit 2025 trên Windows**.

## Các nhóm công cụ

| Nhóm | Công cụ / mục đích |
|---|---|
| Filters | Color Filter: phân nhóm giá trị tham số, áp màu và tạo filter; Copy Filters: sao chép filter cùng thiết lập đồ họa sang view/template |
| Geometry | Join/Unjoin Geometry, SplitBeam, Allow/Disallow Join đầu dầm |
| 2DView | Chỉnh đầu Grid/Level, bật/tắt bubble, Quick Crop, Toggle Leader, căn tag và vẽ X cho Opening |
| 3DView | Định hướng Section Box theo mặt được chọn |
| Update | Nhận bản phát hành ổn định từ GitHub theo tag phiên bản |

Các script có mức độ hoàn thiện khác nhau. Bộ kiểm thử tự động không thay thế
kiểm tra thao tác, hình học và DPI trên phiên bản Revit thực tế.

## Yêu cầu

- Autodesk Revit 2025 và bản pyRevit tương thích, có engine IronPython.
- Git for Windows nếu muốn clone và dùng nút Update Tools.
- Quyền truy cập repository nếu repository được đặt ở chế độ private.
- Python 3 chỉ cần khi chạy bộ kiểm thử độc lập, không phải yêu cầu chạy nút Revit.

## Cài đặt để phát triển

Clone repository vào một thư mục có tên kết thúc bằng `.extension`, ví dụ trong
thư mục extensions mặc định của pyRevit:

```powershell
cd "$env:APPDATA\pyRevit\Extensions"
git clone https://github.com/duongtuong94/MTB.git MTB.extension
```

Nếu đường dẫn extensions trên chưa tồn tại hoặc pyRevit dùng vị trí khác, dùng
thư mục extensions đã cấu hình trong pyRevit. Giữ nguyên các thư mục bên trong
repository và chạy **Reload pyRevit** hoặc mở lại Revit để nạp tab BIM Test.

Để cài máy chỉ sử dụng bản ổn định, hãy clone theo **tag đã phát hành**, theo
hướng dẫn trong [UPDATING.md](UPDATING.md). Clone main có thể nhận code đang phát triển.
Không dùng bản ZIP nếu cần cập nhật bằng Git.

## Đồng bộ code và nhận bản phát hành

Hai luồng này được tách riêng:

- **Phát triển:** dùng Git pull/commit/push trên main giữa các máy.
- **Sử dụng:** bấm Update Tools để nhận tag ổn định dạng `vMAJOR.MINOR.PATCH`.

Push commit lên main không làm xuất hiện thông báo cập nhật. Tag ổn định mới
được kiểm tra khi nạp/reload pyRevit và mỗi 15 phút:

- `icon_hasupdates.png`: có bản phát hành chưa nằm trong lịch sử Git local.
- `icon.png`: đã có bản phát hành mới nhất hoặc chưa có bản phát hành.

Lỗi mạng giữ icon hiện tại, nên icon mặc định chưa phải xác nhận cập nhật khi
chưa kiểm tra thành công. Cập nhật áp dụng bằng fast-forward trên main; tool dừng
nếu cần ghi đè thay đổi hoặc hợp nhất lịch sử. Sau cập nhật, chạy Reload pyRevit.

Xem [UPDATING.md](UPDATING.md) cho quy trình phát hành, cài theo tag và chuyển từ
updater cũ. Bản mẫu `v1.1.0` trong tài liệu không khẳng định tag đó đã tồn tại.

## XLineOpeningShaft

Tool vẽ dấu X bằng Detail Lines riêng cho từng vòng kín của Shaft/Floor Opening.
Xem [hướng dẫn kiểm tra XLineOpeningShaft](tests/OPENING_MARKS.md).
Các thử nghiệm chỉnh sửa Symbolic Lines trong sketch không nằm trong bản public.

## Lưu ý hành vi hiện tại

- SplitBeam có thiết lập Join Cutback **1.0 feet** sau khi chia dầm. Cần kiểm tra
  lại yêu cầu mô hình trước khi áp dụng công cụ này.
- Tool Align Tag hiện xóa Detail Line tham chiếu sau khi căn tag.
- XLineOpeningShaft tạo Detail Lines theo từng vòng kín; chạy lại có thể tạo thêm
  đường. Đường bao lỗi hoặc lỗ có vùng đặc bên trong được báo bỏ qua.
- Giao diện đã có xử lý resize/vùng cuộn; DPI thật và chuyển màn hình vẫn cần
  xác minh. Xem [UI_LAYOUT.md](UI_LAYOUT.md) để biết phạm vi kiểm tra.

## Cấu trúc repository

```text
BIM Test.tab/      Ribbon và các command bundle pyRevit
lib/              Thư viện dùng chung cho UI, Git và hình học
lib/mtb/          Namespace cho tool mới: ui/, revit/, tools/
tests/            Kiểm thử độc lập và hướng dẫn kiểm tra Revit
extension.json    Metadata extension
UPDATING.md       Cài đặt, đồng bộ và phát hành theo tag
UI_LAYOUT.md      Quy tắc bố cục và phạm vi kiểm tra UI
```

`lib/` là source runtime cần phân phối cùng extension, không phải thư mục môi
trường ảo. Không sao chép riêng một script rồi bỏ qua các helper nó import.

Tool mới tách UI, logic thuần và Revit API theo nhu cầu trong `lib/mtb/`.
Các tool hiện có được giữ nguyên đường dẫn/import;
không tự động chuyển toàn bộ source sang MVVM.

## Kiểm thử

Tại thư mục repository, với Python 3 và Git đã cài:

```powershell
python -m unittest discover -s tests -v
```

Bộ test kiểm tra updater bằng repository Git tạm, phân tích đường bao và các
kiểm tra rollback bằng đối tượng giả lập. Không ghi
lên GitHub và không thay đổi mô hình Revit. Kiểm tra layout dùng IronPython/.NET
được mô tả riêng trong [UI_LAYOUT.md](UI_LAYOUT.md).

## Đóng góp và thông tin lỗi

Khi báo lỗi, ghi tên tool, phiên bản Revit/pyRevit, loại view, thao tác tái hiện và
thông báo lỗi. Với lỗi giao diện, bổ sung độ phân giải và Windows Scale. Chỉ chia
sẻ ảnh hoặc file mẫu đã loại thông tin dự án/khách hàng.

## Giấy phép và tài nguyên

Repository hiện chưa có file LICENSE. Không có giấy phép cụ thể nào được tuyên
bố trong README này. Nguồn và quyền phân phối code/icon bên thứ ba cần được xác
nhận trước khi công bố điều kiện sử dụng hoặc phát hành lại các tài nguyên đó.
