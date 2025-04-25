import csv
import logging
import re
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urljoin, urlparse

from itemadapter import ItemAdapter
from rich.console import Console
from rich.live import Live
from scrapy import signals
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule

from ..parsers.html_parser import parse_html
from ..parsers.ical_parser import parse_ical
from ..parsers.pdf_parser import parse_pdf
from ..utils.stats import StatsReporter


class ThwsSpider(CrawlSpider):
    name = "thws"
    allowed_domains = ["thws.de"]
    start_urls = ["https://www.thws.de/", "https://fiw.thws.de/"]
    # follow links in the text to icals and pdf too
    rules = [
        Rule(
            LinkExtractor(
                allow_domains=allowed_domains,
                allow=[r"\.pdf$", r"\.ics$", r"/"],
            ),
            callback="parse_item",
            follow=True,
        )
    ]

    @classmethod
    def from_crawler(cls, crawler):
        spider = cls(settings=crawler.settings)
        spider.crawler = crawler
        crawler.signals.connect(spider.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(spider.spider_closed, signal=signals.spider_closed)
        return spider

    def __init__(self, *args, settings=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.settings = settings

        self.container_mode = self.settings.getbool("CONTAINER_MODE", False)

        # stats & reporting
        self.reporter = StatsReporter()
        self.start_time = datetime.utcnow()

        self._follow_links = True
        if not self.container_mode:
            # live rich table
            self.console = Console(
                height=self.settings.getint("RICH_HEIGHT", 200), record=True
            )
            self.live = Live(
                self.reporter.get_table(self.start_time),
                console=self.console,
                refresh_per_second=4,
            )
        else:
            self.console = None
            self.live = None

    def spider_opened(self):
        if self.live:
            self.live.__enter__()

            log_file_level_str = self.settings.get("LOG_FILE_LEVEL", "WARNING").upper()
            log_file_level = getattr(logging, log_file_level_str, logging.WARNING)

            # extra file handler just for the logfile
            Path("result").mkdir(parents=True, exist_ok=True)
            fh = RotatingFileHandler(
                "result/thws_warnings.log",
                maxBytes=10_000_000,
                backupCount=3,
                encoding="utf-8",
            )
            fh.setLevel(log_file_level)
            fh.setFormatter(
                logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
            )
            logging.getLogger().addHandler(fh)

    def spider_closed(self, reason):
        """
        Called when the spider is closed.  Stops the live table display,
        then converts the final stats table to a csv file.
        """
        if self.live:
            self.live.__exit__(None, None, None)

        ts = self.start_time.strftime("%Y%m%d_%H%M%S")
        csv_path = f"result/stats_{ts}.csv"

        # Extract the internal table data
        table = self.reporter.get_table(self.start_time)

        # Table has rows like: [domain, html, pdf, ical, errors, skipped, bytes]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "Subdomain",
                    "Html",
                    "Pdf",
                    "Ical",
                    "Errors",
                    "Empty",
                    "Bytes",
                    "Ignored",
                ]
            )
            for row in table.rows:
                writer.writerow([cell.plain for cell in row.cells])

        self.logger.info(f"Wrote stats table to {csv_path}")
        self.logger.info(f"Spider closed: {reason}")

    def parse_item(self, response):
        """
        Dispatch to the correct parser (HTML, PDF, iCal), and yield parsed items.
        Also extracts .pdf and .ics links from raw body and follows them.
        """
        domain = urlparse(response.url).netloc
        self.reporter.bump("bytes", domain, len(response.body))
        ctype = response.headers.get("Content-Type", b"").decode().split(";")[0].lower()
        url_lower = response.url.lower()

        # Skip unwanted file types
        ignored_exts = [".seb"]  # online exam format
        if any(url_lower.endswith(ext) for ext in ignored_exts):
            self.logger.debug(f"Ignored filetype: {response.url}")
            self.reporter.bump("ignored", domain)
            return

        # Choose parser
        if url_lower.endswith(".pdf") or "pdf" in ctype:
            items = parse_pdf(response)
        elif url_lower.endswith(".ics") or ctype in (
            "text/calendar",
            "application/ical",
        ):
            items = parse_ical(response)
        else:
            items = parse_html(response)

        if not items:
            self.reporter.bump("empty", domain)
        else:
            for item in items if isinstance(items, list) else [items]:
                adapter = ItemAdapter(item)
                item_type = adapter.get("type", "unknown")
                self.reporter.bump(item_type, domain)
                self.reporter.bump("total")
                yield item

        # Extract and follow embedded .pdf and .ics links
        body_text = response.text
        embedded_links = re.findall(
            r'href=["\'](.*?\.(?:pdf|ics))["\']', body_text, re.IGNORECASE
        )

        for href in embedded_links:
            abs_url = urljoin(response.url, href)
            parsed = urlparse(abs_url)

            # Skip if scheme isn't http/https
            if parsed.scheme not in ("http", "https"):
                continue

            yield response.follow(abs_url, callback=self.parse_item)

        if self.live:
            self.live.update(self.reporter.get_table(self.start_time))
