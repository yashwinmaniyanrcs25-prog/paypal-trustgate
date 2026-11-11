"""
One-shot repair script for Task 3.2A.1.

Clears stale __pycache__ bytecode, verifies the config.py on disk
has all required methods, and runs a quick introspection check.

Run from the backend/ directory:
    python fix_config_cache.py
"""
import sys
import os
import shutil
import pathlib
import ast

backend_root = pathlib.Path(__file__).parent

# ---------------------------------------------------------------------------
# 1. Clear all __pycache__ directories
# ---------------------------------------------------------------------------
print("Step 1: Clearing __pycache__ bytecode...")
removed = []
for cache_dir in backend_root.rglob("__pycache__"):
    try:
        shutil.rmtree(cache_dir)
        removed.append(str(cache_dir.relative_to(backend_root)))
    except Exception as e:
        print(f"  WARNING: Could not remove {cache_dir}: {e}")

if removed:
    print(f"  Removed {len(removed)} cache directories:")
    for d in removed:
        print(f"    {d}")
else:
    print("  No __pycache__ directories found.")

# ---------------------------------------------------------------------------
# 2. Parse config.py with AST to verify method definitions without importing
# ---------------------------------------------------------------------------
print("\nStep 2: Verifying config.py method definitions (AST parse, no import)...")
config_path = backend_root / "app" / "core" / "config.py"

if not config_path.exists():
    print(f"  CRITICAL: {config_path} not found!")
    sys.exit(1)

source = config_path.read_text(encoding="utf-8")
tree = ast.parse(source)

required_methods = {
    "get_ai_api_key", "get_ai_base_url", "get_ai_model",
    "is_ai_configured", "get_xai_api_key", "get_xai_model", "get_xai_base_url",
}

found_methods = set()
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == "Settings":
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                found_methods.add(item.name)

present = required_methods & found_methods
missing = required_methods - found_methods

for m in sorted(present):
    print(f"  [OK]     def {m}() — present in Settings class")
for m in sorted(missing):
    print(f"  [ERROR]  def {m}() — MISSING from Settings class")

if missing:
    print(f"\n  CRITICAL: {len(missing)} required methods are MISSING.")
    print("  The source file must be repaired before proceeding.")
    sys.exit(2)
else:
    print(f"\n  All {len(required_methods)} required methods are present in source.")

# ---------------------------------------------------------------------------
# 3. Import fresh and introspect
# ---------------------------------------------------------------------------
print("\nStep 3: Importing Settings (fresh, no cached bytecode)...")
sys.path.insert(0, str(backend_root))

try:
    from app.core.config import settings
    import inspect
    src_file = inspect.getfile(settings.__class__)
    print(f"  Class:       {settings.__class__.__name__}")
    print(f"  Module:      {settings.__class__.__module__}")
    print(f"  Source file: {src_file}")
except Exception as e:
    print(f"  IMPORT ERROR: {e}")
    sys.exit(3)

checks = [
    ("get_ai_api_key", "method"),
    ("get_ai_base_url", "method"),
    ("get_ai_model", "method"),
    ("is_ai_configured", "method"),
    ("get_xai_api_key", "compat alias"),
]
all_ok = True
for attr, label in checks:
    present = hasattr(settings, attr)
    status = "[OK] " if present else "[FAIL]"
    print(f"  {status} hasattr(settings, '{attr}') = {present}  ({label})")
    if not present:
        all_ok = False

# ---------------------------------------------------------------------------
# 4. Safe functional check
# ---------------------------------------------------------------------------
if all_ok:
    print("\nStep 4: Functional verification (no credentials printed)...")
    key = settings.get_ai_api_key()
    model = settings.get_ai_model()
    base_url = settings.get_ai_base_url()
    configured = settings.is_ai_configured()

    masked_key = key[:8] + "***" if len(key) > 8 else ("[EMPTY]" if not key else "[SET-SHORT]")
    print(f"  get_ai_api_key()   → {masked_key}")
    print(f"  get_ai_model()     → {model or '[EMPTY — set AI_MODEL in .env]'}")
    print(f"  get_ai_base_url()  → {base_url}")
    print(f"  is_ai_configured() → {configured}")

# ---------------------------------------------------------------------------
# 5. Summary
# ---------------------------------------------------------------------------
print()
if all_ok:
    print("=" * 60)
    print("SUCCESS: config.py is correct. __pycache__ cleared.")
    print("You can now run:")
    print("  python -m pytest tests/test_intent_interpreter.py -v")
    print("  python -m pytest tests/test_full_purchase_lifecycle.py -v")
    print("=" * 60)
else:
    print("=" * 60)
    print("FAILURE: Some methods are missing even after cache clear.")
    print("The source file needs repair.")
    print("=" * 60)
    sys.exit(4)

