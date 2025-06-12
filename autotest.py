# File: autotest_robust.py

import requests
import re
import time
from datetime import datetime
import os

MARKDOWN_FILE = "docs/tests/fragen.md"
API_URL = "http://localhost:8000/ask"
METADATA_URL = "http://localhost:8000/metadata"


def extract_questions(md_file):
    """Extracts questions from a markdown file."""
    if not os.path.exists(md_file):
        print(f"ERROR: Markdown file not found at {md_file}")
        return []
    with open(md_file, "r", encoding="utf-8") as file:
        content = file.read()
    questions = re.findall(r"-\s+(.*?)\?", content)
    return [q.strip() + "?" for q in questions]


def query_api(question):
    """
    Queries the API and handles both successful and error responses.
    Returns the JSON response and the HTTP status code.
    """
    try:
        response = requests.post(API_URL, json={"query": question}, timeout=10000) # Added a timeout
        # Check if the request was successful
        if response.status_code == 200:
            return response.json(), response.status_code
        else:
            # For non-200 responses, we can still try to get a JSON error message
            try:
                error_json = response.json()
            except requests.exceptions.JSONDecodeError:
                error_json = {"detail": response.text} # Fallback if error is not JSON
            return error_json, response.status_code
    except requests.exceptions.RequestException as e:
        # Handle connection errors, timeouts, etc.
        return {"detail": f"Failed to connect to API: {e}"}, 503


def get_metadata():
    """Gets metadata from the API."""
    try:
        response = requests.get(METADATA_URL)
        response.raise_for_status() # Raise an exception for bad status codes
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Could not fetch metadata: {e}")
        return {}


def write_header(f, metadata):
    """Writes the header for the results file."""
    commit_hash = metadata.get("git_commit", "unknown")
    f.write(f"Commit: {commit_hash}\n\n")
    f.write("# Automatischer Testlauf\n\n")
    f.write(f"- **Embedding-Modell**: {metadata.get('embedding_model', 'unknown')}\n")
    f.write(f"- **LLM-Modell**: {metadata.get('llm_model', 'unknown')}\n")
    f.write(f"- **Device**: {metadata.get('device', 'unknown')}\n\n")
    f.write("> Antworten aus dem ersten Lauf, kein Cherry-Picking.\n\n")
    f.write("---\n")


def save_result(f, question, duration, res, status_code):
    """Saves a single result or an error to the file."""
    f.write(f"\n#### {question}\n\n")
    f.write(f"Status: `{status_code}` | Dauer: `{duration}s`\n\n")
    f.write("```json\n")
    # If the response was successful, format the answer and sources
    if status_code == 200:
        f.write(res.get("answer", "No answer provided.") + "\n\n")
        f.write("🔗 Quellen:\n")
        sources = res.get("sources", [])
        if sources:
            for src in sources:
                f.write(f"- {src}\n")
        else:
            f.write("- Keine Quellen gefunden.\n")
    # If there was an error, just write the error detail
    else:
        f.write(f"ERROR: {res.get('detail', 'An unknown error occurred.')}\n")
    f.write("```\n")
    f.write("\n---\n")
    f.flush()


def run_tests():
    """Main testing routine."""
    metadata = get_metadata()
    if not metadata:
        print("Aborting tests due to failed metadata fetch.")
        return

    questions = extract_questions(MARKDOWN_FILE)
    if not questions:
        print("Aborting tests because no questions were found.")
        return

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    result_file = f"test_results_{timestamp}.md"

    with open(result_file, "w", encoding="utf-8") as f:
        write_header(f, metadata)

        for i, q in enumerate(questions):
            print(f"🔍 Frage {i+1}/{len(questions)}: {q}")
            start_time = time.time()
            res, status_code = query_api(q)
            duration = round(time.time() - start_time, 2)
            save_result(f, q, duration, res, status_code)

    print(f"\n✅ Test abgeschlossen. Ergebnisse gespeichert in: {result_file}")


if __name__ == "__main__":
    run_tests()
