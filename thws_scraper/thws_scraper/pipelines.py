# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface

import hashlib
import json
import uuid
from datetime import datetime

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langdetect import DetectorFactory, detect
from scrapy.exceptions import DropItem

from .items import DocumentChunkItem, RawPageItem

# make langdetect deterministic
DetectorFactory.seed = 42


class RawOutputPipeline:
    """
    Dumps every RawPageItem as one line in data_raw_<TIMESTAMP>.jsonl
    """

    def open_spider(self, spider):
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self.raw_path = f"result/data_raw_{ts}.jsonl"
        spider.logger.info(f"[RawOutput] opening {self.raw_path}")
        self.raw_file = open(self.raw_path, "w", encoding="utf-8")

    def close_spider(self, spider):
        spider.logger.info(f"[RawOutput] closing {self.raw_path}")
        self.raw_file.close()

    def process_item(self, item, spider):
        if isinstance(item, RawPageItem):
            line = json.dumps(dict(item), ensure_ascii=False)
            self.raw_file.write(line + "\n")
        return item


class ChunkingOutputPipeline:
    """
    Splits each RawPageItem into chunks, dedupes by SHA-256, writes each
    DocumentChunkItem to data_chunks_<TIMESTAMP>.jsonl, and then re-emits
    the original RawPageItem.
    """

    def __init__(self, chunk_size, chunk_overlap):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        self.seen_hashes = set()

    @classmethod
    def from_crawler(cls, crawler):
        cs = crawler.settings.getint("CHUNK_SIZE", 1000)
        co = crawler.settings.getint("CHUNK_OVERLAP", 100)
        return cls(cs, co)

    def open_spider(self, spider):
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self.chunks_path = f"result/data_chunks_{ts}.jsonl"
        spider.logger.info(f"[ChunksOutput] opening {self.chunks_path}")
        self.chunks_file = open(self.chunks_path, "w", encoding="utf-8")

    def close_spider(self, spider):
        spider.logger.info(f"[ChunksOutput] closing {self.chunks_path}")
        self.chunks_file.close()

    def process_item(self, item, spider):
        # Only handle RawPageItem
        if not isinstance(item, RawPageItem):
            return item

        text = (item.get("text") or "").strip()
        if not text:
            raise DropItem(f"Empty text - dropping {item['url']}")

        # Determine language: use item.lang if present, otherwise detect on text
        lang = item.get("lang")
        if not lang:
            try:
                lang = detect(text)
            except Exception:
                lang = "unknown"

        # Split into chunks
        chunks = self.splitter.split_text(text)
        for chunk_text in chunks:
            digest = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
            if digest in self.seen_hashes:
                continue
            self.seen_hashes.add(digest)

            chunk_item = DocumentChunkItem(
                chunk_id=str(uuid.uuid4()),
                text=chunk_text,
                source_url=item["url"],
                title=item.get("title"),
                date_updated=item.get("date_updated"),
                lang=lang,
            )

            # Write out chunk
            line = json.dumps(dict(chunk_item), ensure_ascii=False)
            self.chunks_file.write(line + "\n")

        return item
