import argparse
import json
import logging
from pathlib import Path
from collections import Counter, defaultdict
from statistics import mean, median
from dateutil.parser import parse as date_parse
from deepdiff import DeepDiff
import pandas as pd
from tabulate import tabulate


def load_json(path: str) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        raise FileNotFoundError(f"File '{path}' not found.")
    try:
        content = json_path.read_text(encoding="utf-8")
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Error decoding JSON from file '{path}'.") from e


def analyze_data(data: list) -> tuple[dict, dict]:
    total_entries = len(data)
    urls = [entry["url"] for entry in data if "url" in entry]
    unique_urls = set(urls)

    per_type_data = defaultdict(list)
    for entry in data:
        per_type_data[entry.get("type", "unknown")].append(entry)

    overall_stats = {
        "Total Entries": total_entries,
        "Unique URLs": len(unique_urls),
        "Text Duplicates": count_duplicates(data),
    }

    type_stats = defaultdict(dict)
    for type_, entries in per_type_data.items():
        text_lengths = [len(e.get("text", "")) for e in entries]
        type_stats["Count"][type_] = len(entries)
        type_stats["Average Text Length"][type_] = (
            round(mean(text_lengths), 2) if text_lengths else 0
        )
        type_stats["Median Text Length"][type_] = (
            median(text_lengths) if text_lengths else 0
        )
        type_stats["Maximum Text Length"][type_] = (
            max(text_lengths) if text_lengths else 0
        )
        type_stats["Very Short Texts (<20)"][type_] = sum(
            1 for l in text_lengths if l < 20
        )
        type_stats["Missing Titles"][type_] = sum(
            1 for e in entries if not e.get("title")
        )
        type_stats["Missing date_updated"][type_] = sum(
            1 for e in entries if not e.get("date_updated")
        )
        type_stats["Valid date_updated"][type_] = sum(
            1 for e in entries if is_valid_date(e.get("date_updated"))
        )

    return overall_stats, type_stats


def is_valid_date(value) -> bool:
    try:
        if value:
            date_parse(value)
            return True
    except Exception:
        pass
    return False


def count_duplicates(data: list) -> int:
    texts = [entry.get("text", "") for entry in data]
    return len(texts) - len(set(texts))


def index_by_url(data: list) -> dict:
    return {entry["url"]: entry for entry in data if "url" in entry}


def compare_entries(entry1: dict, entry2: dict, verbose: bool = False) -> list:
    diff = DeepDiff(
        entry1, entry2, ignore_order=True, exclude_paths={"root['date_scraped']"}
    )
    result = []
    if "values_changed" in diff:
        for path, change in diff["values_changed"].items():
            field = path.split("[")[-1].strip("]'\"")
            if field in ["title", "text", "date_updated"]:
                if verbose:
                    result.append(
                        f"  • '{field}': '{change['old_value']}' → '{change['new_value']}'"
                    )
                else:
                    if field == "text":
                        result.append(
                            f"  • Text Length: {len(change['old_value'])} → {len(change['new_value'])}"
                        )
                    else:
                        result.append(f"  • {field} changed")
    return result


def compare_runs(file1: str, file2: str, level: int = 0) -> dict:
    data1 = load_json(file1)
    data2 = load_json(file2)
    map1 = index_by_url(data1)
    map2 = index_by_url(data2)

    shared_urls = set(map1.keys()) & set(map2.keys())
    changed = {}

    for url in sorted(shared_urls):
        changes = compare_entries(map1[url], map2[url], verbose=(level >= 2))
        if changes:
            changed[url] = changes

    return changed


def display_analysis(overall: dict, type_stats: dict):
    print("\n📊 Overall Statistics:\n")
    df = pd.DataFrame(overall.items(), columns=["Metric", "Value"])
    print(tabulate(df, headers="keys", tablefmt="fancy_grid"))

    print("\n📂 Breakdown by Type:\n")
    df_type = pd.DataFrame(type_stats).T  # types become columns
    df_type = df_type.fillna(0).astype(object)
    df_type.index.name = "Metric"
    df_type = df_type.reset_index()
    print(tabulate(df_type, headers="keys", tablefmt="fancy_grid"))


def main():
    parser = argparse.ArgumentParser(description="Analyze and compare scraper runs")
    parser.add_argument("inputs", nargs="+", help="One or two JSON files")
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Show changes (-v) or details (-vv)",
    )
    args = parser.parse_args()

    if args.verbose >= 2:
        logging.basicConfig(level=logging.DEBUG)
    elif args.verbose == 1:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)

    try:
        if len(args.inputs) == 1:
            data = load_json(args.inputs[0])
            overall, type_stats = analyze_data(data)
            display_analysis(overall, type_stats)

        elif len(args.inputs) == 2:
            data1 = load_json(args.inputs[0])
            data2 = load_json(args.inputs[1])
            overall1, type_stats1 = analyze_data(data1)
            overall2, type_stats2 = analyze_data(data2)

            print("\n📊 Comparison of Overall Statistics:\n")
            df = pd.DataFrame(
                [overall1, overall2],
                index=[Path(args.inputs[0]).stem, Path(args.inputs[1]).stem],
            ).T.reset_index()
            df.columns = ["Metric"] + list(df.columns[1:])
            print(tabulate(df, headers="keys", tablefmt="fancy_grid"))

            for type_ in sorted(set(type_stats1["Count"]) | set(type_stats2["Count"])):
                print(f"\n📂 Breakdown for type: {type_}\n")
                rows = {}
                for metric in type_stats1:
                    rows.setdefault(metric, {})
                    rows[metric][Path(args.inputs[0]).stem] = type_stats1[metric].get(
                        type_, 0
                    )
                    rows[metric][Path(args.inputs[1]).stem] = type_stats2[metric].get(
                        type_, 0
                    )

                df_type = pd.DataFrame(rows).T.reset_index()
                df_type.columns = ["Metric"] + list(df_type.columns[1:])
                print(tabulate(df_type, headers="keys", tablefmt="fancy_grid"))

            if args.verbose > 0:
                changes = compare_runs(
                    args.inputs[0], args.inputs[1], level=args.verbose
                )
                if changes:
                    print("\n🔍 Changes in shared URLs:\n")
                    for url, diffs in changes.items():
                        print(f"🔁 {url}")
                        for d in diffs:
                            print(d)
                else:
                    print("\n✅ No relevant changes found.")
        else:
            parser.print_help()
    except Exception as e:
        logging.error(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
