# Clean logs

```shell
jq 'select(
    (.name != "readability.readability")
    and (.error != "Forbidden by robots.txt")
    and (.reason != "unhandled_content_type")
    and (.name != "scrapy.extensions.logstats")
    and (.reason != "soft_error_after_cleaning")
)' result/scrapy_log.jsonl > scrapy_log_cleaned.jsonl
```

# Reasons for Skipped Pages by URL Pattern

```shell
jq -r 'select(.event_type == "page_skipped" and .reason == "ignored_url_pattern") | .pattern_matched' result/scrapy_log.jsonl \
  | sort | uniq -c | sort -nr | column -t
```

# Statistics of Skipped MIME Types

```shell
jq -r 'select(.event_type == "page_skipped" and .reason == "unhandled_content_type") | .content_type' result/scrapy_log.jsonl \
  | sort | uniq -c | sort -nr | column -t
```

# count and rank these soft error messages

```shell
jq -r 'select(.event_type == "page_skipped_html" and .details.soft_errors_matched) | .details.soft_errors_matched[]' result/scrapy_log.jsonl | sort | uniq -c | sort -nr
```

# skipped because their main content was found to be empty after parsing

```shell
jq 'select(.event_type == "page_skipped_html" and (.reason == "empty_content_after_cleaning" or .reason == "empty_full_text_and_readability_empty"))' result/scrapy_log.jsonl | wc -l
```

# Forbidden by robots.txt

```shell
jq 'select(.event_type == "downloader_exception_general" and .error == "Forbidden by robots.txt")' result/scrapy_log.jsonl | wc -l
```

# Most Common Reasons for Skipping Pages (HTML)

```shell
jq -r 'select(.event_type == "page_skipped_html") | .reason' result/scrapy_log.jsonl | sort | uniq -c | sort -nr
```

# GridFS File Sizes

```shell
jq -r 'select(.event_type == "gridfs_file_stored") | [.url, .file_size] | @tsv' result/scrapy_log.jsonl \
  | sort -k2 -nr | head -20 \
  | awk -F'\t' '{
      cmd = "numfmt --to=iec --suffix=B --format=\"%.2f\" <<< " $2;
      cmd | getline size;
      close(cmd);
      print $1 "\t" size
    }' \
  | column -t
```

# Top event types

```shell
jq -r '.event_type' result/scrapy_log.jsonl | sort | uniq -c | sort -nr | column -t
```

# Domains of Skipped URLs

```shell
jq -r 'select(.event_type == "page_skipped") | .url' result/scrapy_log.jsonl | awk -F/ '{print $3}' | sort | uniq -c | sort -nr | column -t
```

# Group by exception Types

```shell
jq -r 'select(.event_type == "downloader_exception_general") | .exception_type' result/scrapy_log.jsonl | sort | uniq -c | sort -nr | column -t
```

# Skipped persons by domain

```shell
jq -r 'select(.reason == "empty_content_after_cleaning" and (.url | test("person"; "i"))) | .url' result/scrapy_log.jsonl \
  | awk -F/ '{print $3}' \
  | sort | uniq -c | sort -nr | column -t
```
