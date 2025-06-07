from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from scrapy.http import Response

from ..items import RawPageItem
from ..utils.lang import extract_lang_from_url


def parse_ical(response: Response, tz: ZoneInfo) -> Optional[RawPageItem]:
    """
    Create a RawPageItem for an iCalendar (.ics) file, including its raw content.
    Event parsing is REMOVED.
    """
    lang = extract_lang_from_url(response.url)

    title_str = response.url.split("/")[-1] or "Calendar Data"

    item = RawPageItem(
        url=response.url,
        type="ical",
        title=title_str,
        text="",
        file_content=response.body,
        date_scraped=datetime.now(tz).isoformat(),
        date_updated=None,
        status=response.status,
        lang=lang,
        parse_error=None,
    )
    return item
