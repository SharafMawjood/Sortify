import os
import sys
import eel
from pathlib import Path

# Add the parent directory of 'sortify' to sys.path to import engine
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from engine import load_config, sort_file, sort_folder, safe_move, get_file_metadata, match_category

# Set web files folder
eel.init('UI')

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

def _collect_all_files(directory: Path) -> list[Path]:
    files = []
    for root, _dirs, filenames in os.walk(directory):
        for fn in filenames:
            files.append(Path(root) / fn)
    return files

def _remove_empty_dirs(directory: Path) -> None:
    for root, dirs, _files in os.walk(str(directory), topdown=False):
        for d in dirs:
            dp = Path(root) / d
            try:
                if not any(dp.iterdir()):
                    dp.rmdir()
            except OSError:
                pass

def _is_folders_category(name: str) -> bool:
    return name.lower() in ("folders", "folder")

def _collapse_year_subfolders(folders_dir: Path) -> None:
    for item in list(folders_dir.iterdir()):
        if item.is_dir() and item.name.isdigit() and len(item.name) == 4:
            for child in list(item.iterdir()):
                dest = safe_move(child, folders_dir)
            try:
                if item.exists() and not any(item.iterdir()):
                    item.rmdir()
            except OSError:
                pass

def _sort_single_file(filepath: Path, config: dict, custom_target: Path | None, base_dir: Path | None = None) -> dict:
    result = {"name": filepath.name, "success": False, "category": "Error", "dest": None, "error": None}
    try:
        if custom_target:
            metadata = get_file_metadata(filepath)
            category = match_category(metadata, config["routing"])
            dest_dir = custom_target / category
            use_year_subfolder = config["routing"].get(category, {}).get("year", False)
            if use_year_subfolder:
                dest_dir = dest_dir / str(metadata["year"])

            file_type_setting = config["routing"].get(category, {}).get("file_type", 0)
            
            if file_type_setting == 1:
                ext = metadata["extension"].lstrip(".")
                ext_folder = ext.upper() if ext else "UNKNOWN"
                dest_dir = dest_dir / ext_folder
                
            elif file_type_setting == 2:
                ext = metadata["extension"]
                file_groups = config["routing"].get(category, {}).get("extensions", {})
                group_folder = "Other Types"
                
                if isinstance(file_groups, dict):
                    for group_name, exts in file_groups.items():
                        if ext in exts:
                            group_folder = group_name
                            break
                        
                dest_dir = dest_dir / group_folder

            dest = safe_move(filepath, dest_dir)
            if dest:
                result.update({"success": True, "category": category, "dest": str(dest)})
        else:
            cat, dest = sort_file(filepath, config, base_dir=base_dir)
            if dest:
                result.update({"success": True, "category": cat, "dest": str(dest)})
    except Exception as exc:
        result["error"] = str(exc)
        
    return result
    
