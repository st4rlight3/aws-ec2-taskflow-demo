# TaskFlow và Amazon EC2

Sản phẩm demo cho học phần điện toán đám mây. Dịch vụ trọng tâm: **Amazon EC2**. Không sử dụng Amazon S3 trong ứng dụng hoặc quy trình triển khai.

## 1. Hiểu dịch vụ trước khi demo

EC2 cung cấp máy chủ ảo trên hạ tầng AWS. Bạn chọn AMI (ảnh hệ điều hành), cấu hình máy, ổ đĩa và mạng rồi cài ứng dụng. EC2 chạy chương trình; EBS là ổ đĩa lưu dữ liệu; Security Group quy định kết nối nào được phép đi vào máy.

Ưu điểm: linh hoạt cấu hình, chủ động cài đặt phần mềm, dễ minh họa cách vận hành máy chủ. Hạn chế: phải quản trị hệ điều hành và bảo mật, theo dõi chi phí; một máy chủ duy nhất không bảo đảm tính sẵn sàng cao. Dừng máy không đồng nghĩa mọi khoản phí đều chấm dứt.

Đọc phần lý thuyết trong báo cáo Word trước khi trình diễn. Các nguồn AWS chính thức được dẫn ở cuối báo cáo.

## 2. Chạy sản phẩm trên Windows

1. Giải nén toàn bộ gói ZIP; không chạy trực tiếp trong cửa sổ xem ZIP.
2. Mở thư mục `ec2-demo`, nhấp đúp `START_DEMO.cmd`.
3. Trình duyệt mở `http://127.0.0.1:8080/`.
4. Xem phần giới thiệu EC2 rồi nhập mã **demo2026** để vào ứng dụng.
5. Giữ cửa sổ chạy ứng dụng mở. Nhấn Ctrl+C trong cửa sổ đó để dừng.

Cần Python 3.10 trở lên. Không cần pip, npm, Docker hoặc khóa AWS để chạy cục bộ. Trên máy có Codex, trình khởi động ưu tiên Python đi kèm Codex; máy khác dùng Python đã cài.

Cách chạy bằng dòng lệnh trên Windows:

```powershell
py -3 app.py --open-browser
```

Trên macOS hoặc Linux:

```bash
python3 app.py --open-browser
```

Nếu cổng 8080 đang được dùng, chạy `python app.py --port 8081 --open-browser`. Cơ sở dữ liệu được tạo ở `data/tasks.db` khi chạy lần đầu. Sáu công việc mẫu chỉ được tạo một lần; tải lại trang không tạo thêm dữ liệu.

## 3. Chức năng sản phẩm

- Trang đầu diễn giải EC2, chức năng, ưu điểm và hạn chế.
- Đăng nhập và đăng xuất bằng mã truy cập chung cho demo.
- Thêm, sửa, xóa công việc; gán người phụ trách, mức ưu tiên và hạn.
- Đổi trạng thái ngay trên từng dòng.
- Tìm tên công việc hoặc người phụ trách; lọc trạng thái và ưu tiên.
- Thống kê theo toàn bộ cơ sở dữ liệu, độc lập với bộ lọc.
- Xuất các dòng đang lọc thành CSV UTF-8, có xử lý ký tự mở đầu công thức.
- Trang kiến trúc giải thích trình duyệt, Nginx, Python, SQLite và EBS.

Tên người và công việc mẫu là dữ liệu minh họa. Tìm kiếm không phân biệt hoa thường với ký tự ASCII; chữ có dấu cần nhập đúng dấu để có kết quả nhất quán.

## 4. Triển khai thực tế lên Amazon EC2

Phần này cần tài khoản AWS và quyền tạo EC2, EBS, Security Group, key pair trong VPC. Bộ bàn giao đã kiểm thử ứng dụng cục bộ; chưa tạo EC2 hoặc kiểm thử bộ cài trên máy AWS. Các bước dưới đây là quy trình triển khai để người thực hiện hoàn tất và chụp bằng chứng thật.

### 4.1 Tạo máy chủ

Trong EC2 Console, chọn Region phù hợp, ví dụ Singapore (ap-southeast-1). Tạo instance tên `taskflow-demo`:

