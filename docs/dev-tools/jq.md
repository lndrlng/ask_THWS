# Some Jq commands for quering the data

Show total entries:
```shell
jq 'length' data/thws_data2_raw.json
```

Show count of different types:
```shell
 jq -r '
  group_by(.type)
  | map("\(.[0].type)\t\(length)")
  | .[]
' data/thws_data2_raw.json | column -t -s $'\t'
```

Show all unique subdomains from the json:

```shell
jq -r '[ .[].url | split("/")[2] ] | sort | unique[]' data/thws_data2_raw.json
```

Show results per subdomain:

```shell
jq -r '
  group_by(.url | split("/")[2])
  | sort_by(length)
  | .[] 
  | "\(.[0].url | split("/")[2])\t\(length)"
' data/thws_data2_raw.json \
| column -t -s $'\t'
```

Count how many fields does not have `date_updated`:
```shell
jq '[ .[] | select(.date_updated == null) ] | length' data/thws_data2_raw.json
```

Most chars per line: 
```shell
jq -r '
  sort_by(.text | length)
  | reverse
  | .[:5][]
  | "\(.url) → \(.text|length) chars"
' data/thws_data2_raw.json
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
' data/thws_data2_raw.json
```

List all PDF filenames:
```shell
jq -r '.[] | select(.type=="pdf") | .url | split("/") | last' data/thws_data2_raw.json
```

List all iCal filenames:
```shell
jq -r '.[] | select(.type=="ical") | .url | split("/") | last' data/thws_data2_raw.json
```

extract each icals summary:
```shell
jq -r '.[] | select(.type=="ical") | .url' data/thws_data2_raw.json \
| while read url; do
    fn=$(basename "$url")
    # fetch the ICS and grab the SUMMARY line
    title=$(curl -s "$url" \
             | grep -m1 '^SUMMARY:' \
             | sed 's/^SUMMARY://')
    printf '%s → %s\n' "$fn" "$title"
  done
```