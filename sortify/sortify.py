import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import load_config, sort_file, sort_folder, safe_move, get_file_metadata, match_category

DEFAULT_CONFIG = Path(__file__).resolve().parent / "config.json"


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
                    print(f"  🗑  Removed empty folder: {dp}")
            except OSError:
                pass


def _is_folders_category(name: str) -> bool:
    return name.lower() in ("folders", "folder")


def _collapse_year_subfolders(folders_dir: Path) -> None:
    for item in list(folders_dir.iterdir()):
        if item.is_dir() and item.name.isdigit() and len(item.name) == 4:
            for child in list(item.iterdir()):
                dest = safe_move(child, folders_dir)
                if dest:
                    print(f"  📂 {child.name}  ←  collapsed from {item.name}/")
            try:
                if item.exists() and not any(item.iterdir()):
                    item.rmdir()
                    print(f"  🗑  Removed year folder: {item}")
            except OSError:
                pass


def interactive_sort(target_dir: Path, config: dict) -> None:
    print("\n╔══════════════════════════════════════════════╗")
    print("║        SORTIFY — File Routing CLI            ║")
    print("╚══════════════════════════════════════════════╝")
    print(f"\n  Target directory: {target_dir}\n")

    print("  [1] Use default routing (from config.json)")
    print("  [2] Custom target (move everything to one folder)")
    print("  [3] Revert (extract all files from subfolders to a single destination)\n")

    choice = input("  Your choice (1/2/3) [default=1]: ").strip()

    if not choice:
        choice = "1"

    custom_target: Path | None = None
    revert_target: Path | None = None
    
    if choice == "2":
        raw = input("  Enter the custom destination path: ").strip().strip('"')
        custom_target = Path(raw)
        custom_target.mkdir(parents=True, exist_ok=True)
        print(f"\n  📂  Custom destination set to: {custom_target}")
    elif choice == "3":
        raw = input("  Enter the destination path to revert all files into: ").strip().strip('"')
        revert_target = Path(raw)
        revert_target.mkdir(parents=True, exist_ok=True)

    flatten = False
    smart_flatten = False
    if choice != "3":
        flatten = input("\n  Flatten subfolders? (y/n) [default=n]: ").strip().lower() == "y"
        if flatten:
            smart_flatten = input("  Use Smart Flatten? (y/n) [default=y]: ").strip().lower() != "n"

    print("\n  ⏳  Processing…\n")

    entries = sorted(target_dir.iterdir())
    moved = 0
    
    if choice == "3":
        # First, revert intact folders from the "Folders" category
        folders_cat = target_dir / "Folders"
        if folders_cat.is_dir():
            for item in folders_cat.iterdir():
                if item.resolve() == revert_target.resolve():
                    continue
                try:
                    dest = safe_move(item, revert_target)
                    if dest:
                        print(f"  ⏪ {item.name}  →  [Reverted Intact] {dest}")
                        moved += 1
                except Exception as exc:
                    print(f"  ⚠  Failed to revert {item.name}: {exc}")

        # Then, revert all individual files from the rest of the structure
        for root, dirs, filenames in os.walk(target_dir):
            root_p = Path(root).resolve()
            rev_p = revert_target.resolve()
            
            # Skip the destination folder to avoid recursion
            if root_p == rev_p or rev_p in root_p.parents:
                dirs.clear()
                continue
                
            # Skip the Folders category as it's already been processed above
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
                        print(f"  ⏪ {f.name}  →  [Reverted] {dest}")
                        moved += 1
                except Exception as exc:
                    print(f"  ⚠  Failed to revert {f.name}: {exc}")
        
        # Clean up the now empty organized folders
        _remove_empty_dirs(target_dir)
        print(f"\n  ✅  Done! {moved} item(s) reverted to {revert_target}.\n")
        input("  Press Enter to exit...")
        return

    for entry in entries:
        if entry.is_file():
            moved += _sort_single_file(entry, config, custom_target, target_dir)

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
                                    print(f"  📁 {item.name}  →  [Folders] {dest}")
                                    moved += 1
                            else:
                                cat, dest = sort_folder(item, config, base_dir=target_dir)
                                if dest:
                                    print(f"  📁 {item.name}  →  [{cat}] {dest}")
                                    moved += 1
                        elif item.is_file():
                            moved += _sort_single_file(item, config, custom_target, target_dir)
                else:
                    # Regular flatten: extract all files
                    for f in _collect_all_files(entry):
                        moved += _sort_single_file(f, config, custom_target, target_dir)
                _remove_empty_dirs(entry)
                try:
                    if entry.exists() and not any(entry.iterdir()):
                        entry.rmdir()
                        print(f"  🗑  Removed empty folder: {entry}")
                except OSError:
                    pass
            else:
                if custom_target:
                    dest_dir = custom_target / "Folders"
                    dest = safe_move(entry, dest_dir)
                    if dest:
                        print(f"  📁 {entry.name}  →  [Folders] {dest}")
                        moved += 1
                else:
                    cat, dest = sort_folder(entry, config, base_dir=target_dir)
                    if dest:
                        print(f"  📁 {entry.name}  →  [{cat}] {dest}")
                        moved += 1

    print(f"\n  ✅  Done! {moved} item(s) routed.\n")
    input("  Press Enter to exit...")


