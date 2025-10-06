import io
import json
import logging
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from minio import Minio
from minio.error import S3Error
from bson import json_util
from typing import Optional, List
from utils.setup_logger import setup_logger
from datetime import datetime, date

class MinioClient:
    """
    Lớp quản lý các thao tác với MinIO, được tối ưu hóa cho việc xử lý dữ liệu lớn
    với định dạng Parquet và tích hợp với Pandas.
    """
    def __init__(self, host: str, port: str, access_key: str, secret_key: str, secure: bool = False):
        self.logger = setup_logger(name='MinioManager',log_folder='logs/minio',log_filename=str(date.today()))
        endpoint = f"{host}:{port}"
        try:
            self.client = Minio(
                endpoint=endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=secure
            )
            self.logger.info(f"Kết nối thành công đến MinIO tại {endpoint}")
        except S3Error as e:
            self.logger.error(f"Không thể kết nối đến MinIO: {e}")
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.info("Thoát khỏi context của MinioClient.")

    def create_bucket(self, bucket_name: str) -> bool:
        """Tạo bucket nếu chưa tồn tại."""
        try:
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)
                self.logger.info(f"Bucket '{bucket_name}' đã được tạo.")
            return True
        except S3Error as e:
            self.logger.error(f"Lỗi khi tạo bucket '{bucket_name}': {e}")
            return False
            
    def list_files(self, bucket_name: str, prefix: str = "", suffix: str = "") -> List[str]:
        """Liệt kê danh sách tên các file trong bucket với prefix và suffix tùy chọn."""
        try:
            objects = self.client.list_objects(bucket_name, prefix=prefix, recursive=True)
            files = [obj.object_name for obj in objects if obj.object_name.endswith(suffix)]
            return files
        except S3Error as e:
            self.logger.error(f"Lỗi khi liệt kê file từ '{bucket_name}/{prefix}': {e}")
            return []

    def upload_parquet(self, bucket_name: str, object_name: str, dataframe: pd.DataFrame) -> None:
        """
        Upload một DataFrame dưới dạng file Parquet vào một đường dẫn cụ thể trong MinIO.
        """
        try:
            if not isinstance(dataframe, pd.DataFrame): raise TypeError("Tham số 'dataframe' phải là pandas DataFrame.")
            if dataframe.empty:
                self.logger.warning("DataFrame rỗng, bỏ qua upload.")
                return
            if not object_name: raise ValueError("Tham số 'object_name' không được để trống.")

            self.create_bucket(bucket_name)
            df_copy = dataframe.copy()

            if '_id' in df_copy.columns: df_copy.drop(columns=['_id'], inplace=True)
            
            for col in df_copy.columns:
                if any(isinstance(val, (dict, list)) for val in df_copy[col].dropna()):
                    df_copy[col] = df_copy[col].apply(
                        lambda x: json.dumps(x, default=json_util.default, ensure_ascii=False) if x else None
                    )

            table = pa.Table.from_pandas(df_copy, preserve_index=False)
            buffer = io.BytesIO()
            pq.write_table(table, buffer)
            buffer.seek(0)

            self.client.put_object(
                bucket_name=bucket_name,
                object_name=object_name,
                data=buffer,
                length=buffer.getbuffer().nbytes,
                content_type="application/octet-stream"
            )
            self.logger.info(f"Upload thành công DataFrame vào '{bucket_name}/{object_name}'")

        except S3Error as e:
            self.logger.error(f"Lỗi S3 khi upload Parquet '{object_name}': {e}")
        except Exception as e:
            self.logger.error(f"Lỗi không xác định khi upload Parquet '{object_name}': {e}")

    def read_parquet(self, bucket_name: str, object_name: str) -> pd.DataFrame:
        """Đọc một file Parquet từ MinIO và trả về DataFrame."""
        response = None
        try:
            response = self.client.get_object(bucket_name, object_name)
            buffer = io.BytesIO(response.read())
            return pd.read_parquet(buffer)
        except S3Error as e:
            if e.code == "NoSuchKey": self.logger.warning(f"File Parquet '{object_name}' không tồn tại.")
            else: self.logger.error(f"Lỗi S3 khi đọc Parquet '{object_name}': {e}")
            return pd.DataFrame()
        except Exception as e:
            self.logger.error(f"Lỗi không xác định khi đọc Parquet '{object_name}': {e}")
            return pd.DataFrame()
        finally:
            if response:
                response.close()
                response.release_conn()
                
    def read_folder_parquet(self, bucket_name: str, prefix: str) -> pd.DataFrame:
        """
        Đọc toàn bộ file Parquet trong một folder (prefix) từ MinIO và trả về DataFrame hợp nhất.
        
        Args:
            bucket_name (str): Tên bucket.
            prefix (str): Thư mục (prefix) trong bucket.

        Returns:
            pd.DataFrame: DataFrame chứa toàn bộ dữ liệu đã gộp.
        """
        try:
            # Liệt kê toàn bộ file .parquet trong folder
            files = self.list_files(bucket_name, prefix=prefix, suffix=".parquet")
            if not files:
                self.logger.warning(f"Không tìm thấy file Parquet nào trong '{bucket_name}/{prefix}'")
                return pd.DataFrame()

            df_list = []
            for file in files:
                df = self.read_parquet(bucket_name, file)
                if not df.empty:
                    df_list.append(df)

            if df_list:
                result = pd.concat(df_list, ignore_index=True)
                self.logger.info(f"Đã đọc thành công {len(files)} file từ '{bucket_name}/{prefix}'")
                return result
            else:
                self.logger.warning(f"Tất cả file trong '{bucket_name}/{prefix}' đều rỗng.")
                return pd.DataFrame()

        except Exception as e:
            self.logger.error(f"Lỗi khi đọc folder '{bucket_name}/{prefix}': {e}")
            return pd.DataFrame()
