import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logger(
    name: str = 'my_project',
    log_level: int = logging.INFO,
    log_folder: str = 'logs',
    log_filename: str = 'app.log',
    max_bytes: int = 10*1024*1024, # 10 MB
    backup_count: int = 2
) -> logging.Logger:
    """
    Cấu hình và trả về một logger tùy chỉnh.

    Logger này sẽ ghi log ra cả console và file, với tính năng
    tự động xoay vòng file log khi đạt đến kích thước tối đa.

    Args:
        name (str): Tên của logger.
        log_level (int): Mức độ log (ví dụ: logging.DEBUG, logging.INFO).
        log_folder (str): Thư mục để lưu file log.
        log_filename (str): Tên của file log.
        max_bytes (int): Kích thước tối đa của mỗi file log trước khi xoay vòng.
        backup_count (int): Số lượng file log backup cần giữ lại.

    Returns:
        logging.Logger: Một instance của logger đã được cấu hình.
    """
    # Lấy logger theo tên
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # Tránh việc thêm handler nhiều lần nếu hàm này được gọi lại
    if logger.hasHandlers():
        logger.handlers.clear()

    # Tạo thư mục logs nếu chưa tồn tại
    os.makedirs(log_folder, exist_ok=True)

    # 1. Định dạng cho log message
    log_format = logging.Formatter(
        '%(asctime)s - %(name)s - [%(levelname)s] - %(message)s (%(filename)s:%(lineno)d)'
    )

    # 2. Cấu hình Console Handler (để in ra màn hình)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    # 3. Cấu hình File Handler (để ghi vào file)
    # Sử dụng RotatingFileHandler để file log không bị quá lớn
    log_file_path = os.path.join(log_folder, log_filename)
    file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)

    return logger
