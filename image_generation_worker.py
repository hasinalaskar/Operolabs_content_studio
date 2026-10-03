import json
import os
import sys
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

FLOW_ENGINE_DIR = Path(r"C:\Users\hasin\OneDrive\Desktop\Flow Image generation")
PROJECTS_ROOT = Path(r"C:\Users\hasin\OperoLabs-Content-Studio\generated_images")

if str(FLOW_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(FLOW_ENGINE_DIR))

from flow_engine import generate_images


def image_path_for_prompt(folder, item):
    return folder / f"{str(item['start']).replace(':', '.')}.jpg"


def status_path(folder):
    return folder / ".image_generation_status.json"


def read_status(folder):
    path = status_path(folder)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_status(folder, data):
    path = status_path(folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)




def main():
    if len(sys.argv) < 2:
        raise RuntimeError("Project folder name was not supplied.")

    folder_name = sys.argv[1]
    output_folder = PROJECTS_ROOT / folder_name
    project_file = output_folder / "project.json"

    if not project_file.exists():
        raise RuntimeError(f"Project file not found: {project_file}")

    data = json.loads(project_file.read_text(encoding="utf-8"))
    all_prompts = data.get("visual_prompts", []) or []
    total_all = len(all_prompts)

    remaining_with_index = [
        (index, item)
        for index, item in enumerate(all_prompts, start=1)
        if not image_path_for_prompt(output_folder, item).exists()
    ]

    completed_before = total_all - len(remaining_with_index)
    remaining_prompts = [item for _, item in remaining_with_index]

    status = read_status(output_folder)
    status.update({
        "worker_type": "process",
        "status": "running",
        "pid": os.getpid(),
        "folder_name": folder_name,
        "total": total_all,
        "completed_before": completed_before,
        "completed_overall": completed_before,
        "remaining_total": len(remaining_prompts),
        "completed_this_run": 0,
        "current_index": remaining_with_index[0][0] if remaining_with_index else None,
        "current_timestamp": remaining_with_index[0][1].get("start", "") if remaining_with_index else "",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "failed": [],
        "error": None,
        "message": "Starting...",
    })
    write_status(output_folder, status)

    if not remaining_prompts:
        status.update({
            "status": "completed",
            "completed_overall": total_all,
            "completed_this_run": 0,
            "remaining_total": 0,
            "current_index": None,
            "current_timestamp": "",
            "message": "Completed",
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        })
        write_status(output_folder, status)
        return

    flow_prompts = [
        {"timestamp": item["start"], "prompt": item["prompt"]}
        for item in remaining_prompts
    ]

    def update_progress(completed, total, timestamp, message):
        if message == "Completed" and completed > 0 and completed <= len(remaining_with_index):
            original_index = remaining_with_index[completed - 1][0]
        elif completed < len(remaining_with_index):
            original_index = remaining_with_index[completed][0]
        elif remaining_with_index:
            original_index = remaining_with_index[-1][0]
        else:
            original_index = completed

        status_now = read_status(output_folder)
        status_now.update({
            "worker_type": "process",
            "status": "running",
            "pid": os.getpid(),
            "completed_overall": min(completed_before + completed, total_all),
            "completed_this_run": completed,
            "remaining_total": total,
            "current_index": original_index,
            "current_timestamp": timestamp,
            "message": message,
        })
        write_status(output_folder, status_now)

    try:

        failed_prompts = generate_images(
            flow_prompts,
            output_folder,
            progress_callback=update_progress,
        ) or []

        generated_this_run = len(remaining_prompts) - len(failed_prompts)
        completed_count = completed_before + generated_this_run
        final = read_status(output_folder)
        final.update({
            "worker_type": "process",
            "status": "completed",
            "pid": os.getpid(),
            "completed_overall": completed_count,
            "completed_this_run": generated_this_run,
            "remaining_total": len(remaining_prompts),
            "current_index": None,
            "current_timestamp": "",
            "message": "Completed",
            "failed": failed_prompts,
            "error": None,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        })
        write_status(output_folder, final)

    except Exception as error:
        failed_status = read_status(output_folder)
        failed_status.update({
            "worker_type": "process",
            "status": "error",
            "pid": os.getpid(),
            "message": "Error",
            "error": str(error),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        })
        write_status(output_folder, failed_status)
        raise



if __name__ == "__main__":
    main()
