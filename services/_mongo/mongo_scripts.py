import logging
import pandas as pd
from pymongo import MongoClient, errors
from pymongo.operations import UpdateOne
from bson.objectid import ObjectId
from typing import Optional, List, Dict, Any, Union
from utils.setup_logger import setup_logger
from datetime import datetime, date

class MongoManager:
    """
    Lớp quản lý toàn diện cho các thao tác CRUD với MongoDB, được tối ưu hóa cho hiệu suất cao
    và tích hợp sâu với Pandas DataFrame. Hỗ trợ quản lý kết nối tự động qua 'with' statement.
    """
    def __init__(self, user: str, password: str, host: str, port: int, db_name: str):
        self.client: Optional[MongoClient] = None
        self.db = None
        self.logger = setup_logger(name='MongoManager',log_folder='logs/mongo',log_filename=str(date.today()))
        
        uri = f"mongodb://{user}:{password}@{host}:{port}/"
        try:
            self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            self.client.admin.command('ping')
            self.db = self.client[db_name]
            self.logger.info(f"Kết nối thành công đến MongoDB, database: '{db_name}'")
        except errors.ConnectionFailure as e:
            self.logger.error(f"Không thể kết nối đến MongoDB: {e}")
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        if self.client:
            self.client.close()
            self.logger.info("Đã đóng kết nối MongoDB.")

    def insert_dataframe(self, collection_name: str, dataframe: pd.DataFrame) -> Optional[List[ObjectId]]:
        """Chèn toàn bộ DataFrame vào collection mà không kiểm tra trùng lặp."""
        if not isinstance(dataframe, pd.DataFrame):
            raise TypeError("Tham số 'dataframe' phải là một pandas DataFrame.")
        if dataframe.empty:
            self.logger.info("DataFrame rỗng, không có gì để chèn.")
            return []
        
        documents = dataframe.to_dict('records')
        return self.insert_many(collection_name, documents)

    def insert_dataframe_if_not_exists(self, collection_name: str, dataframe: pd.DataFrame, unique_field: str = "url") -> Optional[int]:
        """
        Chèn các document từ DataFrame nếu chúng chưa tồn tại, dựa trên một trường duy nhất.
        Sử dụng 'upsert' để đạt hiệu suất tối đa bằng cách giảm thiểu các truy vấn mạng.

        Args:
            collection_name: Tên collection.
            dataframe: DataFrame chứa dữ liệu cần chèn.
            unique_field: Tên trường dùng để kiểm tra trùng lặp.

        Returns:
            Số lượng document MỚI được chèn. Trả về None nếu có lỗi.
        """
        try:
            if not isinstance(dataframe, pd.DataFrame): raise TypeError("Tham số 'dataframe' phải là pandas DataFrame.")
            if dataframe.empty: return 0
            if unique_field not in dataframe.columns: raise ValueError(f"Trường duy nhất '{unique_field}' không tồn tại trong DataFrame.")

            collection = self.db[collection_name]
            operations = [
                UpdateOne(
                    {unique_field: row[unique_field]},
                    {"$setOnInsert": row},
                    upsert=True
                )
                for row in dataframe.to_dict('records') if row.get(unique_field) is not None
            ]

            if not operations: return 0

            result = collection.bulk_write(operations, ordered=False)
            upserted_count = result.upserted_count
            self.logger.info(f"Đã xử lý {len(operations)} document. Chèn mới: {upserted_count} document vào '{collection_name}'.")
            return upserted_count
            
        except errors.BulkWriteError as bwe:
            self.logger.error(f"Lỗi BulkWriteError khi upsert DataFrame: {bwe.details}")
            return None
        except Exception as e:
            self.logger.error(f"Lỗi khi upsert DataFrame: {e}")
            return None
        
    def find_latest_to_dataframe(self, collection_name: str, sort_field: str) -> pd.DataFrame:
        """
        Tìm document gần đây nhất trong collection dựa trên một trường và trả về dưới dạng DataFrame.
        """
        try:
            latest_doc = self.find_latest_one(collection_name, sort_field)
            if latest_doc:
                df = pd.DataFrame([latest_doc])
                if '_id' in df.columns:
                    df['_id'] = df['_id'].astype(str)
                self.logger.info(f"Truy xuất thành công document mới nhất từ '{collection_name}' thành DataFrame.")
                return df
            else:
                # Trả về DataFrame rỗng nếu không tìm thấy document nào
                return pd.DataFrame()
        except Exception as e:
            self.logger.error(f"Lỗi khi truy xuất document mới nhất thành DataFrame: {e}")
            return pd.DataFrame()
        
    def find_to_dataframe(self, collection_name: str, query: Dict[str, Any] = {}, projection: Optional[Dict[str, Any]] = None, limit: int = 0) -> pd.DataFrame:
        """Tìm nhiều document và trả về dưới dạng pandas DataFrame."""
        try:
            documents = list(self.find(collection_name, query, projection, limit))
            if not documents: return pd.DataFrame()
                
            df = pd.DataFrame(documents)
            if '_id' in df.columns: df['_id'] = df['_id'].astype(str)
            self.logger.info(f"Truy xuất thành công {len(df)} document từ '{collection_name}' thành DataFrame.")
            return df
        except Exception as e:
            self.logger.error(f"Lỗi khi truy xuất document thành DataFrame: {e}")
            return pd.DataFrame()

    def insert_one(self, collection_name: str, document: Dict[str, Any]) -> Optional[ObjectId]:
        """Chèn một document vào collection."""
        try:
            result = self.db[collection_name].insert_one(document)
            self.logger.info(f"Đã chèn 1 document vào '{collection_name}' với _id: {result.inserted_id}")
            return result.inserted_id
        except Exception as e:
            self.logger.error(f"Lỗi khi chèn document: {e}")
            return None

    def insert_many(self, collection_name: str, documents: List[Dict[str, Any]]) -> Optional[List[ObjectId]]:
        """Chèn một danh sách các document vào collection."""
        if not documents: return []
        try:
            result = self.db[collection_name].insert_many(documents, ordered=False)
            self.logger.info(f"Đã chèn {len(result.inserted_ids)} document vào '{collection_name}'.")
            return result.inserted_ids
        except errors.BulkWriteError as bwe:
            self.logger.warning(f"Lỗi BulkWrite: Đã chèn thành công {bwe.details['nInserted']}. Chi tiết: {bwe.details['writeErrors']}")
            return None
        except Exception as e:
            self.logger.error(f"Lỗi khi chèn nhiều document: {e}")
            return None

    def insert_if_not_exists(self, collection_name: str, document: Dict[str, Any], unique_field: str = "url") -> Optional[ObjectId]:
        """Chèn document nếu chưa tồn tại (phiên bản tối ưu cho một document)."""
        try:
            unique_value = document.get(unique_field)
            if unique_value is None:
                self.logger.warning(f"Document không có trường unique '{unique_field}', bỏ qua.")
                return None

            result = self.db[collection_name].update_one(
                {unique_field: unique_value},
                {"$setOnInsert": document},
                upsert=True
            )
            if result.upserted_id:
                self.logger.info(f"Đã chèn document mới với _id: {result.upserted_id}")
                return result.upserted_id
            else:
                self.logger.info(f"Document với {unique_field}='{unique_value}' đã tồn tại.")
                return None
        except Exception as e:
            self.logger.error(f"Lỗi khi upsert document: {e}")
            return None
            
    def find_latest_one(self, collection_name: str, sort_field: str) -> Optional[Dict[str, Any]]:
        """Tìm document gần đây nhất trong collection dựa trên một trường."""
        try:
            return self.db[collection_name].find_one(sort=[(sort_field, -1)])
        except Exception as e:
            self.logger.error(f"Lỗi khi tìm document mới nhất: {e}")
            return None

    def find(self, collection_name: str, query: Dict[str, Any] = {}, projection: Optional[Dict[str, Any]] = None, limit: int = 0) -> List[Dict[str, Any]]:
        """Tìm nhiều document."""
        try:
            cursor = self.db[collection_name].find(query, projection)
            if limit > 0: cursor = cursor.limit(limit)
            return list(cursor)
        except Exception as e:
            self.logger.error(f"Lỗi khi tìm nhiều document: {e}")
            return []

    # Các hàm khác (find_one, delete_one, etc.) có thể giữ nguyên và thêm Type Hints nếu cần.