- AMI: Ubuntu Server 24.04 LTS chính thức của Canonical, kiến trúc x86_64.
- Instance type: máy nhỏ phù hợp với tài khoản, ví dụ t3.micro nếu khả dụng. Kiểm tra giá và quyền lợi Free Tier ngay trên tài khoản, không mặc định miễn phí.
- EBS root volume: 8 GiB gp3, bật mã hóa. Cơ sở dữ liệu demo đặt trên ổ root này.
- Key pair: tạo hoặc dùng khóa SSH của bạn. Bảo quản file `.pem`, không đưa vào ZIP hay báo cáo.
- Network: public subnet có route `0.0.0.0/0` tới Internet Gateway; bật auto-assign public IPv4. Default VPC có thể dùng nếu còn tồn tại và đáp ứng cấu hình trên.
- Security Group inbound: TCP 22 từ **My IP/32** và TCP 80 từ **My IP/32**. Nếu giảng viên truy cập từ mạng khác, thêm đúng IP đó cho TCP 80. Không mở cổng 8080.
- Giữ outbound cho phép kết nối ra ngoài để cài gói Ubuntu. Chọn metadata IMDSv2 required nếu tùy chọn khả dụng; ứng dụng không đọc metadata và không cần IAM role hay access key.

Đợi máy chuyển sang Running và các status checks thành công. Sao chép Public IPv4. Nếu mạng lớp học chặn cổng 22 hoặc 80, dùng mạng phù hợp và cập nhật My IP.

### 4.2 Chuyển mã nguồn và chạy bộ cài

Trên máy Windows có OpenSSH, mở PowerShell tại thư mục chứa ZIP và khóa. Thay `PUBLIC_IPV4` và tên khóa bằng giá trị thật:

```powershell
scp -i .\taskflow-key.pem .\San_pham_demo_EC2.zip ubuntu@PUBLIC_IPV4:/home/ubuntu/
ssh -i .\taskflow-key.pem ubuntu@PUBLIC_IPV4
```

Kiểm tra dấu vân tay SSH bằng thông tin do AWS cung cấp trước khi chấp nhận kết nối lần đầu. Trên Ubuntu EC2:

```bash
sudo apt-get update
sudo apt-get install -y unzip
unzip San_pham_demo_EC2.zip -d taskflow-source
cd taskflow-source/ec2-demo
sudo bash deploy/setup_ec2.sh
```

Bộ cài dành riêng cho máy Ubuntu 24.04 mới, cài Python và Nginx, tạo tài khoản hệ thống không có shell, đặt ứng dụng tại `/opt/taskflow`, dữ liệu tại `/var/lib/taskflow/tasks.db`, tạo dịch vụ systemd và reverse proxy. Nhập mã truy cập mới ít nhất 12 ký tự theo yêu cầu của bộ cài. Mã không hiển thị khi gõ; không dùng `demo2026` trên EC2.

Bộ cài dừng nếu đã có `/etc/taskflow.env` hoặc `/opt/taskflow/app.py` để bảo vệ cấu hình hiện có. Đây là bộ cài lần đầu, không phải công cụ cập nhật ứng dụng. Nếu cài lỗi sau khi sao chép file, đọc nhật ký và sửa nguyên nhân trước khi chạy tiếp từng bước cần thiết.

Truy cập `http://PUBLIC_IPV4/`, đăng nhập bằng mã vừa đặt. Nginx nghe cổng 80 và chuyển yêu cầu vào Python tại `127.0.0.1:8080`. Chế độ EC2 yêu cầu mã mới; nhãn giao diện phản ánh cấu hình môi trường, **không tự chứng minh máy đang ở AWS**. Bằng chứng AWS phải gồm instance, địa chỉ truy cập và lệnh kiểm tra thực tế.

### 4.3 Kiểm tra máy chủ và lưu dữ liệu

```bash
curl http://127.0.0.1/health
sudo systemctl status taskflow --no-pager
sudo journalctl -u taskflow -n 30 --no-pager
sudo nginx -t
```

Thêm một công việc duy nhất, ghi lại tên và trạng thái, rồi chạy:

```bash
sudo systemctl restart taskflow
```

Tải lại trang, đăng nhập lại và xác nhận công việc còn nguyên. Sau đó, nếu cần minh họa vòng đời EC2, thực hiện Reboot instance trong Console, đợi máy sẵn sàng và kiểm tra lại ứng dụng. Phiên đăng nhập nằm trong RAM nên đăng nhập lại sau khi tiến trình khởi động lại là hành vi dự kiến.

Để sao lưu SQLite nhất quán khi ứng dụng đang chạy:

```bash
sudo -u taskflow python3 -c "import sqlite3; s=sqlite3.connect('/var/lib/taskflow/tasks.db'); d=sqlite3.connect('/var/lib/taskflow/backup.db'); s.backup(d); d.close(); s.close()"
```

Tải file backup về nơi an toàn trước khi xóa máy nếu muốn giữ dữ liệu. Lệnh trên chỉ tạo bản sao ngay trên cùng ổ đĩa, chưa phải sao lưu ngoài máy.

### 4.4 Chi phí và giới hạn

