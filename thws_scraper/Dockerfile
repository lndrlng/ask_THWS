FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y  --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --prefix=/install \
    scrapy==2.12.0 \
    pymupdf==1.25.5 \
    beautifulsoup4==4.13.4 \
    readability-lxml==0.8.1 \
    lxml-html-clean==0.4.2 \
    icalendar==6.1.3 \
    langdetect==1.0.9 \
    langchain==0.3.23 \
    pandas==2.2.3 \
    jinja2

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY --from=builder /install /usr/local

COPY . .

RUN mkdir -p result

CMD ["scrapy", "crawl", "thws"]
