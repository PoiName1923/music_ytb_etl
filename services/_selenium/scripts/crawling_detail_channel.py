from utils.setup_selenium_driver import setup_webdriver
from utils.setup_logger import setup_logger

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from pymongo import MongoClient, errors
from datetime import datetime, timezone

from ytmusicapi import YTMusic

# ===========================================================================
class DetailChannelYTB:
    """
    Một lớp để thu thập thông tin chi tiết từ trang 'Giới thiệu' của một kênh YouTube.
    
    Lớp này quản lý một instance của Selenium WebDriver để điều hướng, tương tác 
    và trích xuất dữ liệu. Nó được thiết kế để sử dụng như một context manager 
    (với câu lệnh 'with') để đảm bảo tài nguyên được giải phóng đúng cách.
    """
    def __init__(self,host_url):
        """
        Khởi tạo đối tượng DetailChannelYTB.
        
        - Cài đặt WebDriver của Selenium.
        - Cài đặt logger để ghi lại tiến trình và lỗi.
        - Thiết lập WebDriverWait với thời gian chờ mặc định là 10 giây.
        """
        self.driver = setup_webdriver(browser='chrome', headless=True, remote_url=host_url)
        self.logger = setup_logger(name='CrawlDetailChannel', log_folder="logs/selenium",log_filename="crawling_detail_channel.log")
        # Tăng thời gian chờ lên 10 giây để đảm bảo trang có đủ thời gian tải
        self.wait = WebDriverWait(self.driver, 10)
        self.url = None
        
    def __enter__(self):
        """Hỗ trợ context manager, cho phép sử dụng cú pháp 'with'."""
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        """Hỗ trợ context manager, đảm bảo trình duyệt được đóng khi kết thúc."""
        self.close_driver()

    def go_to_url(self, url):
        """
        Điều hướng trình duyệt đến một URL được chỉ định.
        
        Args:
            url (str): Địa chỉ URL của trang web cần truy cập.
        """
        try:
            self.url = url
            self.driver.get(url)
        except Exception as e:
            self.logger.error(f"Lỗi khi truy cập trang web {url}")

    def see_more_click(self):
        """
        Tìm và nhấp vào nút '... more' (Xem thêm) trong phần mô tả của kênh.
        
        Hành động này thường cần thiết trên giao diện di động hoặc một số giao diện
        đặc biệt để hiển thị đầy đủ thông tin.
        
        Returns:
            bool: True nếu nhấp thành công, False nếu ngược lại.
        """
        try:
            # Sử dụng aria-label để tìm nút mở rộng mô tả
            element = self.wait.until(
                EC.element_to_be_clickable((By.XPATH,'//button[contains(@aria-label, "Description")]'))
            )
            self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
            element.click()
            return True
        except (TimeoutException, NoSuchElementException) as e:
            self.logger.warning(f"Không tìm thấy hoặc không thể nhấp vào nút 'Xem thêm' || URL: {self.url}.")
            return False
        
    def extract_channel_info(self):
        """
        Trích xuất thông tin chi tiết từ trang 'Giới thiệu' của kênh.

        Hàm này sẽ thu thập các thông tin sau:
        - Tiêu đề (header_title)
        - Mô tả (description)
        - Tiểu sử (bio)
        - Các đường liên kết (links)
        - Thông tin bổ sung (ngày tham gia, lượt xem, vị trí,...)

        Returns:
            dict: Một dictionary chứa tất cả thông tin đã trích xuất. 
                  Các trường không tìm thấy sẽ có giá trị rỗng.
        """
        data = {
            "header_title": "",
            "description": "",
            "bio": "",
            "links": []
            # Các khóa khác sẽ được thêm động dựa trên icon
        }
        
        try:
            # Đợi cho container chính của trang 'Giới thiệu' được tải
            self.wait.until(EC.presence_of_element_located((By.ID, "about-container")))
            
            # 1. Trích xuất tiêu đề (thường là 'About' hoặc 'Giới thiệu')
            try:
                header_title_element = self.driver.find_element(By.XPATH, '//div[@id="header-row"]/h1')
                data["header_title"] = header_title_element.text.strip()
            except NoSuchElementException:
                # Bỏ qua nếu không tìm thấy, giữ giá trị rỗng
                pass
            
            # 2. Trích xuất mô tả kênh
            try:
                description_element = self.driver.find_element(By.XPATH, '//yt-attributed-string[@id="description-container"]/span')
                data["description"] = description_element.text.strip()
            except NoSuchElementException:
                data["description"] = ""
            
            # 3. Trích xuất tiểu sử (bio)
            try:
                bio_element = self.driver.find_element(By.XPATH, '//div[@id="bio-container"]/yt-attributed-string/span')
                data["bio"] = bio_element.text.strip()
            except NoSuchElementException:
                data["bio"] = ""
            
            # 4. Trích xuất các đường liên kết
            try:
                link_elements = self.driver.find_elements(By.XPATH, '//div[@id="link-list-container"]/yt-channel-external-link-view-model')
                links = []
                for link_element in link_elements:
                    title = link_element.find_element(By.CLASS_NAME, "ytChannelExternalLinkViewModelTitle").text.strip()
                    url = link_element.find_element(By.TAG_NAME, "a").get_attribute("href").strip()
                    links.append({"title": title, "url": url})
                data["links"] = links
            except NoSuchElementException:
                data["links"] = []
            
            # 5. Trích xuất thông tin bổ sung (bảng thống kê)
            try:
                tbody = self.driver.find_element(By.XPATH, '//tbody[@class="style-scope ytd-about-channel-renderer"]')
                rows = tbody.find_elements(By.XPATH, './/tr[@class="description-item style-scope ytd-about-channel-renderer"]')
                
                for row in rows:
                    icon_key = None
                    text_value = None
                    
                    # Lấy icon để dùng làm key cho dictionary
                    try:
                        icon_key = row.find_element(By.XPATH, './/yt-icon').get_attribute("icon")
                        data[icon_key] = None # Tạo một cột nếu có icon nhưng bị thiếu giá trị (để chỉ ra rằng các channel khác có thể có giá trị này để tạo điều kiện cho create database)
                    except NoSuchElementException:
                        continue # Bỏ qua hàng nếu không có icon

                    # Lấy text ở cột thứ 2
                    try:
                        # Lấy tất cả các cột td trong hàng
                        tds = row.find_elements(By.XPATH, './/td')
                        # Kiểm tra xem có đủ 2 cột không để tránh IndexError
                        if len(tds) > 1:
                            td_value = tds[1] 
                            text_value = td_value.text.strip()
                            # Nếu cột không có text, thử tìm thẻ <a>
                            if not text_value:
                                link_in_td = td_value.find_elements(By.TAG_NAME, "a")
                                if link_in_td:
                                    text_value = link_in_td[0].get_attribute("href") or link_in_td[0].text
                    except NoSuchElementException:
                        continue # Bỏ qua nếu cột giá trị có vấn đề

                    if icon_key and text_value:
                        # Gán giá trị vào dictionary với key là tên icon
                        data[icon_key] = text_value

            except NoSuchElementException:
                self.logger.warning(f"Không tìm thấy bảng thông tin bổ sung. || URL: {self.url}.")
            
            return data
        
        except (TimeoutException, NoSuchElementException) as e:
            self.logger.error(f"Không thể tìm thấy container chính '#about-container'. || URL: {self.url}.")
            return data # Trả về dữ liệu rỗng nếu không tìm thấy container
    
    def extract_pipeline(self, url):
        """
        Hàm dùng để gói gọn quy trình thu thập dữ liệu của môt channel
        """
        try:
            self.go_to_url(url=url)
            self.see_more_click()
            data = self.extract_channel_info()
            self.logger.info(f"Trích xuất thông tin thành công từ url: {url}")
            return data
        except Exception as e:
            self.logger.error(f"Lỗi không thể trích xuất thông tin từ url: {url}")
            
    def close_driver(self):
        """
        Đóng trình duyệt WebDriver một cách an toàn.
        """
        try:
            if self.driver:
                self.driver.quit()
        except Exception as e:
            self.logger.error("Lỗi khi đóng trình duyệt")
# ===========================================================================