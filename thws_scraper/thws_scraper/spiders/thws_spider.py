import io
import unicodedata
from datetime import datetime
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

import fitz
import scrapy
from bs4 import BeautifulSoup
from readability import Document
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule
from icalendar import Calendar
from rich.console import Console
from rich.table import Table
from rich.live import Live
from collections import defaultdict


class ThwsSpider(CrawlSpider):
    """
    Spider to crawl and scrape content from THWS websites, including PDF, HTML, and iCal data.
    """

    name = "thws"
    allowed_domains = ["thws.de"]
    start_urls = ["https://www.thws.de/", "https://fiw.thws.de/"]
    rules = [
        Rule(
            LinkExtractor(allow_domains=allowed_domains),
            callback="parse_item",
            follow=True,
        ),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stats = {
            "html": 0,
            "pdf": 0,
            "ical": 0,
            "total": 0,
            "errors": 0,
            "bytes": 0,
            "skipped_empty": 0,
        }
        self.subdomain_stats = defaultdict(
            lambda: {
                "html": 0,
                "pdf": 0,
                "ical": 0,
                "errors": 0,
                "bytes": 0,
                "skipped_empty": 0,
            }
        )
        self.start_time = datetime.utcnow()
        self.executor = ThreadPoolExecutor(max_workers=4)

        # Build initial table and Live context with an artificially large height to prevent cropping
        self.table = self._create_rich_table()
        self.console = Console(height=200)
        self.live = Live(self.table, console=self.console, refresh_per_second=4)
        self.live.__enter__()

    def start_requests(self):
        """
        Override CrawlSpider.start_requests so every Request
        gets our custom errback attached.
        """
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                callback=self.parse_item,
                errback=self._handle_failure,
                dont_filter=True,
            )

    def _handle_failure(self, failure):
        """
        Called when any Request errors out (DNS, timeout, etc).
        We catch DNSLookupError, log a warning, increment a stat,
        and swallow the failure so the crawl continues.
        """
        req = failure.request
        if failure.check(DNSLookupError):
            self.logger.warning(f"[DNS] Could not resolve {req.url}")
            self.stats["dns_errors"] = self.stats.get("dns_errors", 0) + 1
            self.subdomain_stats[urlparse(req.url).netloc]["errors"] += 1
        else:
            self.logger.error(f"[ERR] {req.url} failed: {failure.value!r}")
            self.stats["errors"] += 1
            self.subdomain_stats[urlparse(req.url).netloc]["errors"] += 1
        # no re-raise → Scrapy will drop this request and move on

    def parse_item(self, response):
        """
        Dispatch parsing based on content-type.
        """
        url = response.url
        domain = urlparse(url).netloc
        status = response.status
        ctype = response.headers.get("Content-Type", b"").decode().split(";")[0].lower()
        content_size = len(response.body)

        # Update bytes downloaded stats
        self.stats["bytes"] += content_size
        self.subdomain_stats[domain]["bytes"] += content_size

        if status == 404:
            return

        try:
            if (
                url.lower().endswith(".pdf")
                or "pdf" in ctype
                or ctype == "application/octet-stream"
            ):
                future = self.executor.submit(
                    self.parse_pdf, response, url, domain, status
                )
                yield from future.result()
            elif ctype in ("text/calendar", "text/vcard", "application/ical"):
                yield from self.parse_ical(response, url, domain, status)
            else:
                yield from self.parse_html(response, url, domain, status)
        except Exception as e:
            self.logger.warning(f"Error parsing {url}: {e}")
            self.stats["errors"] += 1
            self.subdomain_stats[domain]["errors"] += 1
            self.update_rich_table()

    def parse_html(self, response, url, domain, status):
        """
        Extract main text from HTML using readability and BeautifulSoup.
        """
        # Extract via Readability
        doc = Document(response.text)
        soup = BeautifulSoup(doc.summary(), "lxml")
        text = self.clean_text(soup.get_text())

        # Skip empty HTML pages
        if not text:
            self.stats["skipped_empty"] += 1
            self.subdomain_stats[domain]["skipped_empty"] += 1
            self.logger.info(f"⏭ Skipping empty HTML page: {url}")
            self.update_rich_table()
            return

        if "404" in text.lower() or "not found" in text.lower():
            return

        title_el = soup.select_one("h1")
        title = (
            title_el.get_text(strip=True)
            if title_el
            else response.css("title::text").get("").strip()
        )
        date_updated = self.extract_date(response)

        # Update stats
        self.stats["html"] += 1
        self.subdomain_stats[domain]["html"] += 1
        self.stats["total"] += 1
        self.update_rich_table()

        yield {
            "url": url,
            "type": "html",
            "title": title,
            "text": text,
            "date_scraped": datetime.utcnow().isoformat(),
            "date_updated": date_updated,
            "status": status,
        }

    def parse_pdf(self, response, url, domain, status):
        """
        Parse PDF content with resilience to failures.
        """
        try:
            with fitz.open(stream=io.BytesIO(response.body), filetype="pdf") as doc:
                raw_text = "\n".join(page.get_text() for page in doc)
                metadata = doc.metadata or {}
        except Exception as e:
            self.logger.warning(f"PDF parsing failed for {url}: {e}")
            self.stats["errors"] += 1
            self.subdomain_stats[domain]["errors"] += 1
            self.update_rich_table()
            yield {
                "url": url,
                "type": "pdf",
                "parse_error": str(e),
                "text": "",
                "date_scraped": datetime.utcnow().isoformat(),
                "status": status,
            }
            return

        text = self.clean_text(raw_text)

        # Skip empty PDFs
        if not text:
            self.stats["skipped_empty"] += 1
            self.subdomain_stats[domain]["skipped_empty"] += 1
            self.logger.info(f"⏭ Skipping empty PDF: {url}")
            self.update_rich_table()
            return

        # Update stats
        self.stats["pdf"] += 1
        self.subdomain_stats[domain]["pdf"] += 1
        self.stats["total"] += 1
        self.update_rich_table()

        yield {
            "url": url,
            "type": "pdf",
            "title": metadata.get("title", ""),
            "author": metadata.get("author", ""),
            "text": text,
            "date_scraped": datetime.utcnow().isoformat(),
            "status": status,
        }

    def clean_text(self, text):
        """Normalize and deduplicate lines."""
        text = unicodedata.normalize("NFKC", text)
        lines = set(line.strip() for line in text.splitlines() if line.strip())
        return "\n".join(lines)

    def extract_date(self, response):
        """Extract date metadata from HTML."""
        selectors = [
            'meta[property="article:published_time"]::attr(content)',
            'meta[name="date"]::attr(content)',
            "time::text",
            ".date::text",
        ]
        for sel in selectors:
            date = response.css(sel).get()
            if date:
                return date.strip()
        return None

    def parse_ical(self, response, url, domain, status):
        """Parses an iCalendar (.ics or vCard) response and extracts individual events."""
        try:
            cal = Calendar.from_ical(response.body)
            events = [ev for ev in cal.walk("VEVENT")]
            for ev in events:
                summary = ev.get("SUMMARY")
                dtstart = (
                    ev.get("DTSTART").dt.isoformat() if ev.get("DTSTART") else None
                )
                dtend = ev.get("DTEND").dt.isoformat() if ev.get("DTEND") else None
                desc = ev.get("DESCRIPTION", "")
                yield {
                    "url": url,
                    "type": "ical-event",
                    "title": summary,
                    "text": desc,
                    "start": dtstart,
                    "end": dtend,
                    "date_scraped": datetime.utcnow().isoformat(),
                    "status": status,
                }
            self.stats["ical"] += len(events)
            self.subdomain_stats[domain]["ical"] += len(events)
            self.stats["total"] += len(events)
        except Exception as e:
            self.logger.warning(f"iCal parsing failed for {url}: {e}")
            self.stats["errors"] += 1
            self.subdomain_stats[domain]["errors"] += 1
        finally:
            self.update_rich_table()

    def update_rich_table(self):
        """
        Update live statistics table, with:
        - no cropping (console.height is large)
        - alphabetical sorting by subdomain
        """
        elapsed_str = str(datetime.utcnow() - self.start_time).split(".")[0]
        table = self._create_rich_table()

        # alphabetical by subdomain name
        sorted_subs = sorted(self.subdomain_stats.items(), key=lambda pair: pair[0])

        for domain, counts in sorted_subs:
            table.add_row(
                domain,
                str(counts["html"]),
                str(counts["pdf"]),
                str(counts["ical"]),
                str(counts["errors"]),
                str(counts["skipped_empty"]),
                f"{counts['bytes'] / 1024:.2f} KB",
            )

        table.add_row("─" * 70, "", "", "", "", "", "")
        table.add_row(
            f"SUMMARY ⏱ {elapsed_str}",
            str(self.stats["html"]),
            str(self.stats["pdf"]),
            str(self.stats["ical"]),
            str(self.stats["errors"]),
            str(self.stats["skipped_empty"]),
            f"{self.stats['bytes'] / (1024 * 1024):.2f} MB",
            style="bold green",
        )
        self.live.update(table, refresh=True)

    def _create_rich_table(self):
        """Initialize rich table structure, now with a Skipped column."""
        t = Table(show_header=True, header_style="bold magenta")
        t.add_column("Subdomain", style="cyan")
        t.add_column("HTML", justify="right")
        t.add_column("PDF", justify="right")
        t.add_column("iCal", justify="right")
        t.add_column("Errors", justify="right")
        t.add_column("Skipped", justify="right")
        t.add_column("Bytes", justify="right")
        return t

    def closed(self, reason):
        """Close resources gracefully."""
        self.executor.shutdown(wait=True)
        self.live.__exit__(None, None, None)
        self.logger.info(f"Spider closed: {reason}")
