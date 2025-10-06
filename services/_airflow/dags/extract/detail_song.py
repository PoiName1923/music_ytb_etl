# ====================================== PATH MANAGE ====================================== 
import os
import sys
import pandas as pd
from dotenv import load_dotenv
load_dotenv()

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
# ==========================================================================================
from _selenium.scripts.crawling_trending_song import TrendingVideoYTB
from _mongo.mongo_scripts import MongoManager
from _minio.minio_scripts import MinioClient
from datetime import datetime, timezone
from ytmusicapi import YTMusic
import re
# ====================================== CONFIGURATION ======================================
MONGO_ADMIN_USER = os.getenv("MONGO_ADMIN_USER")
MONGO_ADMIN_PASSWORD = os.getenv("MONGO_ADMIN_PASSWORD")
MONGO_HOST = os.getenv("MONGO_HOST")
MONGO_PORT = os.getenv("MONGO_PORT")

MONGO_DB_TRENDING_YTB_VIDEOS = os.getenv("MONGO_DB_TRENDING_YTB_VIDEOS")
MONGO_COLL_SES_TRENDING_VIDEOS = os.getenv("MONGO_COLL_SES_TRENDING_VIDEOS")
MONGO_COLL_UNIQUE_VIDEOS = os.getenv("MONGO_COLL_UNIQUE_VIDEOS")
MONGO_COLL_UNIQUE_CHANNELS = os.getenv("MONGO_COLL_UNIQUE_CHANNELS")

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
# ==========================================================================================
if __name__ == '__main__':
    with MongoManager(user=MONGO_ADMIN_USER, password=MONGO_ADMIN_PASSWORD,
                     host=MONGO_HOST, port=MONGO_PORT, db_name=MONGO_DB_TRENDING_YTB_VIDEOS) as mongo_client, \
         MinioClient(host=MINIO_HOST, port=MINIO_PORT,
                     access_key=MINIO_ROOT_USER,
                     secret_key=MINIO_ROOT_PASSWORD) as minio_client:
        yt = YTMusic()
        
        # ========================== Lấy url từ Mongo ==========================
        # Thu thập thời gian mới nhất của dữ liệu
        document_newest = mongo_client.find_latest_one(collection_name=MONGO_COLL_SES_TRENDING_VIDEOS, sort_field="updated_at")
        updated_at = document_newest['updated_at'] if document_newest else None
        updated_at = re.sub(r'[^A-Za-z0-9._-]', '_', updated_at)    
        # Dữ liệu các url được thu thập 
        list_url_videos = mongo_client.find(collection_name=MONGO_COLL_UNIQUE_VIDEOS)

        # ========================== Trích xuất thông tin từ YTBMUSIC và lưu vào MINIO ==========================
        totalVideoDetail = []
        for video in list_url_videos:
            try:
                # Trích xuất dữ liệu từ ytbmusicapi
                video_id = video['video_id']
                data = yt.get_song(videoId=video_id)
                videoData = data.get('microformat')
                
                if videoData:
                    # Thêm id channel vào collection khác để quản lý các channel duy nhất
                    pageOwnerDetails = videoData.get('microformatDataRenderer')['pageOwnerDetails']
                    if pageOwnerDetails:
                        mongo_client.insert_if_not_exists(
                            collection_name=MONGO_COLL_UNIQUE_CHANNELS,
                            document=pageOwnerDetails,
                            unique_field='externalChannelId'
                        )
                    totalVideoDetail.append(videoData)
                else:
                    mongo_client.logger.warning(f"Không tìm thấy microformat cho video_id: {video_id}")
            except Exception as e:
                mongo_client.logger.error(f"Lỗi khi lấy dữ liệu video_id {video_id}: {e}")
                continue
        # ========================== Lưu kết quả vào MINIO ==========================

        obj_name = f"{MINO_LAYER_BRONZE}/{MINIO_FOLDER_VIDEOS}/{updated_at}.parquet"
        if totalVideoDetail:
            # Chuyển totalVideoDetail thành DataFrame
            video_df = pd.DataFrame(totalVideoDetail)
            video_df['record_timestamp'] = updated_at
            print(f"DEBUG: Tên file sẽ được lưu vào MinIO là: '{updated_at}.parquet'")
            # Upload DataFrame dưới dạng Parquet vào MinIO
            minio_client.upload_parquet(
                bucket_name=MINIO_BUCKET_YTB_DATA,
                object_name=obj_name,
                dataframe=video_df
            )
        else:
            mongo_client.logger.warning("Không có dữ liệu video để upload vào MinIO.")
        # ========================================================================================================