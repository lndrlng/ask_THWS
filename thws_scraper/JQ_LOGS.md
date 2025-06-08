### Log Analysis Cheatsheet (`jq`)

This cheatsheet provides a collection of `jq` commands to query and analyze the `scrapy_log.jsonl` file.

______________________________________________________________________

#### **Clean Logs**

Filter out common, high-volume, or less critical log entries to create a cleaner log file for focused analysis.

```shell
jq 'select(
    (.name != "readability.readability")
    and (.message != "Successfully parsed HTML page")
    and (.message != "Skipped page: Ignored URL pattern")
    and (.error != "Forbidden by robots.txt")
    and (.reason != "unhandled_content_type")
    and (.name != "scrapy.extensions.logstats")
    and (.reason != "soft_error_after_cleaning")
)' result/scrapy_log_*.jsonl > scrapy_log_cleaned.jsonl
```

Show all skipped empty pages.

```shell
jq 'select(
    (.message == "Skipped HTML: Content is empty after cleaning.")
)' result/scrapy_log_*.jsonl > scrapy_skipped.jsonl
```

______________________________________________________________________

#### **Summarize Skipped Pages**

##### Reasons for Skipping by URL Pattern

Count how many times each `IGNORED_URL_PATTERNS_LIST` pattern was matched.

```shell
jq -r 'select(.event_type == "page_skipped" and .reason == "ignored_url_pattern") | .pattern_matched' result/scrapy_log_*.jsonl \
  | sort | uniq -c | sort -nr | column -t
```

##### Statistics of Skipped MIME Types

Count and rank the `Content-Type` headers of pages that were skipped because they were not HTML, PDF, or iCal.

```shell
jq -r 'select(.event_type == "page_skipped" and .reason == "unhandled_content_type") | .content_type' result/scrapy_log_*.jsonl \
  | sort | uniq -c | sort -nr | column -t
```

##### Domains of Skipped URLs

Show which domains have the most skipped URLs (due to any `page_skipped` reason).

```shell
jq -r 'select(.event_type == "page_skipped") | .url' result/scrapy_log_*.jsonl | awk -F/ '{print $3}' | sort | uniq -c | sort -nr | column -t
```

______________________________________________________________________

#### **Analyze Skipped HTML Pages**

##### Count Soft Error Messages

Count and rank the specific "soft error" strings found in HTML content that caused pages to be skipped.

```shell
jq -r 'select(.event_type == "page_skipped_html" and .details.soft_errors_matched) | .details.soft_errors_matched[]' result/scrapy_log_*.jsonl | sort | uniq -c | sort -nr
```

##### Count Pages Skipped for Being Empty

Count how many HTML pages were skipped because their main content was empty after parsing and cleaning.

```shell
jq 'select(.event_type == "page_skipped_html" and .reason == "empty_content_after_cleaning")' result/scrapy_log_*.jsonl | wc -l
```

##### Most Common Reasons for Skipping HTML

Get a summary of why HTML pages were skipped after parsing (e.g., empty content vs. soft errors).

```shell
jq -r 'select(.event_type == "page_skipped_html") | .reason' result/scrapy_log_*.jsonl | sort | uniq -c | sort -nr
```

##### Skipped "Person" Pages by Domain (due to empty content)

Find which domains have the most "person" detail pages that are being skipped because their content is empty.

```shell
jq -r 'select(.event_type == "page_skipped_html" and .reason == "empty_content_after_cleaning" and (.url | test("person"; "i"))) | .url' result/scrapy_log_*.jsonl \
  | awk -F/ '{print $3}' \
  | sort | uniq -c | sort -nr | column -t
```

______________________________________________________________________

#### **Analyze Errors and Exceptions**

##### Count Pages Forbidden by `robots.txt`

```shell
jq 'select(.event_type == "downloader_exception_general" and .error == "Forbidden by robots.txt")' result/scrapy_log_*.jsonl | wc -l
```

##### Group by Exception Type

Count and rank the different types of downloader exceptions (e.g., `DNSLookupError`, `TimeoutError`).

```shell
jq -r 'select(.event_type == "downloader_exception_general") | .exception_type' result/scrapy_log_*.jsonl | sort | uniq -c | sort -nr | column -t
```

______________________________________________________________________

#### **General Statistics**

##### Top Event Types

Get a high-level overview of what events are happening most frequently in the logs.

```shell
jq -r '.event_type' result/scrapy_log_*.jsonl | sort | uniq -c | sort -nr | column -t
```

##### Top 20 Largest Files Stored in GridFS

List the largest files stored in GridFS, formatted for human readability.

```shell
jq -r 'select(.event_type == "gridfs_file_stored") | [.url, .file_size] | @tsv' result/scrapy_log_*.jsonl \
  | sort -k2 -nr | head -20 \
  | awk -F'\t' '{
      cmd = "numfmt --to=iec --suffix=B --format=\"%.2f\" <<< " $2;
      cmd | getline size;
      close(cmd);
      print $1 "\t" size
    }' \
  | column -t
```
