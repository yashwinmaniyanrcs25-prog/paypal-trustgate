"""Script to clear all __pycache__ directories in the backend."""
import shutil
import pathlib

backend_root = pathlib.Path(__file__).parent

removed = []
for cache_dir in backend_root.rglob("__pycache__"):
    try:
        shutil.rmtree(cache_dir)
        removed.append(str(cache_dir))
    except Exception as e:
        print(f"WARNING: Could not remove {cache_dir}: {e}")

print(f"Cleared {len(removed)} __pycache__ directories:")
for d in removed:
    print(f"  {d}")

print("\nDone. Re-run diagnose_config.py to verify.")