def _sort_single_file(filepath: Path, config: dict, custom_target: Path | None, base_dir: Path | None = None) -> int:
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
                print(f"  📄 {filepath.name}  →  [{category}] {dest}")
                return 1
            return 0
        else:
            cat, dest = sort_file(filepath, config, base_dir=base_dir)
            if dest:
                print(f"  📄 {filepath.name}  →  [{cat}] {dest}")
                return 1
            return 0
    except Exception as exc:
        print(f"  ⚠  Failed to move {filepath.name}: {exc}")
        return 0


def sync_sort(config: dict) -> None:
    routing = config["routing"]

    print("\n╔══════════════════════════════════════════════╗")
    print("║         SORTIFY — Sync / Re-Sort             ║")
    print("╚══════════════════════════════════════════════╝\n")

    all_files: list[Path] = []
    folders_to_sort: list[Path] = []

    for cat, rules in routing.items():
        cat_path = Path(rules["path"])
        if not cat_path.is_dir():
            continue

        if _is_folders_category(cat):
            # Smart Flatten: collapse year subfolders and collect folders as intact units
            _collapse_year_subfolders(cat_path)
            for item in cat_path.iterdir():
                if item.is_dir():
                    folders_to_sort.append(item)
        else:
            for f in _collect_all_files(cat_path):
                all_files.append(f)

    total_items = len(all_files) + len(folders_to_sort)
    if total_items == 0:
        print("  No items found in any routing destination. Nothing to sync.\n")
        return

    print(f"  Found {len(all_files)} file(s) and {len(folders_to_sort)} folder(s) across all destinations.\n")

    moved = 0

    # Re-sort individual files (non-Folders categories)
    for f in all_files:
        try:
            cat, dest = sort_file(f, config)
            if dest and dest.parent != f.parent:
                print(f"  🔄 {f.name}  →  [{cat}] {dest}")
                moved += 1
        except Exception as exc:
            print(f"  ⚠  Failed to re-sort {f.name}: {exc}")

    # Re-sort intact folders (Folders category)
    for folder in folders_to_sort:
        try:
            cat, dest = sort_folder(folder, config)
            if dest and dest.parent != folder.parent:
                print(f"  🔄 📁 {folder.name}  →  [{cat}] {dest}")
                moved += 1
        except Exception as exc:
            print(f"  ⚠  Failed to re-sort folder {folder.name}: {exc}")

    for cat, rules in routing.items():
        cat_path = Path(rules["path"])
        if cat_path.is_dir():
            _remove_empty_dirs(cat_path)

    print(f"\n  ✅  Sync complete! {moved} item(s) re-routed.\n")
    input("  Press Enter to exit...")


