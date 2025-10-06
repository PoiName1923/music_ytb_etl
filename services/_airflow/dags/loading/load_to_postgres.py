# ====================================== PATH MANAGE ====================================== 
import os
import sys
import json
import pandas as pd
import re
from dotenv import load_dotenv
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
load_dotenv()

# ====================================== PATH MANAGE ====================================== 
from datetime import datetime, date
from dateutil import parser
from utils.setup_logger import setup_logger
from _postgres.postgres_scripts import PostgresManager
from _minio.minio_scripts import MinioClient

# ====================================== CONFIGURATION =====================================
POSTGRES_USER_ETL = os.getenv("POSTGRES_USER_ETL")
POSTGRES_PASSWORD_ETL = os.getenv("POSTGRES_PASSWORD_ETL")

POSTGRES_SCHEMA_ETL = os.getenv("POSTGRES_SCHEMA_ETL")
POSTGRES_DB_ETL = os.getenv("POSTGRES_DB_ETL")

POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")

POSTGRES_FACT_CHANNEL = os.getenv("POSTGRES_FACT_CHANNEL")
POSTGRES_DIM_CHANNEL = os.getenv("POSTGRES_DIM_CHANNEL")
POSTGRES_FACT_VIDEO = os.getenv("POSTGRES_FACT_VIDEO")
POSTGRES_DIM_VIDEO = os.getenv("POSTGRES_DIM_VIDEO")
POSTGRES_DIM_URL = os.getenv("POSTGRES_DIM_URL")


MINIO_ROOT_USER = os.getenv("MINIO_ROOT_USER")
MINIO_ROOT_PASSWORD = os.getenv("MINIO_ROOT_PASSWORD")
MINIO_HOST = os.getenv("MINIO_HOST")
MINIO_PORT = os.getenv("MINIO_PORT")

MINIO_BUCKET_YTB_DATA = os.getenv("MINIO_BUCKET_YTB_DATA")

MINO_LAYER_BRONZE = os.getenv("MINO_LAYER_BRONZE")
MINO_LAYER_SILVER = os.getenv("MINO_LAYER_SILVER")
MINO_LAYER_GOLD = os.getenv("MINO_LAYER_GOLD")

MINIO_FOLDER_VIDEOS = os.getenv("MINIO_FOLDER_VIDEOS")
MINIO_FOLDER_CHANNELS = os.getenv("MINIO_FOLDER_CHANNELS")

# =====================================================================================================
if __name__=="__main__":
    today = str(date.today())
    with MinioClient(host=MINIO_HOST,port=MINIO_PORT,
                     access_key=MINIO_ROOT_USER, secret_key=MINIO_ROOT_PASSWORD) as client_minio , \
         PostgresManager(user=POSTGRES_USER_ETL, password=POSTGRES_PASSWORD_ETL,
                           host=POSTGRES_HOST, port=POSTGRES_PORT, db_name=POSTGRES_DB_ETL) as client_postgres:
        # Đọc dữ liệu
        object_name_channels = f"processed-data/{MINIO_FOLDER_CHANNELS}/{today}.parquet"
        object_name_videos = f"processed-data/{MINIO_FOLDER_VIDEOS}/{today}.parquet"
        data_minio_videos = client_minio.read_parquet(bucket_name=MINIO_BUCKET_YTB_DATA, object_name=object_name_videos)
        data_minio_channels = client_minio.read_parquet(bucket_name=MINIO_BUCKET_YTB_DATA, object_name=object_name_channels)

        # Xác định từng trường dữ liệu
        data_dim_channels = data_minio_channels[['id','name','channel_url','join_date','location','description']]
        data_fact_channels = data_minio_channels[['id','total_views','subscribers','video_count','updated_at']]
        data_dim_videos = data_minio_videos[['video_id','channel_id','title','description','publish_date','duration_seconds','category']]
        data_fact_videos = data_minio_videos[['video_id','view_count','record_timestamp']]
        data_dim_url = data_minio_channels[['url','id','title_url']]
        data_dim_url = data_minio_channels[data_minio_channels["url"].notna()]

        # Load dữ liệu lên postgres
        client_postgres.bulk_insert_ignore(table=f"{POSTGRES_SCHEMA_ETL}.{POSTGRES_DIM_CHANNEL}", 
                        df=data_dim_channels, 
                        column_mapping={"id":"channel_id",
                                        "name":"channel_name",
                                        "channel_url":"channel_url",
                                        "join_date":"join_date",
                                        "location":"location",
                                        "description":"description"
                                        },
                        conflict_columns=['channel_id'])
        client_postgres.commit()
        client_postgres.bulk_insert_ignore(table=f"{POSTGRES_SCHEMA_ETL}.{POSTGRES_DIM_URL}", 
                            df=data_dim_url, 
                            column_mapping={"url":"url",
                                            "id":"channel_id",
                                            "title_url":"title_url"
                                            },
                            conflict_columns=['url'])
        client_postgres.commit()
        client_postgres.bulk_insert_ignore(table=f"{POSTGRES_SCHEMA_ETL}.{POSTGRES_DIM_VIDEO}", 
                            df=data_dim_videos, 
                            column_mapping={"video_id":"video_id",
                                            "channel_id":"channel_id",
                                            "title":"title",
                                            "description":"description",
                                            "publish_date":"publish_date",
                                            "duration_seconds":"duration_seconds",
                                            "category":"category"
                                            },
                            conflict_columns=['video_id'])
        client_postgres.commit()
        client_postgres.bulk_insert_ignore(table=f"{POSTGRES_SCHEMA_ETL}.{POSTGRES_FACT_CHANNEL}", 
                            df=data_fact_channels, 
                            column_mapping={"id":"channel_id",
                                            "total_views":"total_views",
                                            "subscribers":"subscribers",
                                            "video_count":"video_count",
                                            "updated_at":"record_timestamp"
                                            },
                            conflict_columns=["channel_id","record_timestamp"])
        client_postgres.commit()
        client_postgres.bulk_insert(table=f"{POSTGRES_SCHEMA_ETL}.{POSTGRES_FACT_VIDEO}", 
                            df=data_fact_videos, 
                            column_mapping={"video_id":"video_id",
                                            "view_count":"view_count",
                                            "record_timestamp":"record_timestamp"
                                            })
        client_postgres.commit()