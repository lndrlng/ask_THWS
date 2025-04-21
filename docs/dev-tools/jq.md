# Some Jq commands for quering the data

Show total entries:
```shell
jq 'length' data/thws_data3_raw.json
```

Show count of different types:
```shell
jq -r '
  group_by(.type)
  | map("\(.[0].type)\t\(length)")
  | .[]
' data/thws_data3_raw.json | column -t -s (echo -e "\t")
```

Show all unique subdomains from the json:

```shell
jq -r '[ .[].url | split("/")[2] ] | sort | unique[]' data/thws_data3_raw.json
```

Show results per subdomain:

```shell
jq -r '
    group_by(.url | split("/")[2])
    | sort_by(length)
    | .[] 
    | "\(.[0].url | split("/")[2])\t\(length)"
' data/thws_data3_raw.json | column -t -s (echo -e "\t")

```

Count how many fields does not have `date_updated`:
```shell
jq '[ .[] | select(.date_updated == null) ] | length' data/thws_data3_raw.json
```

Most chars per line: 
```shell
jq -r '
  sort_by(.text | length)
  | reverse
  | .[:5][]
  | "\(.url) → \(.text|length) chars"
' data/thws_data3_raw.json
```

Summary per subdomain:
```shell
jq '
  group_by(.url|split("/")[2])
  | map({
      subdomain: (.[0].url|split("/")[2]),
      total: length,
      by_type: (group_by(.type) | map({ (.[0].type): length }) | add)
    })
' data/thws_data3_raw.json
```

List all PDF filenames:
```shell
jq -r '.[] | select(.type=="pdf") | .url | split("/") | last' data/thws_data3_raw.json
```

all pdfs and its title:
```shell
jq -r '.[] | select(.type == "pdf") | [.title] | @csv' data/thws_data3_raw.json
```

all pdfs and its text:
```shell
jq -r '.[] | select(.type == "pdf") | [.text] | @csv' data/thws_data3_raw.json
```

show all status values
```shell
jq -r 'group_by(.status) | map("\(.[0].status)\t\(length)") | .[]' data/thws_data3_raw.json | column -t -s (echo -e "\t")
```

show all etags
```shell
jq -r '.[].etag | select(length > 0)' data/thws_data3_raw.json | sort -u
```

List all iCal filenames:
```shell
jq -r '.[] | select(.type=="ical-event") | .url | split("/") | last' data/thws_data3_raw.json
```

extract each icals summary:
```shell
for url in (jq -r '.[] | select(.type=="ical-event") | .url' data/thws_data3_raw.json)
    set fn (basename $url)
    set title (curl -s $url | grep -m1 '^SUMMARY:' | sed 's/^SUMMARY://')
    printf '%s → %s\n' $fn $title
end
```

extract just all results from fiw.thws.de
```shell
jq -r '
  .[] 
  | select(.url | contains("fiw.thws.de")) 
  | [.url, .type, .title, .author, .status] 
  | @csv
' data/thws_data3_raw.json > fiw_results.csv
```