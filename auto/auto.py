import argparse
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent

from engine import load_config, sort_file


def _notify(title: str, message: str) -> None:
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="Sortify Auto",
            timeout=5,
        )
    except Exception:
        pass


class SortingHandler(FileSystemEventHandler):

    def __init__(self, config: dict) -> None:
        super().__init__()
        self.config = config

    def _process(self, filepath: str) -> None:
        p = Path(filepath)

        if not p.is_file():
            return
        if p.name.startswith(".") or p.name.startswith("~"):
            return

        time.sleep(1)

        if not p.exists():
            return

        try:
            category, dest = sort_file(p, self.config)
            msg = f"{p.name}  →  [{category}]"
            print(f"  📄 {msg}  ({dest})")
            _notify("Sortify — File Sorted", msg)
        except Exception as exc:
            print(f"  ⚠  Error sorting {p.name}: {exc}")

    def on_created(self, event) -> None:
        if isinstance(event, FileCreatedEvent):
            self._process(event.src_path)

    def on_moved(self, event) -> None:
        if isinstance(event, FileMovedEvent):
            self._process(event.dest_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sortify — Background file monitor",
    )
    default_cfg = Path(__file__).parent / "config.json"
    parser.add_argument(
        "--config",
        default=str(default_cfg),
        help="Path to a custom config file (default: config.json)",
    )
    args = parser.parse_args()
    config = load_config(args.config)

    sources = config.get("monitored_sources", [])
    if not sources:
        print("  ❌  No monitored_sources defined in config.json.")
        sys.exit(1)

    handler = SortingHandler(config)
    observer = Observer()

    print("\n╔══════════════════════════════════════════════╗")
    print("║      SORTIFY — Background File Monitor       ║")
    print("╚══════════════════════════════════════════════╝\n")

    for src in sources:
        src_path = Path(src)
        if not src_path.is_dir():
            print(f"  ⚠  Skipping (not found): {src}")
            continue
        observer.schedule(handler, str(src_path), recursive=False)
        print(f"  👁  Watching: {src_path}")

    print("\n  Press Ctrl+C to stop.\n")

    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  🛑  Stopping watcher…")
        observer.stop()
    observer.join()
    print("  ✅  Watcher stopped.\n")


if __name__ == "__main__":
    main()
