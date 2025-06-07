# Logging Key Documentation

This document provides a definitive reference for all possible keys present in the JSON log output of the `thws_scraper`.

Logs are written as JSONL to `result/scrapy_log.jsonl`.

______________________________________________________________________

## 1. Base Schema

These keys are present in **every** log entry.

| Key | Type | Description |
| :--- | :--- | :--- |
| `asctime` | `string` | Timestamp of the log entry (e.g., `"2025-06-06 18:04:14,214"`). |
| `levelname` | `string` | Log level (`"INFO"`, `"WARNING"`, `"ERROR"`, `"DEBUG"`). |
| `name` | `string` | The logger that created the entry (e.g., `"thws_scraper.spiders.thws"`). |
| `message` | `string` | A human-readable description of the event. |

______________________________________________________________________

## 2. Conditional Base Schema

These keys are present in the vast majority of operational log entries but may be absent in some specific contexts (e.g., during initial setup before the spider is fully loaded).

| Key | Type | Description |
| :--- | :--- | :--- |
| `spider` | `string` | The string representation of the running spider instance. |

______________________________________________________________________

## 3. Event-Specific Schemas

Most logs include an `event_type` key. The tables below document all additional keys associated with a specific `event_type`.

### `event_type: downloader_exception_general` / `dns_error`

An error occurred during the download of a request.

| Key | Type | Description |
| :--- | :--- | :--- |
| `url` | `string` | The URL that failed to download. |
| `spider_name`| `string` | Name of the active spider. |
| `middleware_class`|`string` | The middleware that caught the exception (`"ThwsErrorMiddleware"`). |
| `error` | `string` | The exception message (e.g., `"Forbidden by robots.txt"`). |
| `exception_type`| `string` | The Python class name of the exception (e.g., `"IgnoreRequest"`). |
| `domain` | `string` | The domain of the URL (e.g., `"www.thws.de"`). |

### `event_type: file_content_missing_for_binary`

A file item (`pdf`, `ical`) was processed by the pipeline but contained no binary data.

| Key | Type | Description |
| :--- | :--- | :--- |
| `pipeline_class`| `string` | Name of the pipeline class (`"MongoPipeline"`). |
| `url` | `string` | The URL of the item. |
| `item_type`| `string` | The type of the item (`"pdf"`, `"ical"`). |

### `event_type: file_embedded_in_doc`

A small file's binary content was embedded directly into its MongoDB document.

| Key | Type | Description |
| :--- | :--- | :--- |
| `pipeline_class`| `string` | Name of the pipeline class (`"MongoPipeline"`). |
| `url` | `string` | The URL of the file. |
| `file_size` | `integer`| The size of the file in bytes. |

### `event_type: gridfs_deleted_old_version`

An old version of a file was deleted from GridFS before writing the new version.

| Key | Type | Description |
| :--- | :--- | :--- |
| `pipeline_class`| `string` | Name of the pipeline class (`"MongoPipeline"`). |
| `url` | `string` | The URL of the file being updated. |
| `gridfs_id_deleted` | `string` | The GridFS ID (`ObjectId`) of the deleted file. |

### `event_type: gridfs_file_stored`

A large file was successfully stored in GridFS.

| Key | Type | Description |
| :--- | :--- | :--- |
| `pipeline_class`| `string` | Name of the pipeline class (`"MongoPipeline"`). |
| `url` | `string` | The URL of the stored file. |
| `file_size` | `integer`| The size of the file in bytes. |
| `gridfs_id` | `string` | The new GridFS ID (`ObjectId`) for the stored file. |

### `event_type: gridfs_storage_error`

An error occurred while trying to save a file to GridFS.

| Key | Type | Description |
| :--- | :--- | :--- |
| `pipeline_class`| `string` | Name of the pipeline class (`"MongoPipeline"`). |
| `url` | `string` | The URL of the file that failed to store. |
| `file_size` | `integer`| The size of the file in bytes. |
| `error` | `string` | The error message from the GridFS library. |

### `event_type: html_cleaning_error`

An error occurred in the lxml library while cleaning an HTML fragment.

| Key | Type | Description |
| :--- | :--- | :--- |
| `error_details`| `string` | The exception message from the cleaning function. |

### `event_type: item_yield_empty_final`

