# ====================================== PATH MANAGE ====================================== 
import os
import sys
from dotenv import load_dotenv
load_dotenv()

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
# ==========================================================================================
from _selenium.scripts.crawling_trending_song import TrendingVideoYTB
from _mongo.mongo_scripts import MongoManager
import pandas as pd
from datetime import datetime, timezone
# ====================================== CONFIGURATION ======================================

MONGO_ADMIN_USER= os.getenv("MONGO_ADMIN_USER")
MONGO_ADMIN_PASSWORD=os.getenv("MONGO_ADMIN_PASSWORD")

MONGO_HOST=os.getenv("MONGO_HOST")
MONGO_PORT=os.getenv("MONGO_PORT")

MONGO_DB_TRENDING_YTB_VIDEOS=os.getenv("MONGO_DB_TRENDING_YTB_VIDEOS")
MONGO_COLL_SES_TRENDING_VIDEOS=os.getenv("MONGO_COLL_SES_TRENDING_VIDEOS")
MONGO_COLL_UNIQUE_VIDEOS=os.getenv("MONGO_COLL_UNIQUE_VIDEOS")

SELENIUM_HOST_URL=os.getenv("SELENIUM_HOST_URL")
# ==========================================================================================
# Trong đoạn code chính
if __name__=='__main__':
    with MongoManager(user=MONGO_ADMIN_USER, password=MONGO_ADMIN_PASSWORD,
                      host=MONGO_HOST, port=MONGO_PORT, db_name=MONGO_DB_TRENDING_YTB_VIDEOS) as client: 
        agent = TrendingVideoYTB(host_url=SELENIUM_HOST_URL)
        update_time = agent.get_update_time()

        # Kiểm tra thời gian update
        latest_record = client.find_latest_to_dataframe(MONGO_COLL_SES_TRENDING_VIDEOS, "scraped_at_utc")
        last_update_time = None
        if not latest_record.empty:
            last_update_time = latest_record['updated_at'].iloc[0]
            agent.logger.info(f"Thời gian cập nhật gần nhất trong DB: {last_update_time}")
        else:
            agent.logger.info("Collection rỗng, chưa có dữ liệu.")

        if update_time != last_update_time:
            agent.logger.info(f"Phát hiện dữ liệu mới (Web: {update_time}). Bắt đầu cào dữ liệu chi tiết...")
            video_list = agent.top_30_video_trending_in_day_detail()
            if video_list and update_time:
                # Chuyển video_list thành DataFrame để chèn vào MONGO_COLL_UNIQUE_VIDEOS
                video_df = pd.DataFrame(video_list)
                client.insert_dataframe_if_not_exists(MONGO_COLL_UNIQUE_VIDEOS, video_df, unique_field="url")

                # Tạo document cho MONGO_COLL_SES_TRENDING_VIDEOS
                document = {
                    "updated_at": update_time,
                    "scraped_at_utc": datetime.now(timezone.utc),
                    "source": "kworb.net/youtube/trending/vn.html",
                    "videos": video_list
                }
                client.insert_one(collection_name=MONGO_COLL_SES_TRENDING_VIDEOS, document=document)
            else:
                agent.logger.warning("Không có dữ liệu để chèn vào MongoDB.")
            agent.close_driver()
        else:
            agent.logger.info("Dữ liệu trên web không có gì mới. Bỏ qua lần quét này.")
            agent.close_driver()
        # =================================================================