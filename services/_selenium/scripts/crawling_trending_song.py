from utils.setup_selenium_driver import setup_webdriver
from utils.setup_logger import setup_logger

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from pymongo import MongoClient, errors
from datetime import datetime, timezone

from ytmusicapi import YTMusic

# ===========================================================================
class TrendingVideoYTB:
    """
    Lớp chịu trách nhiệm cào (scrape) dữ liệu về các video thịnh hành trên YouTube
    từ trang web kworb.net cho khu vực Việt Nam.

    Lớp này sử dụng Selenium để tự động hóa trình duyệt, truy cập trang web,
    trích xuất thông tin như tiêu đề, URL, và video ID của top 30 video,
    cũng như thời gian cập nhật của danh sách.
    """
    def __init__(self, host_url="http://selenium-hub:4444/wd/hub"):
        """
        Khởi tạo đối tượng TrendingVideoYTB.

        - Cài đặt WebDriver của Selenium để điều khiển trình duyệt.
        - Cài đặt logger để ghi lại tiến trình và các lỗi có thể xảy ra.
        - Điều hướng trình duyệt đến URL trang trending của Việt Nam.
        """
        # Khởi tạo trình duyệt Chrome tự động, có thể kết nối tới Selenium Grid
        self.driver = setup_webdriver(browser='chrome', headless=True, remote_url=host_url)
        # Thiết lập logger để ghi lại hoạt động vào file
        self.logger = setup_logger(name='CrawlTopSong', log_folder="logs/selenium",log_filename="crawling_top_song.log")
        # Thiết lập thời gian chờ tối đa 10 giây cho các element
        self.wait = WebDriverWait(self.driver, 10)

        try:
            # Điều hướng đến trang mục tiêu
            self.driver.get(url="https://kworb.net/youtube/trending/vn.html")
        except Exception as e:
            self.logger.error("Không thể kết nối đến trang đích")

    def get_update_time(self):
            """
            Lấy thời gian cập nhật của danh sách trending từ tiêu đề trang.

            Returns:
                str: Chuỗi chứa thời gian cập nhật (ví dụ: '2025-08-28 12:00 EDT').
                     Trả về None nếu có lỗi.
            """
            try:
                # Chờ element chứa tiêu đề trang xuất hiện và lấy text
                title_datetime = self.wait.until(
                    EC.presence_of_element_located((By.XPATH, ".//span[@class='pagetitle']"))
                ).text
                # Tách chuỗi để lấy phần thời gian, nằm sau dấu "|"
                datetime_str = title_datetime.split("|")[1].strip()
                return datetime_str
            except Exception as e:
                self.logger.error(f"Lỗi khi lấy thời gian cập nhật")
                return None

    def top_30_video_trending_in_day_detail(self):
        """
        Cào thông tin chi tiết của top 30 video thịnh hành trong ngày.

        Returns:
            list: Một danh sách các dictionary, mỗi dictionary chứa thông tin
                  'title', 'url', và 'video_id' của một video.
                  Trả về danh sách rỗng nếu có lỗi.
        """
        results_top_detail = []
        try:
            # Chờ tất cả các element 'a' (link) của video trong bảng trending xuất hiện
            top_30_video_trending_in_day_element = \
                self.wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".music > #trendingcountry > tbody > tr > td.text div a"))
            )
            
            # Lặp qua từng video để trích xuất thông tin
            for element in top_30_video_trending_in_day_element:
                video_url = element.get_attribute("href")
                results_top_detail.append(
                    {
                        "title" : element.get_attribute("innerHTML"),
                        "url"   : video_url,
                        # Tách video_id từ URL (phần chuỗi nằm sau 'v=')
                        "video_id": video_url.split("v=")[1]
                    }
                )
            self.logger.info(f"Tìm kiếm thành công top 30 bài hát được cập nhật vào lúc: {self.get_update_time()}")
            return results_top_detail
        except Exception as e:
            self.logger.error("Lỗi khi lấy danh sách video")
            return []
        
    def close_driver(self):
            """
            Đóng trình duyệt và giải phóng tài nguyên.
            """
            try:
                if self.driver:
                    self.driver.quit()
                    self.logger.info("Đóng trình duyệt thành công")
            except Exception as e:
                self.logger.error("Lỗi khi đóng trình duyệt")
# ===========================================================================