A non-HTML parser (`pdf`, `ical`) returned no item, and no further links were found to follow.

| Key | Type | Description |
| :--- | :--- | :--- |
| `url` | `string` | The URL of the processed response. |
| `content_type` | `string` | The `Content-Type` header of the response. |
| `reason` | `string` | A description of why nothing was yielded. |

### `event_type: middleware_opened`

A spider or downloader middleware was initialized.

| Key | Type | Description |
| :--- | :--- | :--- |
| `spider_name`| `string` | Name of the active spider. |
| `middleware_class`| `string` | The class name of the middleware that was opened. |

### `event_type: mongodb_connected`

The MongoDB pipeline successfully established a connection.

| Key | Type | Description |
| :--- | :--- | :--- |
| `pipeline_class`| `string` | Name of the pipeline class (`"MongoPipeline"`). |
| `mongo_host` | `string` | The MongoDB host. |
| `mongo_port` | `integer`| The MongoDB port. |
| `mongo_db_name`| `string` | The name of the database connected to. |

### `event_type: mongodb_connection_closed`

The MongoDB connection was closed at the end of the crawl.

| Key | Type | Description |
| :--- | :--- | :--- |
| `pipeline_class`| `string` | Name of the pipeline class (`"MongoPipeline"`). |

### `event_type: mongodb_connection_failure`

The pipeline could not connect to MongoDB at startup.

| Key | Type | Description |
| :--- | :--- | :--- |
| `pipeline_class`| `string` | Name of the pipeline class (`"MongoPipeline"`). |
| `mongo_host` | `string` | The MongoDB host attempted. |
| `mongo_port` | `integer`| The MongoDB port attempted. |
| `error` | `string` | The connection error message. |

### `event_type: mongodb_index_ensured`

The pipeline verified that unique indexes exist on the `url` field for collections.

| Key | Type | Description |
| :--- | :--- | :--- |
| `pipeline_class`| `string` | Name of the pipeline class (`"MongoPipeline"`). |
| `collections` |`array[string]`| A list of collection names where indexes were checked. |

### `event_type: mongodb_item_upserted`

An item was successfully written to a MongoDB collection.

| Key | Type | Description |
| :--- | :--- | :--- |
| `pipeline_class`| `string` | Name of the pipeline class (`"MongoPipeline"`). |
| `url` | `string` | The URL of the item. |
| `item_type`| `string` | The type of item (`"html"`, `"pdf"`, `"ical"`). |
| `collection` | `string` | The target collection name (`"pages"`, `"files"`). |
| `gridfs_id_ref`|`string`(Optional)| If the item references a GridFS file, its ID is here. |

### `event_type: mongodb_not_initialized_drop`

An item was dropped because the database connection was not available.

| Key | Type | Description |
| :--- | :--- | :--- |
| `pipeline_class`| `string` | Name of the pipeline class (`"MongoPipeline"`). |
| `item_url` | `string` | The URL of the dropped item. |
| `item_type`| `string` | The type of the dropped item. |

### `event_type: mongodb_operation_failure_setup`

A database command failed during pipeline setup (e.g., creating indexes).

| Key | Type | Description |
| :--- | :--- | :--- |
| `pipeline_class`| `string` | Name of the pipeline class (`"MongoPipeline"`). |
| `mongo_host` | `string` | The MongoDB host. |
| `mongo_port` | `integer`| The MongoDB port. |
| `mongo_db_name`| `string` | The database where the failure occurred. |
| `error` | `string` | The detailed error from the database. |

### `event_type: mongodb_upsert_operation_failure`

An item could not be written to the database due to an operational error.

| Key | Type | Description |
| :--- | :--- | :--- |
| `pipeline_class`| `string` | Name of the pipeline class (`"MongoPipeline"`). |
| `url` | `string` | The URL of the item that failed. |
| `item_type`| `string` | The type of the failed item. |
| `collection` | `string` | The target collection name. |
| `error` | `string` | The error from the database (e.g., authentication, permissions). |
| `reason`|`string`(Optional)| A specific reason if known (e.g., `"document_too_large"`). |
| `approx_item_dict_str_len` | `integer`(Optional)| The approximate string length of the failed document. |

### `event_type: mongodb_upsert_unexpected_error` / `mongodb_unexpected_setup_error`

