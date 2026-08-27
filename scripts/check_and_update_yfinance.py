#!/usr/bin/env python3
"""
yfinance Version Checker and Auto-Rebuild Utility
Checks if a newer version of yfinance exists on PyPI.
Returns exit code 0 if up-to-date, or exit code 10 if an update is available.
"""

import sys
import json
import urllib.request
import argparse
import subprocess
from packaging import version


def get_latest_pypi_version(package_name="yfinance") -> str:
    """Fetch the latest version of a package from PyPI JSON API."""
    url = f"https://pypi.org/pypi/{package_name}/json"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ai-hedge-fund-yfinance-checker/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                return data["info"]["version"]
    except Exception as e:
        print(f"❌ Failed to fetch latest version from PyPI: {e}", file=sys.stderr)
    return None


def get_current_installed_version(package_name="yfinance", container_name=None) -> str:
    """Get the currently installed version locally or inside a running Docker container."""
    if container_name:
        try:
            cmd = ["docker", "exec", container_name, "venv/bin/python", "-c", f"import {package_name}; print({package_name}.__version__)"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass

    try:
        import yfinance
        return yfinance.__version__
    except ImportError:
        pass

    try:
        import importlib.metadata
        return importlib.metadata.version(package_name)
    except Exception:
        pass

    return "0.0.0"


def main():
    parser = argparse.ArgumentParser(description="Check and manage yfinance version updates for ai-hedge-fund-API")
    parser.add_argument("--container", "-c", default="nice_jemison", help="Docker container name to inspect (default: nice_jemison)")
    parser.add_argument("--json", action="store_true", help="Output result as JSON")
    args = parser.parse_args()

    latest_ver = get_latest_pypi_version("yfinance")
    current_ver = get_current_installed_version("yfinance", container_name=args.container)

    if not latest_ver:
        print("⚠️ Could not verify latest version on PyPI.", file=sys.stderr)
        sys.exit(1)

    has_update = version.parse(latest_ver) > version.parse(current_ver)

    result = {
        "package": "yfinance",
        "current_version": current_ver,
        "latest_version": latest_ver,
        "has_update": has_update
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"📦 Package: yfinance")
        print(f"🔹 Installed Version : {current_ver}")
        print(f"🔹 Latest PyPI Version: {latest_ver}")
        if has_update:
            print(f"🚀 New version available! ({current_ver} -> {latest_ver})")
        else:
            print("✅ yfinance is up to date!")

    # Exit with code 10 if an update is available (useful for bash scripts)
    if has_update:
        sys.exit(10)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
