"""Diagnostic script: confirms which Settings class and file is actually imported."""
import sys
import os

# Run from backend/ directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings
import inspect

print("=== Settings Diagnostics ===")
print(f"Class name:   {settings.__class__.__name__}")
print(f"Class module: {settings.__class__.__module__}")

# Find the source file of the Settings class
try:
    src_file = inspect.getfile(settings.__class__)
    print(f"Source file:  {src_file}")
except Exception as e:
    print(f"Source file:  UNKNOWN ({e})")

# Check pyc vs py
import importlib.util
spec = importlib.util.find_spec("app.core.config")
if spec:
    print(f"Module origin: {spec.origin}")

# Check for the methods
print()
print(f"hasattr(settings, 'get_ai_api_key')   = {hasattr(settings, 'get_ai_api_key')}")
print(f"hasattr(settings, 'get_ai_base_url')  = {hasattr(settings, 'get_ai_base_url')}")
print(f"hasattr(settings, 'get_ai_model')     = {hasattr(settings, 'get_ai_model')}")
print(f"hasattr(settings, 'is_ai_configured') = {hasattr(settings, 'is_ai_configured')}")
print(f"hasattr(settings, 'get_xai_api_key')  = {hasattr(settings, 'get_xai_api_key')}")

# If get_ai_api_key exists, test safe invocation
if hasattr(settings, 'get_ai_api_key'):
    key = settings.get_ai_api_key()
    masked = key[:8] + "..." if len(key) > 8 else ("[EMPTY]" if not key else "[SET]")
    print(f"\nget_ai_api_key() masked result: {masked}")
    print(f"get_ai_model():                 {settings.get_ai_model() or '[EMPTY]'}")
    print(f"get_ai_base_url():              {settings.get_ai_base_url()}")
    print(f"is_ai_configured():             {settings.is_ai_configured()}")
else:
    print("\nMethods NOT FOUND — listing all public methods on Settings:")
    for name in sorted(dir(settings)):
        if not name.startswith("_") and callable(getattr(settings, name, None)):
            print(f"  {name}()")

# Check for __pycache__ compiled file
import pathlib
pycache_dir = pathlib.Path(__file__).parent / "app" / "core" / "__pycache__"
print(f"\n__pycache__ exists: {pycache_dir.exists()}")
if pycache_dir.exists():
    pycs = list(pycache_dir.glob("config*.pyc"))
    print(f"Compiled .pyc files: {[str(p.name) for p in pycs]}")
    for pyc in pycs:
        import struct, time
        data = pyc.read_bytes()
        if len(data) >= 16:
            mtime = struct.unpack_from("<I", data, 8)[0] if len(data) > 8 else 0
            print(f"  {pyc.name}: bytecode mtime={mtime} ({time.ctime(mtime)})")

