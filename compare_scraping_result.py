import argparse
import json
import logging
from pathlib import Path
from collections import Counter
from statistics import mean, median
from dateutil.parser import parse as date_parse
from deepdiff import DeepDiff
import pandas as pd
import ace_tools as tools


def load_json(path: str) -> dict:
    """
    Load JSON data from a file path.

    Args:
        path (str): The file path to the JSON file.

    Returns:
        dict: Parsed JSON data.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the JSON data cannot be parsed.
    """
    json_path = Path(path)
    if not json_path.exists():
        raise FileNotFoundError(f"File '{path}' not found.")
    try:
        content = json_path.read_text(encoding="utf-8")
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Error decoding JSON from file '{path}'.") from e


def analyze_data(data: list) -> dict:
    """
    Analyze scraped data and compute various metrics.

    Args:
        data (list): List of dictionaries containing scraped data.

    Returns:
        dict: Metrics including total entries, unique URLs, type distribution,
              average, median, max text lengths, count of very short texts,
              missing titles, missing/valid date_updated, and text duplicates.
    """
    total_entries = len(data)
    urls = [entry["url"] for entry in data if "url" in entry]
    unique_urls = set(urls)
    type_distribution = Counter(entry.get("type", "unknown") for entry in data)
    text_lengths = [len(entry.get("text", "")) for entry in data]
    very_short_texts = sum(1 for length in text_lengths if length < 20)
    missing_titles = sum(1 for entry in data if not entry.get("title"))
    missing_dates = sum(1 for entry in data if not entry.get("date_updated"))
    valid_dates = 0
    for entry in data:
        try:
            if entry.get("date_updated"):
                date_parse(entry["date_updated"])
                valid_dates += 1
        except Exception:
            pass
    text_duplicates = len(text_lengths) - len(
        set(entry.get("text", "") for entry in data)
    )

    return {
        "Total Entries": total_entries,
        "Unique URLs": len(unique_urls),
        "Type Distribution": dict(type_distribution),
        "Average Text Length": round(mean(text_lengths), 2) if text_lengths else 0,
        "Median Text Length": median(text_lengths) if text_lengths else 0,
        "Maximum Text Length": max(text_lengths) if text_lengths else 0,
        "Very Short Texts (<20)": very_short_texts,
        "Missing Titles": missing_titles,
        "Missing date_updated": missing_dates,
        "Valid date_updated": valid_dates,
        "Text Duplicates": text_duplicates,
    }


def index_by_url(data: list) -> dict:
    """
    Index data entries by URL.

    Args:
        data (list): List of dictionaries containing scraped data.

    Returns:
        dict: Dictionary mapping URLs to their corresponding data entry.
    """
    return {entry["url"]: entry for entry in data if "url" in entry}


def compare_entries(entry1: dict, entry2: dict, verbose: bool = False) -> list:
    """
    Compare two data entries and report differences.

    Args:
        entry1 (dict): The first data entry.
        entry2 (dict): The second data entry.
        verbose (bool): Whether to output verbose differences.

    Returns:
        list: A list of change descriptions.
    """
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
    """
    Compare two scraper run JSON files.

    Args:
        file1 (str): Path to the first JSON file.
        file2 (str): Path to the second JSON file.
        level (int): Verbosity level (>=2 for detailed differences).

    Returns:
        dict: Dictionary mapping shared URLs to list of changes.
    """
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


def main():
    """
    Main function for CLI execution.
    """
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

    # Setup logging level based on verbosity
    if args.verbose >= 2:
        logging.basicConfig(level=logging.DEBUG)
    elif args.verbose == 1:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)

    try:
        if len(args.inputs) == 1:
            data = load_json(args.inputs[0])
            stats = analyze_data(data)
            df = pd.DataFrame(stats.items(), columns=["Metric", "Value"])
            tools.display_dataframe_to_user(name="Scraper Run Analysis", dataframe=df)

        elif len(args.inputs) == 2:
            data1 = load_json(args.inputs[0])
            data2 = load_json(args.inputs[1])
            stats1 = analyze_data(data1)
            stats2 = analyze_data(data2)
            df = pd.DataFrame(
                [stats1, stats2],
                index=[Path(args.inputs[0]).stem, Path(args.inputs[1]).stem],
            ).T
            tools.display_dataframe_to_user(
                name="Comparison of Scraper Runs", dataframe=df
            )

            if args.verbose > 0:
                changes = compare_runs(
                    args.inputs[0], args.inputs[1], level=args.verbose
                )
                if changes:
                    logging.info("\n🔍 Changes in shared URLs:\n")
                    for url, diffs in changes.items():
                        logging.info(f"🔁 {url}")
                        for d in diffs:
                            logging.info(d)
                else:
                    logging.info("\n✅ No relevant changes found.")
        else:
            parser.print_help()
    except Exception as e:
        logging.error(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
