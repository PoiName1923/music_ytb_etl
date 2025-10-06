import logging
import pandas as pd
import psycopg2
from psycopg2 import sql, extras, pool
from typing import Optional, List, Dict, Any, Tuple
from utils.setup_logger import setup_logger
from datetime import date

class PostgresManager:
    """
    Một class toàn diện và an toàn cho các hoạt động CRUD với PostgreSQL,
    được tối ưu hóa về hiệu suất và tích hợp với Pandas DataFrame.
    Bao gồm các tính năng: connection pooling, tham số hóa truy vấn an toàn,
    và quản lý giao dịch (transaction) tường minh.
    """

    def __init__(self, user: str, password: str, host: str, port: int, db_name: str, min_conn=1, max_conn=10):
        self.logger = setup_logger(name='PostgresManager', log_folder='logs/postgres', log_filename=str(date.today()))
        self.connection_pool = None
        self.conn = None
        self.cursor = None
        self._table_columns_cache = {}

        try:
            self.connection_pool = psycopg2.pool.SimpleConnectionPool(
                min_conn,
                max_conn,
                user=user,
                password=password,
                host=host,
                port=port,
                dbname=db_name
            )
            self.logger.info(f"Đã tạo pool kết nối cho cơ sở dữ liệu '{db_name}'")
        except psycopg2.OperationalError as e:
            self.logger.error(f"Không thể tạo pool kết nối: {e}")
            raise

    def __enter__(self):
        """Lấy một kết nối từ pool."""
        self.conn = self.connection_pool.getconn()
        self.cursor = self.conn.cursor(cursor_factory=extras.RealDictCursor)
        self.logger.info("Đã lấy một kết nối từ pool.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Xử lý khi thoát context: rollback khi có lỗi và trả kết nối về cho pool.
        """
        if exc_type:
            self.conn.rollback()
            self.logger.error(f"Đã xảy ra lỗi, đang rollback giao dịch: {exc_val}")
        
        if self.cursor:
            self.cursor.close()
        
        if self.conn:
            self.connection_pool.putconn(self.conn)
            self.logger.info("Đã trả kết nối về pool.")

    def commit(self):
        """Commit (xác nhận) giao dịch hiện tại."""
        if self.conn:
            self.conn.commit()
            self.logger.info("Giao dịch đã được commit.")

    def rollback(self):
        """Rollback (hoàn tác) giao dịch hiện tại."""
        if self.conn:
            self.conn.rollback()
            self.logger.warning("Giao dịch đã được rollback.")

    def _build_where_clause(self, conditions: Dict[str, Any]) -> Tuple[sql.SQL, List[Any]]:
        """Xây dựng mệnh đề WHERE một cách an toàn từ dictionary."""
        if not conditions:
            return sql.SQL(""), []
        
        clauses = []
        values = []
        for key, value in conditions.items():
            clauses.append(sql.SQL("{key} = %s").format(key=sql.Identifier(key)))
            values.append(value)
            
        where_sql = sql.SQL(" WHERE ") + sql.SQL(" AND ").join(clauses)
        return where_sql, values
    
    def _get_table_columns(self, table: str) -> List[str]:
        """Lấy danh sách các cột của một bảng trong cơ sở dữ liệu, có sử dụng cache."""
        if table in self._table_columns_cache:
            return self._table_columns_cache[table]
            
        query = """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position;
        """
        self.cursor.execute(query, (table,))
        columns = [row['column_name'] for row in self.cursor.fetchall()]
        self._table_columns_cache[table] = columns
        return columns

    # ============= CÁC HÀM CRUD =============

    def create(self, table: str, data: Dict[str, Any], return_columns: Optional[List[str]] = None) -> Optional[Dict]:
        """
        Chèn một bản ghi vào bảng và tùy chọn trả về một số cột (ví dụ: id).
        Args:
            table: Tên bảng.
            data: Dictionary chứa dữ liệu cần chèn {tên_cột: giá_trị}.
            return_columns: Danh sách các cột cần trả về sau khi chèn.
        Returns:
            Dictionary chứa dữ liệu của bản ghi được trả về, hoặc None.
        """
        try:
            columns = data.keys()
            values = list(data.values())
            
            query = sql.SQL("INSERT INTO {table} ({fields}) VALUES ({placeholders})").format(
                table=sql.Identifier(table),
                fields=sql.SQL(", ").join(map(sql.Identifier, columns)),
                placeholders=sql.SQL(", ").join(sql.Placeholder() * len(columns))
            )
            
            if return_columns:
                query += sql.SQL(" RETURNING {return_fields}").format(
                    return_fields=sql.SQL(", ").join(map(sql.Identifier, return_columns))
                )
            
            self.cursor.execute(query, values)
            self.logger.info(f"Đã chèn 1 bản ghi vào bảng {table}")
            
            if return_columns:
                return self.cursor.fetchone()
            return None
        except Exception as e:
            self.logger.error(f"Lỗi khi chèn dữ liệu vào bảng {table}: {e}")
            raise

    def read(self, table: str, columns: Optional[List[str]] = None,
             conditions: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> pd.DataFrame:
        """
        Đọc dữ liệu từ một bảng với các điều kiện được tham số hóa an toàn.
        Args:
            table: Tên bảng.
            columns: Danh sách các cột cần đọc. Mặc định là tất cả (*).
            conditions: Dictionary chứa các điều kiện WHERE {tên_cột: giá_trị}.
            limit: Giới hạn số lượng bản ghi trả về.
        Returns:
            DataFrame chứa các bản ghi đã đọc.
        """
        try:
            if columns is None:
                col_sql = sql.SQL("*")
            else:
                col_sql = sql.SQL(", ").join(map(sql.Identifier, columns))

            where_clause, values = self._build_where_clause(conditions or {})
            
            query = sql.SQL("SELECT {fields} FROM {table}{where}").format(
                fields=col_sql,
                table=sql.Identifier(table),
                where=where_clause
            )
            
            if limit:
                query += sql.SQL(" LIMIT %s")
                values.append(limit)

            self.cursor.execute(query, values)
            rows = self.cursor.fetchall()
            return pd.DataFrame([dict(row) for row in rows])
        except Exception as e:
            self.logger.error(f"Lỗi khi đọc dữ liệu từ bảng {table}: {e}")
            raise

    def update(self, table: str, data: Dict[str, Any], conditions: Dict[str, Any]) -> int:
        """
        Cập nhật các bản ghi dựa trên điều kiện an toàn và trả về số hàng bị ảnh hưởng.
        Args:
            table: Tên bảng.
            data: Dictionary chứa dữ liệu cần cập nhật {tên_cột: giá_trị}.
            conditions: Dictionary chứa các điều kiện WHERE.
        Returns:
            Số lượng hàng đã được cập nhật.
        """
        try:
            if not data:
                self.logger.warning("Hàm update được gọi nhưng không có dữ liệu để cập nhật.")
                return 0

            set_clause = sql.SQL(", ").join(
                sql.SQL("{key} = %s").format(key=sql.Identifier(k)) for k in data.keys()
            )
            set_values = list(data.values())

            where_clause, where_values = self._build_where_clause(conditions)
            
            if not where_values:
                error_msg = "Thao tác UPDATE phải có mệnh đề WHERE để tránh cập nhật toàn bộ bảng."
                self.logger.error(error_msg)
                raise ValueError(error_msg)

            query = sql.SQL("UPDATE {table} SET {fields}{where}").format(
                table=sql.Identifier(table),
                fields=set_clause,
                where=where_clause
            )
            
            self.cursor.execute(query, set_values + where_values)
            rowcount = self.cursor.rowcount
            self.logger.info(f"Đã cập nhật {rowcount} bản ghi trong bảng {table} với điều kiện {conditions}")
            return rowcount
        except Exception as e:
            self.logger.error(f"Lỗi khi cập nhật dữ liệu trong bảng {table}: {e}")
            raise

    def delete(self, table: str, conditions: Dict[str, Any]) -> int:
        """
        Xóa các bản ghi dựa trên điều kiện an toàn và trả về số hàng bị ảnh hưởng.
        Args:
            table: Tên bảng.
            conditions: Dictionary chứa các điều kiện WHERE.
        Returns:
            Số lượng hàng đã được xóa.
        """
        try:
            where_clause, values = self._build_where_clause(conditions)

            if not values:
                error_msg = "Thao tác DELETE phải có mệnh đề WHERE để tránh xóa toàn bộ bảng."
                self.logger.error(error_msg)
                raise ValueError(error_msg)
                
            query = sql.SQL("DELETE FROM {table}{where}").format(
                table=sql.Identifier(table),
                where=where_clause
            )
            
            self.cursor.execute(query, values)
            rowcount = self.cursor.rowcount
            self.logger.info(f"Đã xóa {rowcount} bản ghi khỏi bảng {table} với điều kiện {conditions}")
            return rowcount
        except Exception as e:
            self.logger.error(f"Lỗi khi xóa dữ liệu trong bảng {table}: {e}")
            raise

    # ============= CÁC HÀM HỮU ÍCH KHÁC =============

    def execute_query(self, query: str, params: Optional[tuple] = None) -> pd.DataFrame:
        """
        Thực thi một câu lệnh SQL thô và trả về kết quả dưới dạng DataFrame.
        Args:
            query: Câu lệnh SQL.
            params: Tham số để truyền vào câu lệnh.
        Returns:
            DataFrame chứa kết quả truy vấn.
        """
        try:
            self.cursor.execute(query, params)
            if self.cursor.description:
                rows = self.cursor.fetchall()
                return pd.DataFrame([dict(row) for row in rows])
            return pd.DataFrame()
        except Exception as e:
            self.logger.error(f"Lỗi khi thực thi câu lệnh SQL: {e}")
            raise

    def _prepare_df_for_bulk_ops(self, table: str, df: pd.DataFrame, column_mapping: Optional[Dict[str, str]]):
        """
        Hàm hỗ trợ để chuẩn bị DataFrame và xác định các cột sẽ được chèn.
        Trả về DataFrame đã được ánh xạ và danh sách các cột mục tiêu.
        """
        if df.empty:
            self.logger.warning("DataFrame rỗng. Không có dữ liệu nào được xử lý.")
            return None, None
            
        if column_mapping:
            # Sử dụng mapping được cung cấp
            df_mapped = df[list(column_mapping.keys())].rename(columns=column_mapping)
        else:
            # Tự động ánh xạ
            db_columns = self._get_table_columns(table)
            df_columns = df.columns.tolist()
            
            matched_columns = [col for col in df_columns if col in db_columns]
            df_mapped = df[matched_columns]
            
            if not matched_columns:
                self.logger.warning(f"Không có cột nào trong DataFrame khớp với bảng '{table}'. Không có dữ liệu nào được chèn.")
                return None, None
            
            ignored_columns = [col for col in df_columns if col not in db_columns]
            if ignored_columns:
                self.logger.warning(f"Các cột sau trong DataFrame không có trong bảng '{table}' và sẽ bị bỏ qua: {ignored_columns}")

        return df_mapped, df_mapped.columns.tolist()

    def bulk_insert(self, table: str, df: pd.DataFrame, column_mapping: Optional[Dict[str, str]] = None) -> int:
        """
        Chèn hàng loạt một DataFrame vào bảng một cách hiệu quả.
        Tự động ánh xạ cột nếu không có mapping được cung cấp.
        Args:
            table: Tên bảng.
            df: DataFrame để chèn.
            column_mapping: Ánh xạ {df_col: table_col}. Nếu None, sẽ cố gắng
                            chèn các cột có tên trùng khớp.
        Returns:
            Số lượng bản ghi đã được chèn.
        """
        df_mapped, cols = self._prepare_df_for_bulk_ops(table, df, column_mapping)
        if df_mapped is None:
            return 0
        
        tuples = [tuple(x) for x in df_mapped.to_numpy()]
        cols_sql = sql.SQL(",").join(map(sql.Identifier, cols))
        
        if '.' in table:
            schema, table_name = table.split('.', 1)
            table_identifier = sql.Identifier(schema, table_name)
        else:
            table_identifier = sql.Identifier(table)
            
        query = sql.SQL("INSERT INTO {table} ({columns}) VALUES %s").format(
            table=table_identifier,
            columns=cols_sql
        )
        
        # SỬA LỖI: Tạo một con trỏ chuẩn chỉ để dùng cho bulk insert
        with self.conn.cursor() as bulk_cursor:
            extras.execute_values(bulk_cursor, query, tuples)
        
        row_count = self.cursor.rowcount
        self.logger.info(f"Đã chèn hàng loạt {row_count} bản ghi vào bảng {table}")
        return row_count

    def bulk_upsert(self, table: str, df: pd.DataFrame, conflict_columns: List[str], column_mapping: Optional[Dict[str, str]] = None) -> int:
        """
        Thực hiện 'upsert' hàng loạt (INSERT ON CONFLICT UPDATE).
        Tự động ánh xạ cột nếu không có mapping được cung cấp.
        Args:
            table: Tên bảng.
            df: DataFrame để upsert.
            conflict_columns: Danh sách các cột tạo nên ràng buộc unique.
            column_mapping: Ánh xạ {df_col: table_col}. Nếu None, sẽ cố gắng
                            ánh xạ tự động.
        Returns:
            Số lượng bản ghi đã được upsert.
        """
        df_mapped, cols = self._prepare_df_for_bulk_ops(table, df, column_mapping)
        if df_mapped is None:
            return 0
        
        tuples = [tuple(x) for x in df_mapped.to_numpy()]
        update_cols = [col for col in cols if col not in conflict_columns]

        if '.' in table:
            schema, table_name = table.split('.', 1)
            table_identifier = sql.Identifier(schema, table_name)
        else:
            table_identifier = sql.Identifier(table)
            
        cols_sql = sql.SQL(",").join(map(sql.Identifier, cols))
        conflict_sql = sql.SQL(",").join(map(sql.Identifier, conflict_columns))
        update_sql = sql.SQL(",").join(
            sql.SQL("{col} = EXCLUDED.{col}").format(col=sql.Identifier(c)) for c in update_cols
        )

        query = sql.SQL("""
            INSERT INTO {table} ({cols}) 
            VALUES %s
            ON CONFLICT ({conflict_cols}) 
            DO UPDATE SET {update_clause}
        """).format(
            table=table_identifier,
            cols=cols_sql,
            conflict_cols=conflict_sql,
            update_clause=update_sql
        )
        
        with self.conn.cursor() as bulk_cursor:
            extras.execute_values(bulk_cursor, query, tuples)
        
        row_count = self.cursor.rowcount
        self.logger.info(f"Đã upsert hàng loạt {row_count} bản ghi vào bảng {table}")
        return row_count

    def bulk_insert_ignore(self, table: str, df: pd.DataFrame, conflict_columns: List[str], column_mapping: Optional[Dict[str, str]] = None) -> int:
        """
        Chèn dữ liệu từ DataFrame vào bảng Postgres và bỏ qua các bản ghi trùng
        theo conflict_columns (INSERT ON CONFLICT DO NOTHING).
        Tự động ánh xạ cột nếu không có mapping được cung cấp.
        Args:
            table: Tên bảng Postgres.
            df: DataFrame nguồn.
            conflict_columns: Danh sách các cột unique trong bảng để kiểm tra trùng lặp.
            column_mapping: Ánh xạ {df_col: table_col}. Nếu None, sẽ cố gắng
                            ánh xạ tự động.
        Returns:
            Số lượng bản ghi mới đã được chèn.
        """
        df_mapped, cols = self._prepare_df_for_bulk_ops(table, df, column_mapping)
        if df_mapped is None:
            return 0
        
        tuples = [tuple(x) for x in df_mapped.to_numpy()]
        cols_sql = sql.SQL(",").join(map(sql.Identifier, cols))
        conflict_sql = sql.SQL(",").join(map(sql.Identifier, conflict_columns))

        # SỬA LỖI: Tách tên schema và tên bảng
        if '.' in table:
            schema, table_name = table.split('.', 1)
            table_identifier = sql.Identifier(schema, table_name)
        else:
            table_identifier = sql.Identifier(table)
            
        query = sql.SQL("""
            INSERT INTO {table} ({cols})
            VALUES %s
            ON CONFLICT ({conflict_cols}) DO NOTHING
        """).format(
            table=table_identifier,
            cols=cols_sql,
            conflict_cols=conflict_sql
        )
        
        # SỬA LỖI: Tạo một con trỏ chuẩn chỉ để dùng cho bulk insert
        with self.conn.cursor() as bulk_cursor:
            extras.execute_values(bulk_cursor, query, tuples)
        
        row_count = self.cursor.rowcount
        self.logger.info(f"Đã chèn {row_count} bản ghi mới vào bảng {table} (bỏ qua trùng lặp, có mapping cột).")
        return row_count