def quick_sort(target_dir: Path, config: dict) -> None:
    print("\n╔══════════════════════════════════════════════╗")
    print("║       SORTIFY — Quick Sort (In-Place)        ║")
    print("╚══════════════════════════════════════════════╝")
    print(f"\n  Target directory: {target_dir}\n")
    print("  ⏳  Processing…\n")

    entries = sorted(target_dir.iterdir())
    moved = 0

    for entry in entries:
        if entry.is_file():
            moved += _sort_single_file(entry, config, custom_target=target_dir, base_dir=target_dir)
        elif entry.is_dir():
            dest_dir = target_dir / "Folders"
            dest = safe_move(entry, dest_dir)
            if dest:
                print(f"  📁 {entry.name}  →  [Folders] {dest}")
                moved += 1

    print(f"\n  ✅  Done! {moved} item(s) sorted in-place.\n")
    input("  Press Enter to exit...")


def flat_sort(target_dir: Path) -> None:
    print("\n╔══════════════════════════════════════════════╗")
    print("║       SORTIFY — Flat (Smart Flatten)         ║")
    print("╚══════════════════════════════════════════════╝")
    print(f"\n  Target directory: {target_dir}\n")
    print("  ⏳  Processing…\n")

    moved = 0

    for entry in list(target_dir.iterdir()):
        if not entry.is_dir():
            continue

        if _is_folders_category(entry.name):
            # Smart Flatten: collapse year subfolders, then move original folders up
            _collapse_year_subfolders(entry)
            for item in list(entry.iterdir()):
                dest = safe_move(item, target_dir)
                if dest:
                    if item.is_dir():
                        print(f"  📁 {item.name}  ←  extracted from {entry.name}/")
                    else:
                        print(f"  📄 {item.name}  ←  extracted from {entry.name}/")
                    moved += 1
            # Remove the now-empty Folders container
            try:
                if entry.exists() and not any(entry.iterdir()):
                    entry.rmdir()
                    print(f"  🗑  Removed container: {entry.name}/")
            except OSError:
                pass
        else:
            # Regular flatten: extract all files from subfolders
            for f in _collect_all_files(entry):
                dest = safe_move(f, target_dir)
                if dest:
                    print(f"  📄 {f.name}  ←  extracted from {entry.name}/")
                    moved += 1
            _remove_empty_dirs(entry)
            try:
                if entry.exists() and not any(entry.iterdir()):
                    entry.rmdir()
                    print(f"  🗑  Removed empty folder: {entry.name}/")
            except OSError:
                pass

    print(f"\n  ✅  Done! {moved} item(s) flattened.\n")
    input("  Press Enter to exit...")

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sortify — Logic-Gate File Routing CLI",
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to sort (default: current dir)",
    )
    parser.add_argument(
        "--sync-default",
        action="store_true",
        help="Re-sort all files already in routing destinations",
    )
    parser.add_argument(
        "--quick-sort",
        action="store_true",
        help="Sort files in-place within the target directory (creates category subfolders)",
    )
    parser.add_argument(
        "--flat",
        action="store_true",
        help="Flatten all subfolders in-place (Smart Flatten: keeps original folders from Folders/ intact)",
    )
    parser.add_argument(
        "--custom-config",
        default=str(DEFAULT_CONFIG),
        help="Path to a custom config.json (default: config.json next to this script)",
    )
    parser.add_argument(
        "--config",
        action="store_true",
        help="Open the configuration file in the default editor",
    )

    args = parser.parse_args()
    
    if args.config:
        config_path = Path(args.custom_config).resolve()
        print(f"\n  📂  Opening configuration file: {config_path}")
        try:
            os.startfile(config_path)
            sys.exit(0)
        except Exception as e:
            print(f"  ❌  Failed to open config: {e}")
            sys.exit(1)

    config = load_config(args.custom_config)

    if args.sync_default:
        sync_sort(config)
    elif args.quick_sort:
        target = Path(args.directory).resolve()
        if not target.is_dir():
            print(f"  ❌  Not a valid directory: {target}")
            sys.exit(1)
        quick_sort(target, config)
    elif args.flat:
        target = Path(args.directory).resolve()
        if not target.is_dir():
            print(f"  ❌  Not a valid directory: {target}")
            sys.exit(1)
        flat_sort(target)
    else:
        target = Path(args.directory).resolve()
        if not target.is_dir():
            print(f"  ❌  Not a valid directory: {target}")
            sys.exit(1)
        interactive_sort(target, config)


if __name__ == "__main__":
    main()
