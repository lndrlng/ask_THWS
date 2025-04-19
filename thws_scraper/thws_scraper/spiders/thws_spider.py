import io
import re
import unicodedata
from datetime import datetime
from urllib.parse import urlparse

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
    name = "thws"
    allowed_domains = ["thws.de"]
    start_urls = [
        "https://www.thws.de/",
        "https://fiw.thws.de/",
    ]
    rules = [
        # follow all links within allowed_domains, handle every response in parse_item
        Rule(LinkExtractor(allow_domains=allowed_domains), callback="parse_item", follow=True),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stats = {"html": 0, "pdf": 0, "ical": 0, "total": 0, "errors": 0}
        self.subdomain_stats = defaultdict(lambda: {"html": 0, "pdf": 0, "ical": 0, "errors": 0})
        self.start_time = datetime.utcnow()

        self.table = self._create_rich_table()
        self.live = Live(self.table, console=Console(), refresh_per_second=4)
        self.live.__enter__()

    def parse_item(self, response):
        url = self.normalize_url(response.url)
        domain = urlparse(url).netloc
        status = response.status
        etag = response.headers.get("ETag", b"").decode("utf-8", errors="ignore")
        last_modified = response.headers.get("Last-Modified", b"").decode("utf-8", errors="ignore")
        ctype = response.headers.get("Content-Type", b"").decode("utf-8", errors="ignore").split(";")[0].lower()

        # skip hard 404
        if status == 404:
            return

        try:
            if ctype == "application/pdf":
                yield from self.parse_pdf(response, url, domain, status, etag, last_modified)
            elif ctype in ("text/calendar", "text/vcard", "application/ical"):
                yield from self.parse_ical(response, url, domain, status, etag, last_modified)
            else:
                yield from self.parse_html(response, url, domain, status, etag, last_modified)
        except Exception as e:
            self.logger.warning(f"Error parsing {url}: {e}")
            self.stats["errors"] += 1
            self.subdomain_stats[domain]["errors"] += 1
            self.update_rich_table()

    def parse_html(self, response, url, domain, status, etag, last_modified):
        # extract main content via readability
        doc = Document(response.text)
        summary_html = doc.summary()
        text = BeautifulSoup(summary_html, "lxml").get_text()
        cleaned = self.clean_text(text)

        # skip soft-404s
        if any(msg in cleaned.lower() for msg in ["404", "not found", "diese seite existiert nicht"]):
            return

        # title and date
        headline = BeautifulSoup(summary_html, "lxml").select_one("h1")
        title = headline.get_text().strip() if headline else response.css("title::text").get(default="").strip()
        date_updated = self.extract_date(response)

        item = {
            "url": url,
            "type": "html",
            "title": title,
            "text": cleaned,
            "date_scraped": datetime.utcnow().isoformat(),
            "date_updated": date_updated,
            "status": status,
            "etag": etag,
            "last_modified": last_modified,
        }

        self.stats["html"] += 1
        self.subdomain_stats[domain]["html"] += 1
        self.stats["total"] += 1
        self.update_rich_table()
        yield item

    def parse_pdf(self, response, url, domain, status, etag, last_modified):
        try:
            with fitz.open(stream=io.BytesIO(response.body), filetype="pdf") as doc:
                metadata = doc.metadata or {}
                text = "\n".join(page.get_text() for page in doc)
        except Exception as e:
            self.logger.warning(f"PDF parsing failed for {url}: {e}")
            self.stats["errors"] += 1
            self.subdomain_stats[domain]["errors"] += 1
            self.update_rich_table()
            return

        cleaned = self.clean_text(text)
        item = {
            "url": url,
            "type": "pdf",
            "title": metadata.get("title", ""),
            "author": metadata.get("author", ""),
            "text": cleaned,
            "date_scraped": datetime.utcnow().isoformat(),
            "date_updated": None,
            "status": status,
            "etag": etag,
            "last_modified": last_modified,
        }

        self.stats["pdf"] += 1
        self.subdomain_stats[domain]["pdf"] += 1
        self.stats["total"] += 1
        self.update_rich_table()
        yield item

    def parse_ical(self, response, url, domain, status, etag, last_modified):
        try:
            cal = Calendar.from_ical(response.body)
            events = [ev for ev in cal.walk("VEVENT")]
            for ev in events:
                summary = ev.get("SUMMARY")
                dtstart = ev.get("DTSTART").dt.isoformat() if ev.get("DTSTART") else None
                dtend = ev.get("DTEND").dt.isoformat() if ev.get("DTEND") else None
                desc = ev.get("DESCRIPTION", "")
                item = {
                    "url": url,
                    "type": "ical-event",
                    "title": summary,
                    "text": desc,
                    "start": dtstart,
                    "end": dtend,
                    "date_scraped": datetime.utcnow().isoformat(),
                    "status": status,
                    "etag": etag,
                    "last_modified": last_modified,
                }
                yield item
            # count by event
            self.stats["ical"] += len(events)
            self.subdomain_stats[domain]["ical"] += len(events)
            self.stats["total"] += len(events)
        except Exception as e:
            self.logger.warning(f"iCal parsing failed for {url}: {e}")
            self.stats["errors"] += 1
            self.subdomain_stats[domain]["errors"] += 1
        finally:
            self.update_rich_table()

    def clean_text(self, text: str) -> str:
        text = unicodedata.normalize("NFKC", text)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return self.deduplicate_lines("\n".join(lines))

    def deduplicate_lines(self, text: str) -> str:
        seen, out = set(), []
        for line in text.splitlines():
            if line not in seen:
                seen.add(line)
                out.append(line)
        return "\n".join(out)

    def normalize_url(self, url: str) -> str:
        p = urlparse(url)
        return p._replace(query="").geturl().rstrip("/")

    def extract_date(self, response):
        for sel in ('meta[property="article:published_time"]::attr(content)',
                    'meta[name="date"]::attr(content)',
                    "time::text",
                    ".date::text"):
            s = response.css(sel).get()
            if s:
                s = s.strip()
                try:
                    return datetime.fromisoformat(s).isoformat()
                except ValueError:
                    return s
        return None

    def closed(self, reason):
        self.live.__exit__(None, None, None)
        self.logger.info("=== FINAL CRAWLING SUMMARY ===")
        for k, v in self.stats.items():
            self.logger.info(f"{k.upper()}: {v}")
        self.logger.info(f"Spider closed because: {reason}")

    def update_rich_table(self):
        elapsed = datetime.utcnow() - self.start_time
        elapsed_str = str(elapsed).split(".")[0]

        filtered = {
            d: c for d, c in self.subdomain_stats.items()
            if (c["html"] + c["pdf"] + c["ical"]) > 1
        }
        sorted_subs = sorted(filtered.items(), reverse=True)

        table = Table(show_header=False, expand=True)
        for domain, counts in sorted_subs:
            table.add_row(
                domain,
                str(counts["html"]),
                str(counts["pdf"]),
                str(counts["ical"]),
                str(counts["errors"]),
            )
        table.add_row("─" * 60, "", "", "", "")
        table.add_row("Subdomain", "HTML", "PDF", "iCal", "Errors", style="bold magenta")
        table.add_row(
            f"SUMMARY ⏱ {elapsed_str}",
            str(self.stats["html"]),
            str(self.stats["pdf"]),
            str(self.stats["ical"]),
            str(self.stats["errors"]),
            style="bold green",
        )

        self.live.update(table)

    def _create_rich_table(self) -> Table:
        t = Table(show_header=True, header_style="bold magenta")
        t.add_column("Subdomain", style="cyan")
        t.add_column("HTML", justify="right")
        t.add_column("PDF", justify="right")
        t.add_column("iCal", justify="right")
        t.add_column("Errors", justify="right")
        return t
```