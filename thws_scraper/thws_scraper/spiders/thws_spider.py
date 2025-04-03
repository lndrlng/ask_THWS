import scrapy
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import fitz
import io


class ThwsSpider(scrapy.Spider):
    name = "thws"
    allowed_domains = ["thws.de", "fiw.thws.de"]
    start_urls = ["https://www.thws.de/", "https://fiw.thws.de/"]

    def parse(self, response):
        url = response.url

        # Handle PDF files
        if (
            url.lower().endswith(".pdf")
            or "application/pdf" in response.headers.get("Content-Type", b"").decode()
        ):
            yield from self.parse_pdf(response)
            return

        # Parse HTML
        soup = BeautifulSoup(response.text, "html.parser")

        # Remove scripts/styles/nav
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)

        yield {"url": url, "type": "html", "text": text}

        # Follow internal links
        for link in soup.find_all("a", href=True):
            next_url = urljoin(url, link["href"])
            if any(domain in next_url for domain in self.allowed_domains):
                yield response.follow(next_url, callback=self.parse)

    def parse_pdf(self, response):
        url = response.url
        pdf_bytes = response.body
        text = ""

        with fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf") as doc:
            for page in doc:
                text += page.get_text()

        yield {"url": url, "type": "pdf", "text": text}