Chi phí gồm thời gian chạy EC2, dung lượng EBS, public IPv4, truyền dữ liệu và các tài nguyên phát sinh khác. Public IPv4 hiện có giá niêm yết cơ bản 0,005 USD/giờ/địa chỉ; hai giờ tương ứng 0,01 USD chỉ cho phần IPv4, trước ưu đãi và thuế. Giá EC2, EBS phụ thuộc Region và cấu hình. Tra giá hiện hành trước khi Launch.

Demo dùng HTTP, một mã chung, Python HTTP server tiêu chuẩn, một máy EC2 và SQLite. Chỉ dùng dữ liệu giả, giới hạn nguồn truy cập bằng Security Group. Muốn dùng thực tế cần HTTPS, xác thực theo người dùng, máy chủ ứng dụng phù hợp, quản lý bí mật, sao lưu ngoài máy và thiết kế sẵn sàng cao. Khi bổ sung HTTPS, bật `COOKIE_SECURE=1` trong môi trường ứng dụng.

### 4.5 Dọn tài nguyên

Sau buổi demo, sao lưu dữ liệu cần giữ rồi Terminate instance. Kiểm tra ổ EBS và `Delete on termination`; xóa các ổ/snapshot không còn cần. Nếu đã cấp Elastic IP, release khi không dùng. Chỉ xóa Security Group và key pair dành riêng cho bài này khi không còn phụ thuộc. Kiểm tra Billing/Cost Explorer sau khi dọn. Stop instance chỉ ngừng phần tính toán thông thường, EBS và một số tài nguyên khác vẫn có thể tính phí.

## 5. Kịch bản trình diễn 8 phút

1. Phút 0–2: nói EC2 là gì, AMI, EBS, Security Group; nêu hai ưu điểm và hai hạn chế.
2. Phút 2–3: chỉ sơ đồ kiến trúc; nếu đang chạy AWS, mở EC2 Console chỉ instance thật và rules cổng 22/80.
3. Phút 3–5: đăng nhập, thêm công việc `Kiem chung EC2`, phụ trách `Nhom demo`, ưu tiên Cao, đổi từ Chưa bắt đầu sang Đang thực hiện.
4. Phút 5–6: tìm đúng tên, lọc trạng thái, xuất CSV. Nhắc rằng số trên thẻ thống kê là số của toàn bộ dữ liệu.
5. Phút 6–7: khởi động lại ứng dụng, đăng nhập lại, xác nhận công việc còn tồn tại. Reboot EC2 có thể chuẩn bị trước do thời gian đợi khó đoán.
6. Phút 7–8: giải thích chi phí, hạn chế của một máy và cách dọn tài nguyên.

Nếu chỉ chạy cục bộ, nói rõ: “Đây là sản phẩm đã chạy trên máy; phần EC2 là hướng dẫn triển khai, chưa phải bằng chứng triển khai AWS.”

## 6. Tự chạy kiểm thử

```powershell
py -3 tests/test_api.py
```

Hoặc `python3 tests/test_api.py`. Bộ kiểm thử dùng cổng tạm, cơ sở dữ liệu tạm và mật khẩu riêng; không thay đổi dữ liệu demo của bạn. File `tests/test-results.json` ghi kết quả. Bộ bàn giao đã chạy 25 ca thành công; kết quả không thay thế kiểm thử trên EC2.

## 7. Cấu trúc mã nguồn

- `app.py`: HTTP API, kiểm tra dữ liệu, phiên đăng nhập, SQLite, CSV.
- `web/index.html`, `web/style.css`, `web/app.js`: giao diện và tương tác.
- `START_DEMO.cmd`: khởi động trên Windows.
- `deploy/setup_ec2.sh`: cài trên Ubuntu EC2 mới.
- `tests/test_api.py`: kiểm thử hành vi API và dữ liệu sau khởi động lại.
- `data/tasks.db`: chỉ tạo lúc chạy, không đóng gói sẵn.

## 8. Lỗi thường gặp

- Không mở được localhost: giữ cửa sổ chạy app mở, kiểm tra đúng cổng; xem thông báo lỗi Python.
- EC2 timeout: kiểm tra Running, checks, public IPv4, route tới Internet Gateway và source IP trong Security Group.
- Nginx báo 502: kiểm tra `systemctl status taskflow`, `journalctl` và `/etc/taskflow.env`.
- SSH lỗi quyền khóa: đặt quyền đọc khóa chỉ cho tài khoản của bạn; kiểm tra đúng người dùng `ubuntu` và đúng cặp khóa.
- Quên mã EC2: quản trị viên sửa `DEMO_PASSWORD` trong `/etc/taskflow.env`, giữ quyền file 600, sau đó restart dịch vụ. Không ghi mã vào báo cáo.
- Sau Stop/Start không vào được URL cũ: public IPv4 tự cấp có thể thay đổi; lấy địa chỉ mới từ Console.
