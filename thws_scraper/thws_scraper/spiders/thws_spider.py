from datetime import datetime
from urllib.parse import urlparse

import scrapy
from rich.console import Console
from rich.live import Live
from scrapy import signals
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule
from scrapy.utils.defer import defer_to_thread

from ..parsers.html_parser import parse_html
from ..parsers.ical_parser import parse_ical
from ..parsers.pdf_parser import parse_pdf
from ..utils.stats import StatsReporter


class ThwsSpider(CrawlSpider):
    name = "thws"
    allowed_domains = ["thws.de"]
    start_urls = ["https://www.thws.de/", "https://fiw.thws.de/"]
    rules = [
        Rule(
            LinkExtractor(allow_domains=allowed_domains),
            callback="parse_item",
            follow=True,
        )
    ]

    @classmethod
    def from_crawler(cls, crawler):
        spider = super().from_crawler(crawler)
        crawler.signals.connect(spider.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(spider.spider_closed, signal=signals.spider_closed)
        return spider

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # stats & reporting
        self.reporter = StatsReporter()
        self.start_time = datetime.utcnow()
        # live table
        self.console = Console(height=self.settings.getint("RICH_HEIGHT", 200))
        self.live = Live(
            self.reporter.get_table(), console=self.console, refresh_per_second=4
        )

    def spider_opened(self):
        self.live.__enter__()

    def spider_closed(self, reason):
        """
        Called when the spider is closed.  Stops the live table display,
        then writes out the final stats table to a timestamped text file.
        """
        # stop live-render
        self.live.__exit__(None, None, None)

        # export the recorded table
        ts = self.start_time.strftime("%Y%m%d_%H%M%S")
        path = f"stats_{ts}.txt"

        # re-print the final table into the console's record buffer
        self.console.print(self.reporter.get_table(self.start_time))

        # write out the recorded text
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.console.export_text())

        self.logger.info(f"Wrote stats table to {path}")
        self.logger.info(f"Spider closed: {reason}")

    def parse_item(self, response) -> scrapy.Request:
        """
        Dispatch to the right parser in a thread if needed.
        """
        domain = urlparse(response.url).netloc
        self.reporter.bump("bytes", domain, len(response.body))
        ctype = response.headers.get("Content-Type", b"").decode().split(";")[0].lower()

        # PDF
        if response.url.lower().endswith(".pdf") or "pdf" in ctype:
            d = defer_to_thread(parse_pdf, response)
            d.addBoth(lambda items: self._handle_result(items, domain))
            return d

        # iCal
        if ctype in ("text/calendar", "application/ical"):
            items = parse_ical(response)
            return self._handle_result(items, domain)

        # HTML
        items = parse_html(response)
        return self._handle_result(items, domain)

    def _handle_result(self, items, domain):
        """
        Common: bump stats, update table, yield items.
        """
        if not items:
            self.reporter.bump("skipped_empty", domain)
        else:
            for it in items if isinstance(items, list) else [items]:
                self.reporter.bump(it["type"], domain)
                self.reporter.bump("total")
                yield it
        self.live.update(self.reporter.get_table())
