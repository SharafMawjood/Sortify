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


def interactive_sort(target_dir: Path, config: dict) -> None:
    print("\n╔══════════════════════════════════════════════╗")
    print("║        SORTIFY — File Routing CLI            ║")
    print("╚══════════════════════════════════════════════╝")
    print(f"\n  Target directory: {target_dir}\n")

    print("  [1] Use default routing (from config.json)")
    print("  [2] Custom target (move everything to one folder)")
    print("  [3] Revert (extract all files from subfolders to a single destination)\n")

    choice = input("  Your choice (1/2/3) [default=2]: ").strip()

    custom_target: Path | None = None
    revert_target: Path | None = None
    
    if choice in ("2", ""):
        raw = input("  Enter the custom destination path: ").strip()
        custom_target = Path(raw)
        custom_target.mkdir(parents=True, exist_ok=True)

        for category_name in config["routing"]:
            (custom_target / category_name).mkdir(parents=True, exist_ok=True)
        print(f"\n  📂  Created category folders inside: {custom_target}")
    elif choice == "3":
        raw = input("  Enter the destination path to revert all files into: ").strip()
        revert_target = Path(raw)
        revert_target.mkdir(parents=True, exist_ok=True)

    flatten = False
    if choice != "3":
        flatten = input("\n  Flatten subfolders? (y/n): ").strip().lower() == "y"

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
                    print(f"  📁 {entry.name}  →  [Folders] {dest}")
                else:
                    cat, dest = sort_folder(entry, config, base_dir=target_dir)
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

            dest = safe_move(filepath, dest_dir)
            print(f"  📄 {filepath.name}  →  [{category}] {dest}")
        else:
            cat, dest = sort_file(filepath, config, base_dir=base_dir)
            print(f"  📄 {filepath.name}  →  [{cat}] {dest}")
        return 1
    except Exception as exc:
        print(f"  ⚠  Failed to move {filepath.name}: {exc}")
        return 0


def sync_sort(config: dict) -> None:
    routing = config["routing"]

    print("\n╔══════════════════════════════════════════════╗")
    print("║         SORTIFY — Sync / Re-Sort             ║")
    print("╚══════════════════════════════════════════════╝\n")

    all_files: list[Path] = []

    for cat, rules in routing.items():
        cat_path = Path(rules["path"])
        if cat_path.is_dir():
            for f in _collect_all_files(cat_path):
                all_files.append(f)

    if not all_files:
        print("  No files found in any routing destination. Nothing to sync.\n")
        return

    print(f"  Found {len(all_files)} file(s) across all destinations.\n")

    moved = 0
    for f in all_files:
        try:
            cat, dest = sort_file(f, config)
            if dest.parent != f.parent:
                print(f"  🔄 {f.name}  →  [{cat}] {dest}")
                moved += 1
        except Exception as exc:
            print(f"  ⚠  Failed to re-sort {f.name}: {exc}")

    for cat, rules in routing.items():
        cat_path = Path(rules["path"])
        if cat_path.is_dir():
            _remove_empty_dirs(cat_path)

    print(f"\n  ✅  Sync complete! {moved} file(s) re-routed.\n")
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
        "--sync",
        action="store_true",
        help="Re-sort all files already in routing destinations",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to a custom config.json (default: config.json next to this script)",
    )

    args = parser.parse_args()
    config = load_config(args.config)

    if args.sync:
        sync_sort(config)
    else:
        target = Path(args.directory).resolve()
        if not target.is_dir():
            print(f"  ❌  Not a valid directory: {target}")
            sys.exit(1)
        interactive_sort(target, config)


if __name__ == "__main__":
    main()
