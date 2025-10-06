# ====================================== PATH MANAGE ====================================== 
import os
import sys
import pandas as pd
from dotenv import load_dotenv
load_dotenv()

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
# ==========================================================================================
from _selenium.scripts.crawling_trending_song import TrendingVideoYTB
from _selenium.scripts.crawling_detail_channel import DetailChannelYTB

from _mongo.mongo_scripts import MongoManager
from _minio.minio_scripts import MinioClient
from utils.setup_logger import setup_logger
from datetime import datetime, timezone
from ytmusicapi import YTMusic
import re
from multiprocessing import Pool, cpu_count

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

SELENIUM_HOST_URL=os.getenv("SELENIUM_HOST_URL")
NUM_WORKERS = 3
file_logger = setup_logger(name="WorkerCrawlingDetailChannels",log_folder="logs",log_filename='worker-selenium.log')

# ====================================== WORKER FUNCTION =====================================
def scrape_channel_worker(channel_doc):
    """
    Hàm worker để cào dữ liệu cho MỘT kênh.
    Hàm này sẽ được chạy trong một tiến trình riêng biệt.
    
    Args:
        channel_doc (dict): Một document từ MongoDB chứa thông tin kênh.
    
    Returns:
        dict: Dữ liệu chi tiết của kênh đã được cào, hoặc None nếu có lỗi.
    """
    channel_url = channel_doc.get('youtubeProfileUrl')
    channel_id = channel_doc.get('externalChannelId')
    channel_name = channel_doc.get('name')
    
    if not channel_url or not channel_id or not channel_name:
        return None

    # Quan trọng: Mỗi worker phải tự khởi tạo và đóng driver của riêng mình.
    # Sử dụng 'with' để đảm bảo driver luôn được đóng ngay cả khi có lỗi.
    try:
        with DetailChannelYTB(host_url=SELENIUM_HOST_URL) as driver:
            channel_data = driver.extract_pipeline(url=channel_url)
            channel_data['channel_url'] = channel_url
            channel_data['name'] = channel_name
            channel_data['id'] = channel_id
            return channel_data
    except Exception as e:
        return None

# ====================================== MAIN EXECUTION =====================================
if __name__ == '__main__':
    with MongoManager(user=MONGO_ADMIN_USER, password=MONGO_ADMIN_PASSWORD,
                     host=MONGO_HOST, port=MONGO_PORT, db_name=MONGO_DB_TRENDING_YTB_VIDEOS) as mongo_client, \
         MinioClient(host=MINIO_HOST, port=MINIO_PORT,
                     access_key=MINIO_ROOT_USER,
                     secret_key=MINIO_ROOT_PASSWORD) as minio_client:
        
        # ========================== Lấy danh sách kênh từ Mongo ==========================
        document_newest = mongo_client.find_latest_one(collection_name=MONGO_COLL_SES_TRENDING_VIDEOS, sort_field="updated_at")
        updated_at = document_newest['updated_at'] if document_newest else datetime.now().isoformat()
        updated_at = re.sub(r'[^A-Za-z0-9._-]', '_', updated_at)    
        
        list_channels = mongo_client.find(collection_name=MONGO_COLL_UNIQUE_CHANNELS)
        
        if not list_channels:
            file_logger.error("Không tìm thấy kênh nào trong MongoDB để cào dữ liệu.")
        else:
            file_logger.info(f"Tìm thấy {len(list_channels)} kênh. Bắt đầu cào dữ liệu song song với {NUM_WORKERS} worker...")
            
            # ========================== Trích xuất thông tin song song ==========================
            # Khởi tạo Pool với số lượng worker đã định.
            with Pool(processes=NUM_WORKERS) as pool:
                # pool.map sẽ phân chia 'list_channels' cho các worker
                # và chạy hàm 'scrape_channel_worker' trên mỗi phần tử.
                # Nó sẽ chặn cho đến khi tất cả các worker hoàn thành.
                results = pool.map(scrape_channel_worker, list_channels)
            
            # Lọc bỏ các kết quả bị lỗi (None)
            totalChannelDetail = [res for res in results if res is not None]
            
            print(f"Hoàn thành cào dữ liệu. Thu được thông tin của {len(totalChannelDetail)} kênh.")
            
            # ========================== Lưu kết quả vào MINIO ==========================
            obj_name = f"{MINO_LAYER_BRONZE}/{MINIO_FOLDER_CHANNELS}/{updated_at}.parquet"
            if totalChannelDetail:
                channel_df = pd.DataFrame(totalChannelDetail)
                print(f"Tên file sẽ được lưu vào MinIO là: '{updated_at}.parquet'")

                minio_client.upload_parquet(
                    bucket_name=MINIO_BUCKET_YTB_DATA,
                    object_name=obj_name,
                    dataframe=channel_df
                )
            else:
                mongo_client.logger.warning("Không có dữ liệu kênh nào được thu thập để upload vào MinIO.")
# ========================================================================================================