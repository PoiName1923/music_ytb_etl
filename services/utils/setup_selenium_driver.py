import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager

def setup_webdriver(
    browser: str = 'chrome',
    headless: bool = False,
    window_size: tuple = (1920, 1080),
    custom_options: list = None,
    remote_url: str = None
):
    """
    Cấu hình và trả về một instance của Selenium WebDriver, hỗ trợ cả local và remote.

    Hàm này tự động quản lý việc tải và cài đặt driver cho trình duyệt khi chạy local.
    Khi remote_url được cung cấp, nó sẽ kết nối đến một Selenium Grid hoặc server từ xa.

    Args:
        browser (str): Tên trình duyệt ('chrome', 'firefox', 'edge'). Mặc định là 'chrome'.
        headless (bool): Chạy ở chế độ không giao diện (ẩn). Mặc định là False.
        window_size (tuple): Kích thước cửa sổ (width, height). Mặc định là (1920, 1080).
        custom_options (list): Danh sách các tùy chọn (arguments) khác để thêm vào trình duyệt.
        remote_url (str, optional): URL của máy chủ Selenium Remote WebDriver.
                                    Ví dụ: 'http://localhost:4444/wd/hub'.
                                    Nếu là None, driver sẽ được chạy cục bộ. Mặc định là None.

    Returns:
        Một instance của WebDriver (local hoặc remote) đã được cấu hình.

    Raises:
        ValueError: Nếu tên trình duyệt không được hỗ trợ.
    """
    browser = browser.lower()

    # 1. Thiết lập các tùy chọn (Options) chung
    common_args = [
        # --- CƠ BẢN & HIỆU SUẤT ---
        '--no-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
        '--disable-extensions',
        '--disable-infobars',
        '--log-level=3',
        f'--window-size={window_size[0]},{window_size[1]}',

        # --- TRÁNH BỊ PHÁT HIỆN LÀ BOT ---
        '--disable-blink-features=AutomationControlled',
        '--start-maximized',
        '--ignore-certificate-errors',
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',

        # --- TỐI ƯU HÓA TỐC ĐỘ ---
        '--disable-background-networking',
        '--disable-background-timer-throttling',
        '--disable-backgrounding-occluded-windows',
        '--disable-breakpad',
        '--disable-client-side-phishing-detection',
        '--disable-component-update',
        '--disable-default-apps',
        '--disable-hang-monitor',
        '--disable-ipc-flooding-protection',
        '--disable-popup-blocking',
        '--disable-prompt-on-repost',
        '--disable-renderer-backgrounding',
        '--disable-sync',
        '--metrics-recording-only',
        '--mute-audio',
        '--no-first-run',
        '--safebrowsing-disable-auto-update',
        '--enable-automation',
    ]
    if headless:
        common_args.append('--headless=new') # Sử dụng '--headless=new' cho các phiên bản Chrome mới

    if custom_options and isinstance(custom_options, list):
        common_args.extend(custom_options)

    # 2. Cấu hình options cho từng trình duyệt cụ thể
    options = None
    if browser == 'chrome':
        options = webdriver.ChromeOptions()
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
    elif browser == 'firefox':
        options = webdriver.FirefoxOptions()
    elif browser == 'edge':
        options = webdriver.EdgeOptions()
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
    else:
        raise ValueError(f"Trình duyệt '{browser}' không được hỗ trợ. Vui lòng chọn 'chrome', 'firefox', hoặc 'edge'.")

    # Thêm các arguments chung vào options
    for arg in common_args:
        options.add_argument(arg)

    # 3. Khởi tạo WebDriver (Remote hoặc Local)
    driver = None
    if remote_url:
        # Nếu remote_url được cung cấp, tạo một Remote WebDriver
        # print(f"Đang kết nối đến Remote WebDriver tại: {remote_url}")
        driver = webdriver.Remote(command_executor=remote_url, options=options)
    else:
        # Nếu không, tạo một WebDriver cục bộ
        print(f"Đang khởi tạo WebDriver cục bộ cho trình duyệt: {browser}")
        if browser == 'chrome':
            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        elif browser == 'firefox':
            service = FirefoxService(GeckoDriverManager().install())
            driver = webdriver.Firefox(service=service, options=options)
        elif browser == 'edge':
            service = EdgeService(EdgeChromiumDriverManager().install())
            driver = webdriver.Edge(service=service, options=options)

    # Giả lập để tránh bị phát hiện là bot
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    return driver