# ETL YOUTUBE MUSIC
Dự án dựng hạ tầng thu thập và xử lý dữ liệu YouTube (trending/âm nhạc) bằng Selenium + MongoDB + MinIO + PostgreSQL, điều phối bởi Airflow.

## Mục tiêu
- Chuẩn hóa một stack hạ tầng ETL/ELT để crawl, lưu trữ và phân tích dữ liệu YouTube.
- Lưu dữ liệu thô và các lớp xử lý theo mô hình data lake (bronze/silver/gold).
- Thiết kế kho dữ liệu dạng star schema (dimension/fact) trong PostgreSQL.
- Sẵn sàng quan sát và vận hành thông qua các UI quản trị (Airflow, Adminer, Mongo Express, MinIO Console).

## Kết quả
- Stack dịch vụ được định nghĩa trong `docker-compose.yml` với đầy đủ healthcheck.
- PostgreSQL được khởi tạo thêm user/database ETL và schema riêng (xem `services/_postgres/init-schema.sql`).
- Các bảng dữ liệu chính:
  - `dim_channel`, `dim_video`, `dim_url`
  - `fact_video_record`, `fact_channel_record`
- MongoDB và MinIO sẵn sàng cho lưu trữ dữ liệu thô/processed.

## Quy trình hoạt động
1) Selenium Grid (Hub + Chrome Node) thực hiện crawl dữ liệu từ YouTube.
2) Dữ liệu raw được lưu vào MongoDB và/hoặc MinIO (layer bronze).
3) Các bước xử lý/chuẩn hóa tạo dữ liệu silver và gold trên MinIO.
4) Dữ liệu sạch được nạp vào PostgreSQL theo mô hình dim/fact.
5) Airflow điều phối lịch chạy, quản lý DAG và log xử lý.
6) Người dùng truy cập kết quả qua Adminer (Postgres), Mongo Express (Mongo), MinIO Console, hoặc Airflow UI.

Lưu ý: repo hiện chỉ có phần hạ tầng và script khởi tạo DB; chưa có code DAG/crawler. Quy trình trên là luồng dự kiến theo cấu hình hiện có.

## Kiến trúc & thành phần
- Selenium Hub + Chrome Node (Selenium Grid)
- MongoDB + Mongo Express
- MinIO (object storage)
- PostgreSQL + Adminer
- Redis (broker cho CeleryExecutor)
- Airflow: init, webserver, scheduler, worker

## Cấu trúc thư mục
- `docker-compose.yml`: định nghĩa toàn bộ stack dịch vụ.
- `sample.env`: mẫu cấu hình biến môi trường.
- `services/_selenium/`: Dockerfile cho Selenium Hub/Chrome.
- `services/_postgres/`: script tạo DB/schema + tiện ích kết nối.
- `picture/diagram_schema.pdf`: sơ đồ dữ liệu tham khảo.
- `services/_airflow/`, `services/_mongo/`, `services/_minio/`, `services/utils/`: hiện đang trống trong repo.

## Cài đặt & chạy
1) Tạo file `.env` từ mẫu:
```bash
cp sample.env .env
```
2) Điền đầy đủ biến môi trường trong `.env`.
3) Khởi động stack:
```bash
docker compose up -d --build
```

## Cổng truy cập dịch vụ
- Airflow Webserver: `http://localhost:8080`
- Mongo Express: `http://localhost:8081`
- Adminer (Postgres UI): `http://localhost:8082`
- MinIO API: `http://localhost:9000`
- MinIO Console: `http://localhost:9001`
- Selenium Hub: `http://localhost:4444`
- VNC Chrome Node: `localhost:5900`
- MongoDB: `mongodb://localhost:27017`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

## Lược đồ dữ liệu PostgreSQL
Schema ETL được tạo theo biến `POSTGRES_SCHEMA_ETL` và gồm các bảng:
- `dim_channel`: thông tin kênh.
- `dim_video`: thông tin video.
- `dim_url`: URL liên quan đến kênh.
- `fact_video_record`: snapshot thống kê video.
- `fact_channel_record`: snapshot thống kê kênh.

Sơ đồ chi tiết tham khảo `picture/diagram_schema.pdf`.

## Tiện ích PostgreSQL
`services/_postgres/postgres_scripts.py` cung cấp `PostgresManager` với:
- CRUD có điều kiện an toàn (parameterized).
- Bulk insert, upsert, insert ignore bằng `execute_values`.
- Hỗ trợ mapping cột từ DataFrame và cache metadata.

## Biến môi trường chính
Tham khảo đầy đủ trong `sample.env`. Các nhóm chính:
- Selenium: `SELENIUM_HOST_URL`
- MongoDB: thông tin admin, database, collection
- MinIO: tài khoản, bucket, folder theo layer
- PostgreSQL: user Airflow, user ETL, schema, tên bảng
- Airflow: thông tin tài khoản admin

## Lưu ý/Tồn tại
- `services/_airflow/dockerfile.airflow` đang được gọi trong `docker-compose.yml` nhưng thư mục trống.
- `services/_mongo/init-db.js` được mount trong `docker-compose.yml` nhưng chưa có file.
- `services/utils/setup_logger.py` được import trong `postgres_scripts.py` nhưng chưa có file.
Hãy bổ sung các phần này trước khi chạy pipeline thực tế.
