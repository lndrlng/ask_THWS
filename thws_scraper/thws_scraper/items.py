# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class RawPageItem(scrapy.Item):
    """The full text + metadata for one fetched page or file."""

    url = scrapy.Field()
    type = scrapy.Field()  # "html" | "pdf" | "ical"
    title = scrapy.Field()
    text = scrapy.Field()  # Main text for HTML, potentially empty for PDF/iCal

    # file_content: New field for raw file content (PDF, iCal)
    file_content = scrapy.Field()  # bytes

    date_scraped = scrapy.Field()
    date_updated = scrapy.Field()
    status = scrapy.Field()
    lang = scrapy.Field()
    parse_error = scrapy.Field()

    gridfs_id = scrapy.Field()
    file_size = scrapy.Field()

    metadata_extracted = scrapy.Field()
