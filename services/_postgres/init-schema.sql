
-- Bắt đầu một transaction để đảm bảo tất cả các lệnh đều thành công
BEGIN;

-- Tạo một schema mới có tên là 'youtube_data'
-- IF NOT EXISTS đảm bảo không bị lỗi nếu schema đã tồn tại
CREATE SCHEMA IF NOT EXISTS :"app_schema";

-- Cấp quyền cho user
GRANT USAGE, CREATE ON SCHEMA :"app_schema" TO :"app_user";
-- Duy chuyển đến schema
SET search_path TO :"app_schema";
-- =======================
-- DIMENSION TABLES
-- =======================
-- Channel (thuộc về 1 user)
CREATE TABLE dim_channel (
    channel_id VARCHAR(255) PRIMARY KEY,
    channel_name VARCHAR(255) NOT NULL,
    channel_url TEXT UNIQUE NOT NULL,
    join_date DATE,
    location VARCHAR(255),
    description TEXT
);

-- Video (thuộc về 1 channel)
CREATE TABLE dim_video (
    video_id VARCHAR(255) PRIMARY KEY,
    channel_id VARCHAR(255) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    publish_date DATE,
    duration_seconds INT,
    category VARCHAR(100),
    FOREIGN KEY (channel_id) REFERENCES dim_channel(channel_id) ON DELETE CASCADE
);

-- URL liên quan đến channel
CREATE TABLE dim_url (
    url TEXT PRIMARY KEY,
    channel_id VARCHAR(255) NOT NULL,
    title_url VARCHAR(255),
    FOREIGN KEY (channel_id) REFERENCES dim_channel(channel_id) ON DELETE CASCADE
);

-- =======================
-- FACT TABLES
-- =======================

-- Snapshot thống kê video
CREATE TABLE fact_video_record (
    record_id SERIAL PRIMARY KEY,
    video_id VARCHAR(255) NOT NULL,
    view_count BIGINT,
    record_timestamp TIMESTAMP,
    FOREIGN KEY (video_id) REFERENCES dim_video(video_id) ON DELETE CASCADE
);

-- Snapshot thống kê channel
CREATE TABLE fact_channel_record (
    record_id SERIAL PRIMARY KEY,
    channel_id VARCHAR(255) NOT NULL,
    total_views BIGINT,
    subscribers BIGINT,
    video_count INT,
    record_timestamp TIMESTAMP,
    FOREIGN KEY (channel_id) REFERENCES dim_channel(channel_id) ON DELETE CASCADE,
    UNIQUE (channel_id, record_timestamp) 
);

-- Cấp tất cả các quyền (SELECT, INSERT, UPDATE, DELETE) trên TẤT CẢ các bảng
-- trong schema 'youtube_data' cho user ứng dụng.
GRANT ALL ON ALL TABLES IN SCHEMA :"app_schema" TO :"app_user";

-- Quan trọng: Cấp quyền sử dụng cho các sequence (dùng cho cột SERIAL)
-- Nếu không có dòng này, lệnh INSERT sẽ thất bại.
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA :"app_schema" TO :"app_user";

-- Kết thúc transaction
COMMIT;