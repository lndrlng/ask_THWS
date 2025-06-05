from datetime import datetime

from gridfs import GridFS
from gridfs.errors import GridFSError
from itemadapter import ItemAdapter
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from scrapy.exceptions import CloseSpider, DropItem

from .items import RawPageItem

MAX_EMBEDDED_FILE_SIZE = 15 * 1024 * 1024  # Mongo max 16mb, so 15 is safe


class MongoPipeline:
    """
    A Scrapy pipeline to store items in MongoDB.
    Handles RawPageItems:
    - 'html' type goes to a 'pages' collection.
    - 'pdf', 'ical' types:
        - Small files are stored directly in the 'files' collection.
        - Large files (content > MAX_EMBEDDED_FILE_SIZE) are stored in GridFS,
          and a reference (gridfs_id) is stored in the 'files' collection.
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
        self.fs = None

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
            self.fs = GridFS(self.db)
            spider.logger.info(
                f"[MongoPipeline] Connected to MongoDB: {self.mongo_host}, DB: {self.mongo_db_name}. GridFS initialized."  # noqa 501
            )

            self.db[self.pages_collection_name].create_index("url", unique=True)
            self.db[self.files_collection_name].create_index("url", unique=True)
            spider.logger.info("[MongoPipeline] Ensured indexes on 'url' for collections.")

        except ConnectionFailure as e:
            spider.logger.error(f"[MongoPipeline] MongoDB connection failed: {e}")
            self.client = None
            self.db = None
            self.fs = None
            raise CloseSpider("MongoDB connection failed at startup")
        except Exception as e:
            spider.logger.error(
                f"[MongoPipeline] An unexpected error occurred during MongoDB setup: {e}"
            )
            self.client = None
            self.db = None
            self.fs = None
            raise CloseSpider(f"MongoDB setup failed due to unexpected error: {e}")

    def close_spider(self, spider):
        if self.client:
            self.client.close()
            spider.logger.info("[MongoPipeline] Closed MongoDB connection.")

    def process_item(self, item, spider):
        if self.db is None or self.fs is None:
            spider.logger.error(
                "[MongoPipeline] No MongoDB connection or GridFS not initialized, dropping item."
            )
            raise DropItem(f"No MongoDB connection/GridFS for item {item.get('url')}")

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

            if "file_content" in item_dict and not item_dict.get("file_content"):
                del item_dict["file_content"]

        elif item_type in ["pdf", "ical"]:
            collection_name = self.files_collection_name
            original_file_content = item_dict.pop("file_content", None)
            item_dict.pop("gridfs_id", None)

            if "text" in item_dict and not item_dict["text"]:
                del item_dict["text"]

            if original_file_content:
                file_size = len(original_file_content)
                item_dict["file_size"] = file_size

                if file_size > MAX_EMBEDDED_FILE_SIZE:
                    spider.logger.info(
                        f"[MongoPipeline] File {url} ({file_size} bytes) is large, using GridFS."
                    )
                    try:
                        gridfs_filename = url

                        for old_file in self.fs.find({"filename": gridfs_filename}):
                            self.fs.delete(old_file._id)
                            spider.logger.debug(
                                f"[MongoPipeline] Deleted existing GridFS file version '{gridfs_filename}' (ID: {old_file._id})."  # noqa 501
                            )

                        file_metadata = {
                            "url": url,
                            "type": item_type,
                            "original_title": item_dict.get("title"),
                            "lang": item_dict.get("lang"),
                            "date_scraped_item": item_dict.get("date_scraped"),
                            "status_code_item": item_dict.get("status"),
                        }

                        gridfs_id = self.fs.put(
                            original_file_content,
                            filename=gridfs_filename,
                            metadata=file_metadata,
                        )
                        item_dict["gridfs_id"] = gridfs_id
                        spider.logger.debug(
                            f"[MongoPipeline] Stored file for {url} in GridFS with ID: {gridfs_id}, filename: '{gridfs_filename}'"  # noqa 501
                        )

                    except GridFSError as e:
                        spider.logger.error(f"[MongoPipeline] GridFS error for {url}: {e}")
                        raise DropItem(f"GridFS error for {url}: {e}")
                    except Exception as e:
                        spider.logger.error(
                            f"[MongoPipeline] Unexpected error during GridFS operation for {url}: {e}"  # noqa 501
                        )
                        raise DropItem(f"Unexpected GridFS error for {url}: {e}")
                else:
                    item_dict["file_content"] = original_file_content
                    spider.logger.debug(
                        f"[MongoPipeline] File {url} ({file_size} bytes) is small, embedding directly."  # noqa 501
                    )
            else:
                spider.logger.warning(
                    f"[MongoPipeline] No file_content for {item_type} item: {url}. Document will be upserted without file data."  # noqa 501
                )
                item_dict["file_size"] = 0

        else:
            spider.logger.warning(
                f"[MongoPipeline] Unknown item type: {item_type} for URL: {url}"
            )  # noqa 501
            return item

        if collection_name:
            try:
                self.db[collection_name].update_one(
                    {"url": url}, {"$set": item_dict}, upsert=True
                )  # noqa 501
                spider.logger.debug(
                    f"[MongoPipeline] Upserted {item_type} item: {url} into {collection_name}"
                )
            except OperationFailure as e:
                if "document too large" in str(e).lower():
                    spider.logger.error(
                        f"[MongoPipeline] MongoDB operation failed for {url} in {collection_name} - document still too large: {e}. "  # noqa 501
                        f"Item dict size: approx {len(str(item_dict))} bytes. Check MAX_EMBEDDED_FILE_SIZE."  # noqa 501
                    )
                else:
                    spider.logger.error(
                        f"[MongoPipeline] MongoDB operation failed for {url} in {collection_name}: {e}"  # noqa 501
                    )
                raise DropItem(f"MongoDB operation failed for {url}")
            except Exception as e:
                spider.logger.error(
                    f"[MongoPipeline] Unexpected error upserting item {url} for {collection_name}: {e}"  # noqa 501
                )
                raise DropItem(f"Unexpected error for {url}")
        return item