An unexpected Python exception occurred during database interactions.

| Key | Type | Description |
| :--- | :--- | :--- |
| `pipeline_class`| `string` | Name of the pipeline class (`"MongoPipeline"`). |
| `url` | `string`(Optional)| The URL of the item being processed (if applicable). |
| `item_type`|`string`(Optional)| The type of item being processed (if applicable). |
| `collection`|`string`(Optional)| The target collection (if applicable). |
| `error` | `string` | The string representation of the Python exception. |
| `traceback`| `string` | A full Python traceback for debugging. |

### `event_type: page_skipped`

A URL was deliberately not processed based on a predefined rule.

| Key | Type | Description |
| :--- | :--- | :--- |
| `url` | `string` | The URL that was skipped. |
| `reason`|`string`| Why it was skipped (`"ignored_url_pattern"`, `"unhandled_content_type"`). |
| `pattern_matched`|`string`(Optional)| The specific pattern from settings that was matched. |
| `content_type`|`string`(Optional)| The `Content-Type` header of the response. |

### `event_type: page_skipped_html`

An HTML page was skipped after parsing because its content was invalid.

| Key | Type | Description |
| :--- | :--- | :--- |
| `url` | `string` | The URL of the skipped HTML page. |
| `reason` | `string` | Reason for skipping (e.g., `"soft_error_after_cleaning"`). |
| `details` | `object` | An object containing detailed parsing metrics. |
| `details.cleaned_main_text_length` | `integer` | Character count of the main content after cleaning. |
| `details.raw_readability_text_length` | `integer` | Character count of the raw text from Readability. |
| `details.raw_readability_preview` | `string` | A short preview of the raw extracted text. |
| `details.soft_errors_matched`|`array[string]`| A list of the soft error strings found in the content.|

### `event_type: pdf_item_with_error`

A PDF item was created, but an error was noted during its processing. The `parse_error` field in the final item will be set.

| Key | Type | Description |
| :--- | :--- | :--- |
| `url` | `string` | The URL of the PDF. |
| `item_parse_error_field`| `string` | The error message that will be saved with the item. |

### `event_type: pdf_processing_error`

A fatal error occurred in the PyMuPDF library while parsing a PDF.

| Key | Type | Description |
| :--- | :--- | :--- |
| `url` | `string` | The URL of the PDF that failed to parse. |
| `error_details`| `string` | The string representation of the Python exception. |
| `traceback`| `string` | A full Python traceback for debugging. |

### `event_type: readability_error`

The Readability library failed to extract main content from an HTML page.

| Key | Type | Description |
| :--- | :--- | :--- |
| `url` | `string` | The URL of the page that failed. |
| `error` | `string` | The error message from the Readability library. |

### `event_type: readability_empty_summary`

Readability ran successfully but returned no main content.

| Key | Type | Description |
| :--- | :--- | :--- |
| `url` | `string` | The URL of the page with no extracted content. |

### `event_type: robots_txt_bypass`

The `robots.txt` rules were intentionally bypassed for a specific URL.

| Key | Type | Description |
| :--- | :--- | :--- |
| `url` | `string` | The URL for which the rules were bypassed. |
| `reason` | `string` | The justification for the bypass (e.g., `"path_starts_with_fileadmin"`). |
| `middleware_class`| `string` | The middleware responsible (`"RobotsBypassMiddleware"`). |

### `event_type: spider_exception`

An unhandled exception occurred within the spider's processing logic.

| Key | Type | Description |
| :--- | :--- | :--- |
| `url` | `string` | The URL of the response being processed when the error occurred. |
| `spider_name`| `string` | Name of the active spider. |
| `middleware` | `string` | The middleware that caught the exception. |
| `error` | `string` | The string representation of the Python exception. |
| `exception_type`| `string` | The Python class name of the exception. |
| `traceback`| `string` | A full Python traceback for debugging. |

### `event_type: unknown_item_type_pipeline`

The database pipeline received an item of an unknown or unhandled type.

| Key | Type | Description |
| :--- | :--- | :--- |
| `pipeline_class`| `string` | Name of the pipeline class (`"MongoPipeline"`). |
| `item_url` | `string` | The URL of the unknown item. |
| `item_type`| `string` | The type of the unknown item. |
