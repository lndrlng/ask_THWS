import scrapy
from urllib.parse import urljoin, urlparse
import fitz
import io
import re
from datetime import datetime


class ThwsSpider(scrapy.Spider):
    name = "thws"
    allowed_domains = ["thws.de"]
    start_urls = ["https://www.thws.de/", "https://fiw.thws.de/"]

    def __init__(self, *args, **kwargs) -> None:
        """
        Initialize the ThwsSpider with tracking for visited URLs and stats.
        """
        super().__init__(*args, **kwargs)
        self.visited: set[str] = set()
        self.stats: dict[str, int] = {
            "html": 0,
            "pdf": 0,
            "ical": 0,
            "errors": 0,
            "total": 0,
        }

    def parse(self, response: scrapy.http.Response) -> None:
        """
        Parse the response from the website. Handles HTML, PDF, and iCal responses.
        """
        url = self.normalize_url(response.url)
        if url in self.visited:
            return
        self.visited.add(url)

        content_type = response.headers.get("Content-Type", b"").decode("utf-8").lower()

        if url.lower().endswith(".pdf") or "application/pdf" in content_type:
            yield from self.parse_pdf(response)
            return

        if url.lower().endswith(".ics") or "text/calendar" in content_type:
            yield from self.parse_ical(response)
            return

        # Extract HTML content from main selectors or fallback to body text
        main_selectors = response.css("div#main, main, [role=main]")
        if main_selectors:
            raw_text = "\n".join(main_selectors.css("::text").getall())
        else:
            raw_text = "\n".join(response.css("body ::text").getall())

        cleaned_text = self.clean_text(raw_text)
        title = response.css("title::text").get(default="").strip()
        date = self.extract_date(response)

        self.stats["html"] += 1
        self.stats["total"] += 1

        yield {
            "url": url,
            "type": "html",
            "title": title,
            "text": cleaned_text,
            "date_scraped": datetime.utcnow().isoformat(),
            "date_updated": date,
        }

        # Follow internal links
        for href in response.css("a::attr(href)").getall():
            next_url = urljoin(url, href)
            parsed = urlparse(next_url)
            if parsed.netloc.endswith("thws.de"):
                normalized_next = self.normalize_url(next_url)
                if normalized_next not in self.visited:
                    yield response.follow(next_url, callback=self.parse)

    def parse_pdf(self, response: scrapy.http.Response) -> None:
        """
        Parse PDF content from the response and yield scraped data.
        """
        url = self.normalize_url(response.url)
        try:
            pdf_bytes = response.body
            text = ""
            with fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf") as doc:
                for page in doc:
                    text += page.get_text()

            cleaned_text = self.clean_text(text)

            self.stats["pdf"] += 1
            self.stats["total"] += 1

            yield {
                "url": url,
                "type": "pdf",
                "title": "",
                "text": cleaned_text,
                "date_scraped": datetime.utcnow().isoformat(),
                "date_updated": None,
            }

        except Exception as e:
            self.stats["errors"] += 1
            self.logger.warning(f"PDF parsing failed for {url}: {e}")

    def parse_ical(self, response: scrapy.http.Response) -> None:
        """
        Parse iCal content from the response and yield scraped data.
        """
        url = self.normalize_url(response.url)
        try:
            text = response.text
            cleaned_text = self.clean_text(text)
            title = self.extract_ical_title(text)

            self.stats["ical"] += 1
            self.stats["total"] += 1

            yield {
                "url": url,
                "type": "ical",
                "title": title,
                "text": cleaned_text,
                "date_scraped": datetime.utcnow().isoformat(),
                "date_updated": None,
            }

        except Exception as e:
            self.stats["errors"] += 1
            self.logger.warning(f"iCal parsing failed for {url}: {e}")

    def clean_text(self, text: str) -> str:
        """
        Clean text by stripping whitespace from lines, removing empty lines,
        and deduplicating lines.
        """
        lines = [line.strip() for line in text.splitlines()]
        lines = [line for line in lines if line]
        return self.deduplicate_lines("\n".join(lines))

    def deduplicate_lines(self, text: str) -> str:
        """
        Remove duplicate lines from text while preserving order.
        """
        seen: set[str] = set()
        unique_lines = []
        for line in text.splitlines():
            if line not in seen:
                seen.add(line)
                unique_lines.append(line)
        return "\n".join(unique_lines)

    def normalize_url(self, url: str) -> str:
        """
        Normalize a URL by removing query parameters and trailing slashes.
        """
        parsed = urlparse(url)
        return parsed._replace(query="").geturl().rstrip("/")

    def extract_date(self, response: scrapy.http.Response) -> str | None:
        """
        Extract a date from the response using common meta and text selectors.
        Attempts to parse and standardize the date format.

        Returns:
            A standardized ISO date string if parsing succeeds, else the raw date string,
            or None if no date is found.
        """
        selectors = [
            'meta[property="article:published_time"]::attr(content)',
            'meta[name="date"]::attr(content)',
            "time::text",
            ".date::text",
        ]
        for selector in selectors:
            date_str = response.css(selector).get()
            if date_str:
                date_str = date_str.strip()
                try:
                    # Attempt to parse to a standardized ISO format
                    parsed_date = datetime.fromisoformat(date_str)
                    return parsed_date.isoformat()
                except ValueError:
                    # If parsing fails, return the raw string
                    return date_str
        return None

    def extract_ical_title(self, text: str) -> str:
        """
        Extract the title from iCal content using a regex pattern.
        """
        match = re.search(r"SUMMARY:(.+)", text)
        return match.group(1).strip() if match else ""

    def closed(self, reason: str) -> None:
        """
        Log a summary of the crawling statistics upon spider closure.
        """
        self.logger.info("=== CRAWLING SUMMARY ===")
        for key, value in self.stats.items():
            self.logger.info(f"{key.upper()}: {value}")
        self.logger.info(f"Spider closed because: {reason}")