@eel.expose
def open_config():
    try:
        os.startfile(DEFAULT_CONFIG_PATH)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def api_sort(target_dir_str, mode, custom_target_str, flatten, smart_flatten=True):
    target_dir_str = target_dir_str.strip().strip('"')
    mode = mode or "default"
    custom_target_str = custom_target_str.strip().strip('"')
    
    if not target_dir_str:
        return {"error": "Target directory is required."}
        
    target_dir = Path(target_dir_str)
    if not target_dir.is_dir():
        return {"error": "Invalid target directory."}
        
    try:
        config = load_config(DEFAULT_CONFIG_PATH)
    except Exception as e:
        return {"error": f"Failed to load config: {e}"}

    custom_target = None
    revert_target = None
    
    if mode == "custom":
        if not custom_target_str:
            return {"error": "Custom destination path is required when mode is 'custom'."}
        custom_target = Path(custom_target_str)
        custom_target.mkdir(parents=True, exist_ok=True)
    elif mode == "revert":
        if not custom_target_str:
            return {"error": "Destination path is required when mode is 'revert'."}
        revert_target = Path(custom_target_str)
        revert_target.mkdir(parents=True, exist_ok=True)

    entries = sorted(target_dir.iterdir())
    moved_count = 0
    logs = []
    
    if mode == "revert":
        folders_cat = target_dir / "Folders"
        if folders_cat.is_dir():
            for item in folders_cat.iterdir():
                if item.resolve() == revert_target.resolve():
                    continue
                try:
                    dest = safe_move(item, revert_target)
                    if dest:
                        logs.append({"name": item.name, "action": "Reverted Intact", "dest": str(dest), "success": True})
                        moved_count += 1
                except Exception as exc:
                     logs.append({"name": item.name, "action": "Error", "error": str(exc), "success": False})

        for root, dirs, filenames in os.walk(target_dir):
            root_p = Path(root).resolve()
            rev_p = revert_target.resolve()
            
            if root_p == rev_p or rev_p in root_p.parents:
                dirs.clear()
                continue
                
            if folders_cat.is_dir():
                fcat_p = folders_cat.resolve()
                if root_p == fcat_p or fcat_p in root_p.parents:
                    dirs.clear()
                    continue
                    
            for fn in filenames:
                f = Path(root) / fn
                try:
                    dest = safe_move(f, revert_target)
                    if dest:
                        logs.append({"name": f.name, "action": "Reverted", "dest": str(dest), "success": True})
                        moved_count += 1
                except Exception as exc:
                     logs.append({"name": f.name, "action": "Error", "error": str(exc), "success": False})
        
        _remove_empty_dirs(target_dir)
        return {"message": f"Successfully reverted {moved_count} items.", "logs": logs, "moved_count": moved_count}

    for entry in entries:
        if entry.is_file():
            res = _sort_single_file(entry, config, custom_target, target_dir)
            if res["success"]:
                moved_count += 1
            logs.append(res)
        elif entry.is_dir():
            if flatten:
                if smart_flatten and _is_folders_category(entry.name):
                    # Smart Flatten: collapse year subfolders but keep original folders intact
                    _collapse_year_subfolders(entry)
                    for item in list(entry.iterdir()):
                        if item.is_dir():
                            if custom_target:
                                dest_dir = custom_target / "Folders"
                                dest = safe_move(item, dest_dir)
                                if dest:
                                    moved_count += 1
                                    logs.append({"name": item.name, "success": True, "category": "Folders", "dest": str(dest)})
                            else:
                                try:
                                    cat, dest = sort_folder(item, config, base_dir=target_dir)
                                    if dest:
                                        moved_count += 1
                                        logs.append({"name": item.name, "success": True, "category": cat, "dest": str(dest)})
                                except Exception as e:
                                    logs.append({"name": item.name, "success": False, "category": "Error", "error": str(e)})
                        elif item.is_file():
                            res = _sort_single_file(item, config, custom_target, target_dir)
                            if res["success"]:
                                moved_count += 1
                            logs.append(res)
                else:
                    # Regular flatten: extract all files
                    for f in _collect_all_files(entry):
                        res = _sort_single_file(f, config, custom_target, target_dir)
                        if res["success"]:
                            moved_count += 1
                        logs.append(res)
                _remove_empty_dirs(entry)
                try:
                    if entry.exists() and not any(entry.iterdir()):
                        entry.rmdir()
                except OSError:
                    pass
            else:
                if custom_target:
                    dest_dir = custom_target / "Folders"
                    dest = safe_move(entry, dest_dir)
                    if dest:
                        moved_count += 1
                        logs.append({"name": entry.name, "success": True, "category": "Folders", "dest": str(dest)})
                else:
                    try:
                        cat, dest = sort_folder(entry, config, base_dir=target_dir)
                        if dest:
                            moved_count += 1
                            logs.append({"name": entry.name, "success": True, "category": cat, "dest": str(dest)})
                    except Exception as e:
                        logs.append({"name": entry.name, "success": False, "category": "Error", "error": str(e)})

    return {"message": f"Successfully moved {moved_count} items.", "logs": logs, "moved_count": moved_count}

if __name__ == '__main__':
    eel.start('index.html', size=(900, 700), mode='edge', port=0) # Use dynamic port to avoid conflicts
