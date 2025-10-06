# ====================================== PATH MANAGE ====================================== 
import os
import sys
import json
import pandas as pd
import re
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

class SilverChannelsProcessor:
    """
    Lớp chịu trách nhiệm cho việc đọc dữ liệu thô từ lớp Bronze,
    thực hiện làm sạch, chuẩn hóa và lưu kết quả vào lớp Silver.
    """
    def __init__(self, minio_config):
        self.logger = setup_logger(name="VideosProcessor", log_folder="logs/silver", log_filename="channels.log")
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
        
    def __parse_numeric_value(self,  value):
        """Chuyển đổi chuỗi (ví dụ: '13.4K', '10,227,643') thành số nguyên."""
        if not isinstance(value, str):
            return 0
        value = value.lower().strip()
        value = re.sub(r'[, views subscribers videos]', '', value)
        
        multiplier = 1
        if 'k' in value:
            multiplier = 1000
            value = value.replace('k', '')
        elif 'm' in value:
            multiplier = 1000000
            value = value.replace('m', '')
            
        try:
            return int(float(value) * multiplier)
        except (ValueError, TypeError):
            return 0
        
    def __extract_urls(self, data_str):
        """Chuyển string JSON thành list dict [{title, url}]"""
        try:
            data = json.loads(data_str)
            return [{"title": item.get("title"), "url": item.get("url")} for item in data]
        except (json.JSONDecodeError, TypeError):
            return []


    def _process_links_column(self, df):
        """Nhận DataFrame có cột chứa str JSON link, trả về DataFrame đã phân loại"""    
        # B1: parse JSON string -> list link dicts
        df["parsed_links"] = df['links'].apply(self.__extract_urls)
        
        # B2: bung list thành từng row (explode)
        df = df.explode("parsed_links").reset_index(drop=True)
        
        # B3: tách title + url riêng
        df["title_url"] = df["parsed_links"].apply(lambda x: x.get("title") if isinstance(x, dict) else None)
        df["url"]   = df["parsed_links"].apply(lambda x: x.get("url") if isinstance(x, dict) else None)
        df.drop(columns=['links'], inplace=True)
        df.drop(columns=['parsed_links'], inplace=True)
        
        return df
    
    def _extract_channel_id_from_url(self, url):
        """Trích xuất Channel ID hoặc Handle từ URL của kênh YouTube."""
        if not isinstance(url, str): return None
        patterns = [
            r'/(channel|c|user)/([^/?]+)', # Lấy ID kênh
            r'/@([^/?]+)' # Lấy handle kênh
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                # Đối với handle, trả về có dấu @
                return '@' + match.group(1) if pattern.endswith('([^/?]+)') else match.group(2)
        return None
    
    def __parse_joined_date(self, text):

        if not text or not isinstance(text, str):
            return None
        try:
            # loại bỏ tiền tố "Joined "
            clean_text = text.replace("Joined", "").strip()
            # parse với format tháng viết tắt (Aug)
            dt = datetime.strptime(clean_text, "%b %d, %Y")
            return dt  # trả về datetime
            # return dt.date().isoformat()  # nếu muốn trả về dạng '2014-08-06'
        except Exception:
            return None
        
    def _transform_and_clean(self, df):
        """
        Thực hiện toàn bộ quá trình chuyển đổi và làm sạch trên DataFrame.
        """
        if df.empty:
            return pd.DataFrame()
        required_cols = ['channel_url', 'info_outline','person_radar','my_videos','privacy_public','links']
        if not all(col in df.columns for col in required_cols):
            missing_cols = [col for col in required_cols if col not in df.columns]
            raise ValueError(f"Các cột cần thiết bị thiếu trong DataFrame từ Bronze: {missing_cols}.")
        silver_df = df.copy()

        column_mapping = {
            'id':'id',
            'name':'name',
            'channel_url': 'channel_url', 
            'description': 'description', 
            'bio': 'bio',
            'info_outline': 'join_date', 
            'trending_up': 'total_views', 
            'person_radar': 'subscribers',
            'my_videos': 'video_count', 
            'privacy_public': 'location', 
            'links': 'links',
            'mail': 'email', 
            'phone': 'phone',
            'title_url': 'title_url',
            'url':'url',
            'record_timestamp':'updated_at'
        }
        # Tạo cột id
        silver_df['channel_id'] = silver_df['channel_url'].apply(self._extract_channel_id_from_url)

        # Ép kiểu và làm sạch các cột cơ bản
        silver_df = silver_df.rename(columns=column_mapping)
        # 1. Xử lý links
        silver_df = self._process_links_column(df=silver_df)
        
        # 2. Xử lý các định dạng số 
        silver_df['updated_at'] = silver_df['updated_at'].apply(lambda x: self.__normalize_timestamp(x))
        silver_df['join_date'] = silver_df['join_date'].apply(lambda x: self.__parse_joined_date(x))
        silver_df['total_views'] = silver_df['total_views'].apply(self.__parse_numeric_value)
        silver_df['subscribers'] = silver_df['subscribers'].apply(self.__parse_numeric_value)
        silver_df['video_count'] = silver_df['video_count'].apply(self.__parse_numeric_value)
        
        # 3. Xử lý các chuỗi văn bản
        silver_df['id'] = silver_df['id'].str.strip()
        silver_df['name'] = silver_df['name'].str.strip()
        silver_df['description'] = silver_df['description'].str.strip()
        silver_df['location'] = silver_df['location'].str.strip()
        silver_df['title_url'] = silver_df['title_url'].str.strip()
        silver_df['url'] = silver_df['url'].str.strip()

        # 4. Xoá các cột không cần thiết hoặc không mang giá trị
        silver_df.drop(columns=['email'], inplace=True)
        silver_df.drop(columns=['phone'], inplace=True)
        silver_df.drop(columns=['bio'], inplace=True)

        silver_schema = [
            'id','name','channel_id','channel_url', 'description', 'join_date', 'total_views', 'subscribers', 
            'video_count', 'location', 'title_url', 'url', 'updated_at'
        ]

        for col in silver_schema:
            if col not in silver_df.columns:
                silver_df[col] = None
        
        silver_df = silver_df[silver_schema]. \
                            dropna(subset=["join_date", "updated_at"], how="any"). \
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
    
    processor = SilverChannelsProcessor(minio_config=minio_connection_config)

    source_folder = f"{MINO_LAYER_BRONZE}/{MINIO_FOLDER_CHANNELS}"
    dest_folder   = f"{MINO_LAYER_SILVER}/{MINIO_FOLDER_CHANNELS}"

    processor.process_bronze_to_silver(
        source_bucket=MINIO_BUCKET_YTB_DATA,
        source_folder=source_folder,
        dest_bucket=MINIO_BUCKET_YTB_DATA,
        dest_folder=dest_folder
    )