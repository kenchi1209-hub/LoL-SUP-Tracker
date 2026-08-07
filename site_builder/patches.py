"""Patch表示の正規化。"""

import re


def normalize_patch(value):
    match = re.match(r"^(\d+)\.(\d+)", str(value or "").strip())
    return f"{int(match.group(1))}.{int(match.group(2))}" if match else "Unknown"
