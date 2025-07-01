import asyncio
import json
import logging
from pathlib import Path

from rich.progress import (
    BarColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.text import Text
from rich.pretty import Pretty

log = logging.getLogger(__name__)


class TimePerItemColumn(ProgressColumn):
    """Renders the average time taken to process one item."""

    def render(self, task: "Task") -> Text:
        """Calculate and render the time per item."""
        if not task.completed:
            return Text("-", style="cyan")

        time_per_item = task.elapsed / task.completed
        return Text(f"Ø {round(time_per_item)}s", style="cyan")


class EstimatedTimeRemainingColumn(ProgressColumn):
    """Renders the estimated time remaining based on time per item."""

    def render(self, task: "Task") -> Text:
        """Calculate and render the estimated time remaining."""
        if (
            task.total is None
            or task.completed is None
            or task.elapsed is None
            or task.completed == 0
        ):
            return Text("ETA -", style="cyan")

        remaining_items = task.total - task.completed
        if remaining_items <= 0:
            return Text("ETA 0s", style="cyan")

        time_per_item = task.elapsed / task.completed
        estimated_remaining_time = time_per_item * remaining_items

        if estimated_remaining_time < 60:
            return Text(f"ETA {round(estimated_remaining_time)}s", style="cyan")
        elif estimated_remaining_time < 3600:
            minutes = estimated_remaining_time / 60
            return Text(f"ETA {round(minutes)}m", style="cyan")
        else:
            hours = estimated_remaining_time / 3600
            return Text(f"ETA {round(hours)}h", style="cyan")


async def monitor_progress(
    progress: Progress, task_id, status_file_path: Path, main_task: asyncio.Task
):
    """Watches the doc_status.json file and updates the progress bar's completion."""
    last_processed_count = 0
    while not main_task.done():
        await asyncio.sleep(0.5)
        try:
            if status_file_path.exists():
                with open(status_file_path, "r") as f:
                    status_data = json.load(f)
                processed_count = sum(
                    1 for item in status_data.values() if item.get("status") == "processed"
                )
                if processed_count > last_processed_count:
                    total_items = len(status_data)
                    progress.update(task_id, completed=processed_count, total=total_items)
                    last_processed_count = processed_count
        except (json.JSONDecodeError, FileNotFoundError):
            continue
        except Exception as e:
            log.error(f"Error in progress monitor: {e}")


def get_kg_progress_bar() -> Progress:
    """Returns a pre-configured Rich Progress bar for the KG building process."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[green]Building KG..."),
        BarColumn(),
        TextColumn("[bold blue]{task.completed}/{task.total} chunks"),
        TextColumn("•"),
        TimePerItemColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("•"),
        EstimatedTimeRemainingColumn(),
    )
