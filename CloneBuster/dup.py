import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path


def hash_file(filepath: Path) -> str:
    """Compute SHA-256 hash of a file's content only (no metadata)."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def hash_directory(dirpath: Path) -> str:
    """Compute a combined SHA-256 hash of all file contents within a directory.
    
    Sorts files by relative path for order-independent comparison,
    then hashes each file's content hash concatenated together.
    """
    h = hashlib.sha256()
    all_files = []
    for root, _dirs, filenames in os.walk(dirpath):
        for fn in filenames:
            full = Path(root) / fn
            rel = full.relative_to(dirpath)
            all_files.append((str(rel), full))

    # Sort by relative path for consistent ordering
    all_files.sort(key=lambda x: x[0])

    for rel_path, full_path in all_files:
        # Include the relative path in the hash to distinguish file structure
        h.update(rel_path.encode("utf-8"))
        h.update(hash_file(full_path).encode("utf-8"))

    return h.hexdigest()


def longest_common_prefix(names: list[str]) -> str:
    """Find the longest common prefix of a list of strings."""
    if not names:
        return ""
    prefix = names[0]
    for name in names[1:]:
        while not name.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    # Strip trailing whitespace, underscores, hyphens, and dots
    return prefix.rstrip(" _-.")


def safe_mkdir(target_dir: Path, name: str) -> Path:
    """Create a directory with collision handling (_1, _2, etc.)."""
    dest = target_dir / name
    if not dest.exists():
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    counter = 1
    while True:
        new_name = f"{name}_{counter}"
        dest = target_dir / new_name
        if not dest.exists():
            dest.mkdir(parents=True, exist_ok=True)
            return dest
        counter += 1


def find_duplicates(target_dir: Path, deep: bool = False, individual: bool = False) -> None:
    print("\n╔══════════════════════════════════════════════╗")
    print("║          DUP — Duplicate Finder              ║")
    print("╚══════════════════════════════════════════════╝")
    print(f"\n  Target directory: {target_dir}\n")

    mode_str = "Files only"
    if deep and individual:
        mode_str = "Deep + Individual (files inside subdirs)"
    elif deep:
        mode_str = "Deep (subdirs as single objects)"
    print(f"  Mode: {mode_str}\n")
    print("  ⏳  Hashing files…\n")

    # Collect items and compute hashes
    hash_map: dict[str, list[Path]] = {}

    # --- Hash top-level files ---
    for entry in sorted(target_dir.iterdir()):
        if entry.is_file():
            try:
                file_hash = hash_file(entry)
                hash_map.setdefault(file_hash, []).append(entry)
            except (PermissionError, OSError) as e:
                print(f"  ⚠  Skipped {entry.name}: {e}")

    # --- Handle subdirectories based on mode ---
    if deep:
        if individual:
            # Deep + Individual: go into each subdir and hash files separately
            for entry in sorted(target_dir.iterdir()):
                if entry.is_dir():
                    for root, _dirs, filenames in os.walk(entry):
                        for fn in filenames:
                            f = Path(root) / fn
                            try:
                                file_hash = hash_file(f)
                                hash_map.setdefault(file_hash, []).append(f)
                            except (PermissionError, OSError) as e:
                                print(f"  ⚠  Skipped {f.name}: {e}")
        else:
            # Deep (default): treat each subdir as a single object
            for entry in sorted(target_dir.iterdir()):
                if entry.is_dir():
                    try:
                        dir_hash = hash_directory(entry)
                        hash_map.setdefault(dir_hash, []).append(entry)
                    except (PermissionError, OSError) as e:
                        print(f"  ⚠  Skipped directory {entry.name}: {e}")

    # Filter to only duplicate groups (2+ items with same hash)
    duplicate_groups = {h: items for h, items in hash_map.items() if len(items) >= 2}

    if not duplicate_groups:
        print("  ✅  No duplicates found!\n")
        input("  Press Enter to exit...")
        return

    total_groups = len(duplicate_groups)
    total_items = sum(len(items) for items in duplicate_groups.values())
    print(f"  Found {total_groups} duplicate group(s) ({total_items} items total).\n")

    moved = 0

    for group_hash, items in duplicate_groups.items():
        # Get names (stems for files, names for dirs)
        names = []
        for item in items:
            if item.is_file():
                names.append(item.stem)
            else:
                names.append(item.name)

        # Find common prefix
        common = longest_common_prefix(names)
        if not common:
            # Fallback: use first file's stem
            common = names[0] if names else f"dup_{group_hash[:8]}"

        # Create the group folder
        group_folder = safe_mkdir(target_dir, common)
        print(f"  📂 Group: {group_folder.name}/")

        # Move all duplicates into the folder
        for item in items:
            try:
                dest = group_folder / item.name
                if dest.exists():
                    # Handle name collision within the group folder
                    stem = item.stem
                    suffix = item.suffix
                    counter = 1
                    while dest.exists():
                        dest = group_folder / f"{stem}_{counter}{suffix}"
                        counter += 1
                shutil.move(str(item), str(dest))
                print(f"     ↳ {item.name}")
                moved += 1
            except Exception as e:
                print(f"     ⚠  Failed to move {item.name}: {e}")

    print(f"\n  ✅  Done! {moved} item(s) grouped into {total_groups} folder(s).\n")
    input("  Press Enter to exit...")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dup — Duplicate File Finder (by content hash)",
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to scan for duplicates (default: current dir)",
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Also process subdirectories (default: as single objects)",
    )
    parser.add_argument(
        "--individual",
        action="store_true",
        help="With --deep, treat files inside subdirs individually instead of comparing whole dirs",
    )

    args = parser.parse_args()

    target = Path(args.directory).resolve()
    if not target.is_dir():
        print(f"  ❌  Not a valid directory: {target}")
        sys.exit(1)

    if args.individual and not args.deep:
        print("  ⚠  --individual requires --deep. Enabling --deep automatically.\n")
        args.deep = True

    find_duplicates(target, deep=args.deep, individual=args.individual)


if __name__ == "__main__":
    main()
