import json
import os
import shutil
import datetime
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config(path: str | Path | None = None) -> dict:
    p = Path(path) if path else CONFIG_PATH
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def get_file_metadata(filepath: str | Path) -> dict:
    p = Path(filepath)
    stat = p.stat()
    size_gb = stat.st_size / (1024 ** 3)

    try:
        ctime = stat.st_birthtime
    except AttributeError:
        ctime = stat.st_ctime

    year = datetime.datetime.fromtimestamp(ctime).year

    return {
        "extension": p.suffix.lower(),
        "size_gb": size_gb,
        "year": year,
    }


def match_category(metadata: dict, routing: dict) -> str:
    for category, rules in routing.items():
        if category in ("Others", "Folders"):
            continue

        if not _rule_matches(metadata, rules):
            continue

        return category

    return "Others"


def _rule_matches(metadata: dict, rules: dict) -> bool:
    extensions = rules.get("extensions", [])
    if extensions:
        if metadata["extension"] not in extensions:
            return False

    year = rules.get("year", False)
    # We no longer filter by year matching. 
    # If year is True, it will be used in sort_file to create a subfolder.

    min_gb = rules.get("min_gb")
    if min_gb is not None:
        if metadata["size_gb"] < min_gb:
            return False

    max_gb = rules.get("max_gb")
    if max_gb is not None:
        if metadata["size_gb"] > max_gb:
            return False

    return True


def safe_move(src: str | Path, dest_dir: str | Path) -> Path:
    src = Path(src)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest = dest_dir / src.name

    if dest.exists():
        stem = src.stem
        suffix = src.suffix
        counter = 1
        while True:
            new_name = f"{stem}_{counter}{suffix}"
            dest = dest_dir / new_name
            if not dest.exists():
                break
            counter += 1

    shutil.move(str(src), str(dest))
    return dest


def sort_file(filepath: str | Path, config: dict, base_dir: str | Path | None = None) -> tuple[str, Path]:
    filepath = Path(filepath)
    if not filepath.is_file():
        raise ValueError(f"Not a file: {filepath}")

    metadata = get_file_metadata(filepath)
    routing = config["routing"]
    category = match_category(metadata, routing)
    dest_dir = Path(routing[category]["path"])
    
    # If the routing rule specifies year=True, create a subfolder for the year
    use_year_subfolder = routing[category].get("year", False)
    if use_year_subfolder:
        dest_dir = dest_dir / str(metadata["year"])

    # If the routing rule specifies file_type=True, create an extension subfolder inside it
    use_type_subfolder = routing[category].get("file_type", False)
    if use_type_subfolder:
        ext = metadata["extension"].lstrip(".")
        ext_folder = ext.upper() if ext else "UNKNOWN"
        dest_dir = dest_dir / ext_folder
        
    if base_dir and not dest_dir.is_absolute():
        dest_dir = Path(base_dir) / dest_dir
    final = safe_move(filepath, dest_dir)
    return category, final


def sort_folder(folderpath: str | Path, config: dict, base_dir: str | Path | None = None) -> tuple[str, Path]:
    folderpath = Path(folderpath)
    if not folderpath.is_dir():
        raise ValueError(f"Not a directory: {folderpath}")

    routing = config["routing"]
    if "Folders" not in routing:
        raise KeyError("No 'Folders' category defined in config.json")

    dest_dir = Path(routing["Folders"]["path"])
    if base_dir and not dest_dir.is_absolute():
        dest_dir = Path(base_dir) / dest_dir
    final = safe_move(folderpath, dest_dir)
    return "Folders", final
