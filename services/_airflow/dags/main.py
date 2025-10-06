# main_dag.py

from __future__ import annotations

import pendulum

from airflow.models.dag import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
from datetime import datetime, timedelta
# ==========================================================================================
# === 1. ĐỊNH NGHĨA CÁC THAM SỐ MẶC ĐỊNH (DEFAULT ARGS) =======================================
# ==========================================================================================
# Đây là các tham số sẽ được áp dụng cho tất cả các task trong DAG.
# Việc này giúp tránh lặp lại code và dễ dàng quản lý.

default_args = {
    "owner": "ndtien", # Tên người sở hữu DAG
    "depends_on_past": False, # Task không phụ thuộc vào trạng thái của lần chạy trước
    "email_on_failure": True, # gửi email khi thất bại
    "email_on_retry": True, # gửi email khi thử lại
    "retries": 5, # Số lần thử lại nếu task thất bại
    "retry_delay": pendulum.duration(minutes=1), # Thời gian chờ giữa các lần thử lại
}

# ==========================================================================================
# === 2. ĐỊNH NGHĨA DAG CHÍNH ==============================================================
# ==========================================================================================
# Sử dụng 'with' statement là một practice tốt nhất để định nghĩa DAG.

with DAG(
    dag_id="YTB_MUSIC_AIRFLOW", # Tên định danh duy nhất cho DAG
    default_args=default_args,
    description="Mẫu DAG để thu thập dữ liệu về các bài hát trending từ youtube music",
    start_date=pendulum.datetime(2025, 8, 30, tz="Asia/Ho_Chi_Minh"), # Ngày bắt đầu chạy DAG
    schedule="*/15 * * * *", # Lịch trình chạy DAG, ví dụ: "@daily", "@hourly", "0 0 * * *"
    catchup=False, # Không chạy lại các lần chạy bị lỡ trong quá khứ
    tags=["ytb", "ytbmusic"], # Gán nhãn để dễ dàng lọc và tìm kiếm trên UI
) as dag:
    
    # Thêm tài liệu cho DAG, sẽ hiển thị trên giao diện Airflow UI
    dag.doc_md = """ HE HE """

    # ======================================================================================
    # === 3. ĐỊNH NGHĨA CÁC TASK (CÁC BƯỚC TRONG PIPELINE) ==================================
    # ======================================================================================

    # Task bắt đầu: Sử dụng EmptyOperator để đánh dấu điểm bắt đầu của luồng.
    start = EmptyOperator(
        task_id="start"
    )

    # --- CHẠY FILE PYTHON BẰNG BASHOPERATOR ---
    # Airflow sẽ gọi một tiến trình bash và thực thi lệnh được cung cấp.
    crawling_trending_music_on_kworb = BashOperator(
        task_id="crawling_trending_music_on_kworb",
        bash_command="python /opt/airflow/app/_airflow/dags/extract/trending.py",
    )
    extract_detail_songs = BashOperator(
        task_id="extract_detail_songs",
        bash_command="python /opt/airflow/app/_airflow/dags/extract/detail_song.py",
    )
    extract_detail_channels = BashOperator(
        task_id="extract_detail_channels",
        bash_command="python /opt/airflow/app/_airflow/dags/extract/detail_channel.py",
    )
    processing_data_videos = BashOperator(
        task_id="processing_data_videos",
        bash_command="python /opt/airflow/app/_airflow/dags/transform/dataprocessing_videos.py",
    )
    processing_data_channels = BashOperator(
        task_id="processing_data_channels",
        bash_command="python /opt/airflow/app/_airflow/dags/transform/dataprocessing_channels.py",
    )
    # Task kết thúc: Đánh dấu điểm kết thúc của luồng.
    end = EmptyOperator(
        task_id="end"
    )


    # ======================================================================================
    # === 4. ĐỊNH NGHĨA LUỒNG CHẠY (TASK DEPENDENCIES) ======================================
    # ======================================================================================
    start >> crawling_trending_music_on_kworb
    crawling_trending_music_on_kworb >> extract_detail_songs >> extract_detail_channels >> [processing_data_videos,processing_data_channels] >> end

with DAG(
    dag_id='LOADING_POSTGRES_DAILY_YTB_MUSIC',
    default_args=default_args,
    description='Một dags để chạy vào cuối ngày để đưa toàn bộ dữ liệu của ngày hôm đó vào postgres',
    schedule_interval="0 23 * * *",
    start_date=datetime(2025, 9, 10),
    catchup=False,
    tags=['postgres', 'daily'],
) as dag_2:
    start = EmptyOperator(task_id="start")
    daily_loading = BashOperator(
        task_id="daily_loading_postgres",
        bash_command="python /opt/airflow/app/_airflow/dags/loading/load_to_postgres.py",
    )
    end = EmptyOperator(task_id="end")
    start >> daily_loading >> end