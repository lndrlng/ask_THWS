from datetime import datetime

from itemadapter import ItemAdapter
from langdetect import DetectorFactory, detect
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from scrapy.exceptions import CloseSpider, DropItem

from .items import RawPageItem

DetectorFactory.seed = 42


class MongoPipeline:
    """
    A Scrapy pipeline to store items in MongoDB.
    Handles RawPageItems:
    - 'html' type goes to a 'pages' collection.
    - 'pdf', 'ical' types go to a 'files' collection with their binary content.
    """

    def __init__(
        self,
        mongo_host,
        mongo_port,
        mongo_db_name,
        mongo_user,
        mongo_pass,
        pages_collection_name,
        files_collection_name,
    ):
        self.mongo_host = mongo_host
        self.mongo_port = int(mongo_port)
        self.mongo_db_name = mongo_db_name
        self.mongo_user = mongo_user
        self.mongo_pass = mongo_pass
        self.pages_collection_name = pages_collection_name
        self.files_collection_name = files_collection_name

        self.client = None
        self.db = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            mongo_host=crawler.settings.get("MONGO_HOST"),
            mongo_port=crawler.settings.get("MONGO_PORT"),
            mongo_db_name=crawler.settings.get("MONGO_DB_NAME"),
            mongo_user=crawler.settings.get("MONGO_USER"),
            mongo_pass=crawler.settings.get("MONGO_PASS"),
            pages_collection_name=crawler.settings.get("MONGO_PAGES_COLLECTION", "pages"),
            files_collection_name=crawler.settings.get("MONGO_FILES_COLLECTION", "files"),
        )

    def open_spider(self, spider):
        try:
            if self.mongo_user and self.mongo_pass:
                uri = f"mongodb://{self.mongo_user}:{self.mongo_pass}@{self.mongo_host}:{self.mongo_port}/{self.mongo_db_name}?authSource=admin"  # noqa 501
            else:
                uri = f"mongodb://{self.mongo_host}:{self.mongo_port}/"

            self.client = MongoClient(uri)
            self.client.admin.command("ping")
            self.db = self.client[self.mongo_db_name]
            spider.logger.info(
                f"[MongoPipeline] Connected to MongoDB: {self.mongo_host}, DB: {self.mongo_db_name}"
            )

            self.db[self.pages_collection_name].create_index("url", unique=True)
            self.db[self.files_collection_name].create_index("url", unique=True)
            spider.logger.info("[MongoPipeline] Ensured indexes on 'url' for collections.")

        except ConnectionFailure as e:
            spider.logger.error(f"[MongoPipeline] MongoDB connection failed: {e}")
            raise CloseSpider("MongoDB connection failed at startup")
            self.client = None
            self.db = None

    def close_spider(self, spider):
        if self.client:
            self.client.close()
            spider.logger.info("[MongoPipeline] Closed MongoDB connection.")

    def process_item(self, item, spider):
        if self.db is not None:
            spider.logger.error("[MongoPipeline] No MongoDB connection, dropping item.")
            raise DropItem(f"No MongoDB connection for item {item.get('url')}")

        if not isinstance(item, RawPageItem):
            return item

        adapter = ItemAdapter(item)
        item_type = adapter.get("type")
        url = adapter.get("url")

        item_dict = {}
        for key, value in adapter.asdict().items():
            if value is not None:
                if isinstance(value, datetime):
                    item_dict[key] = value.isoformat()
                else:
                    item_dict[key] = value

        if "text" in item_dict and isinstance(item_dict["text"], str):
            item_dict["text"] = item_dict["text"].replace("\x00", "")
        if "title" in item_dict and isinstance(item_dict["title"], str):
            item_dict["title"] = item_dict["title"].replace("\x00", "")

        collection_name = None
        if item_type == "html":
            collection_name = self.pages_collection_name
            if not item_dict.get("lang") and item_dict.get("text"):
                try:
                    from bs4 import BeautifulSoup

                    html_for_lang_detect = item_dict.get("text", "")
                    soup_for_lang_detect = BeautifulSoup(html_for_lang_detect, "lxml")
                    plain_text_for_lang_detect = soup_for_lang_detect.get_text(" ", strip=True)
                    if plain_text_for_lang_detect:
                        item_dict["lang"] = detect(plain_text_for_lang_detect)
                    else:
                        item_dict["lang"] = "unknown"
                except Exception as e:
                    spider.logger.warning(f"Language detection failed for {url}: {e}")
                    item_dict["lang"] = "unknown"
            if "file_content" in item_dict and not item_dict["file_content"]:
                del item_dict["file_content"]

        elif item_type in ["pdf", "ical"]:
            collection_name = self.files_collection_name
            if "text" in item_dict and not item_dict["text"]:
                del item_dict["text"]
            if not item_dict.get("file_content"):
                spider.logger.warning(
                    f"[MongoPipeline] No file_content for {item_type}: {url}. Skipping DB insert."
                )
                return item

        else:
            spider.logger.warning(f"[MongoPipeline] Unknown item type: {item_type} for URL: {url}")
            return item

        if collection_name:
            try:
                self.db[collection_name].update_one({"url": url}, {"$set": item_dict}, upsert=True)
                spider.logger.debug(
                    f"[MongoPipeline] Upserted {item_type} item: {url} into {collection_name}"
                )
            except OperationFailure as e:
                spider.logger.error(
                    f"[MongoPipeline] MongoDB operation failed for {url} in {collection_name}: {e}"
                )
                raise DropItem(f"MongoDB operation failed for {url}")
            except Exception as e:
                spider.logger.error(
                    f"[MongoPipeline] Unexpected error processing item {url} for {collection_name}: {e}"  # noqa 501
                )
                raise DropItem(f"Unexpected error for {url}")
        return item
