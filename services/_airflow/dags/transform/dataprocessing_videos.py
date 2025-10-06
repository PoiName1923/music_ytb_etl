# ====================================== PATH MANAGE ====================================== 
import os
import sys
import json
import pandas as pd
from dotenv import load_dotenv
load_dotenv()
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
load_dotenv()
# ====================================== PATH MANAGE ====================================== 
from datetime import datetime
from dateutil import parser
from utils.setup_logger import setup_logger
from _minio.minio_scripts import MinioClient
import pytz
# ====================================== CONFIGURATION ======================================
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

# ============================================================================================

class SilverVideosProcessor:
    """
    Lớp chịu trách nhiệm cho việc đọc dữ liệu thô từ lớp Bronze,
    thực hiện làm sạch, chuẩn hóa và lưu kết quả vào lớp Silver.
    """
    def __init__(self, minio_config):
        self.logger = setup_logger(name="VideosProcessor", log_folder="logs/silver", log_filename="videos.log")
        try:
            self.minio_client = MinioClient(
                host=minio_config['host'],
                port=minio_config['port'],
                access_key=minio_config['access_key'],
                secret_key=minio_config['secret_key']
            )
            self.logger.info("Khởi tạo MinioClient thành công.")
        except Exception as e:
            self.logger.error(f"Lỗi khi khởi tạo MinioClient: {e}")
            raise

    def __extract_thumbnail_url(self, data):
        try:
            # Dữ liệu có thể là list, và list đó có thể rỗng
            if isinstance(data, list) and len(data) > 0:
                return data[0].get('url')
        except:
            return None
        return None
    
    def __normalize_timestamp(self, ts):
        try:
            date_part, hour, minute, tz_abbr = ts.split("_")
            dt = datetime.strptime(f"{date_part}_{hour}_{minute}", "%Y-%m-%d_%H_%M")
            source_tz = pytz.timezone("US/Eastern")
            dt = source_tz.localize(dt)
            vn_time = dt.astimezone(pytz.timezone("Asia/Ho_Chi_Minh"))
            return vn_time.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return None
        
    def _transform_and_clean(self, df):
        """
        Thực hiện toàn bộ quá trình chuyển đổi và làm sạch trên DataFrame.
        """
        if df.empty:
            return pd.DataFrame()

        required_cols = ['microformatDataRenderer', 'record_timestamp']
        if not all(col in df.columns for col in required_cols):
            missing_cols = [col for col in required_cols if col not in df.columns]
            raise ValueError(f"Các cột cần thiết bị thiếu trong DataFrame từ Bronze: {missing_cols}.")

        def safe_json_loads(s):
            try:
                return json.loads(s) if isinstance(s, str) else s
            except (json.JSONDecodeError, TypeError):
                return None
        
        parsed_data = df['microformatDataRenderer'].apply(safe_json_loads)
        valid_rows_mask = parsed_data.notna()
        
        if not valid_rows_mask.any():
            self.logger.warning("Không có hàng nào có dữ liệu JSON hợp lệ.")
            return pd.DataFrame()

        timestamps_df = df.loc[valid_rows_mask, ['record_timestamp']].reset_index(drop=True)
        normalized_df = pd.json_normalize(parsed_data[valid_rows_mask]).reset_index(drop=True)
        silver_df = pd.concat([normalized_df, timestamps_df], axis=1)
        
        column_mapping = {
            'title': 'title',
            'description': 'description',
            'viewCount': 'view_count',
            'publishDate': 'publish_date',
            'category': 'category',
            'tags': 'tags',
            'videoDetails.externalVideoId': 'video_id',
            'videoDetails.durationSeconds': 'duration_seconds',
            'pageOwnerDetails.name': 'channel_name',
            'pageOwnerDetails.externalChannelId': 'channel_id',
            'thumbnail.thumbnails': 'thumbnail_data'
        }
        # Ép kiểu và làm sạch các cột cơ bản
        silver_df = silver_df.rename(columns=column_mapping)
        
        silver_df['view_count'] = pd.to_numeric(silver_df.get('view_count'), errors='coerce').fillna(0).astype('int64')
        silver_df['duration_seconds'] = pd.to_numeric(silver_df.get('duration_seconds'), errors='coerce').fillna(0).astype('int64')
        silver_df['publish_date'] = pd.to_datetime(silver_df.get('publish_date'), errors='coerce')
        silver_df['record_timestamp'] = silver_df['record_timestamp'].apply(lambda x: self.__normalize_timestamp(x))
        silver_df['thumbnail_url'] = silver_df['thumbnail_data'].apply(self.__extract_thumbnail_url)
        
        if 'title' in silver_df.columns:
            silver_df['title'] = silver_df['title'].str.strip()
        if 'tags' not in silver_df.columns:
             silver_df['tags'] = [[] for _ in range(len(silver_df))]
        else:
             silver_df['tags'] = silver_df['tags'].fillna('').apply(lambda x: list(x) if isinstance(x, (list, tuple)) else [])


        silver_schema = [
            'video_id', 'title', 'description', 'publish_date', 'view_count', 
            'duration_seconds', 'category', 'tags', 'channel_id', 'channel_name', 
            'thumbnail_url', 'record_timestamp'
        ]
        for col in silver_schema:
            if col not in silver_df.columns:
                silver_df[col] = None

        silver_df = silver_df[silver_schema]. \
                            dropna(subset=["publish_date", "record_timestamp"], how="any"). \
                            reset_index(drop=True)
        return silver_df

    def process_bronze_to_silver(self, source_bucket, source_folder, dest_bucket, dest_folder):
        """
        Quy trình chính: Đọc từ Bronze -> Chuyển đổi và làm sạch -> Ghi vào Silver.
        """
        self.logger.info(f"Bắt đầu quy trình xử lý Bronze -> Silver cho folder: '{source_folder}'")
        
        prefix = source_folder + '/' if not source_folder.endswith('/') else source_folder
        all_objects = self.minio_client.list_files(source_bucket, prefix=prefix)
        parquet_files = [obj for obj in all_objects if obj.endswith('.parquet')]

        if not parquet_files:
            self.logger.warning(f"Không tìm thấy file Parquet nào trong folder '{source_folder}'. Kết thúc quy trình.")
            return

        list_of_dfs = []
        for file_path in parquet_files:
            df = self.minio_client.read_parquet(source_bucket, file_path)
            if not df.empty:
                file_basename = os.path.basename(file_path)
                file_name_without_ext = os.path.splitext(file_basename)[0]
                df['record_timestamp'] = file_name_without_ext
                list_of_dfs.append(df)

        if not list_of_dfs:
            self.logger.warning("Không có dữ liệu trong các file nguồn. Kết thúc quy trình.")
            return

        bronze_df = pd.concat(list_of_dfs, ignore_index=True)
        self.logger.info(f"Đã đọc và gộp {len(bronze_df)} dòng từ {len(list_of_dfs)} file trong lớp Bronze.")

        silver_df = self._transform_and_clean(bronze_df)
        
        if silver_df.empty:
            self.logger.warning("Không có dữ liệu hợp lệ sau khi xử lý. Kết thúc quy trình.")
            return

        self.logger.info(f"Xử lý thành công {len(silver_df)} dòng dữ liệu.")

        today_str = datetime.today().strftime("%Y-%m-%d")
        obj_name = f"{dest_folder}/{today_str}.parquet"
        
        self.minio_client.upload_parquet(
            bucket_name=dest_bucket,
            object_name=obj_name,
            dataframe=silver_df
        )

if __name__ == '__main__':
    minio_connection_config = {
        "host": MINIO_HOST,
        "port": MINIO_PORT,
        "access_key": MINIO_ROOT_USER,
        "secret_key": MINIO_ROOT_PASSWORD
    }
    
    processor = SilverVideosProcessor(minio_config=minio_connection_config)

    source_folder = f"{MINO_LAYER_BRONZE}/{MINIO_FOLDER_VIDEOS}"
    dest_folder   = f"{MINO_LAYER_SILVER}/{MINIO_FOLDER_VIDEOS}"

    processor.process_bronze_to_silver(
        source_bucket=MINIO_BUCKET_YTB_DATA,
        source_folder=source_folder,
        dest_bucket=MINIO_BUCKET_YTB_DATA,
        dest_folder=dest_folder
    )
