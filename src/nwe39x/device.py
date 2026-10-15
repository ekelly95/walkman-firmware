"""Find a connected NW-E390-series player and read the firmware version it reports."""

from __future__ import annotations

import re
import string
import sys
from dataclasses import dataclass
from pathlib import Path

MODEL = "NW-E390 Series"


@dataclass
class Player:
    root: Path
    version: str


def candidate_roots() -> list[Path]:
    if sys.platform == "win32":
        return [Path(f"{d}:/") for d in string.ascii_uppercase[3:]]
    # /media/WALKMAN, /media/$USER/WALKMAN, /run/media/$USER/WALKMAN1 (udisks adds a number when the
    # name is taken), /Volumes/WALKMAN; never inside the mounted drives themselves.
    return sorted(p for base in (Path("/media"), Path("/run/media"), Path("/Volumes"))
                  if base.exists() for pattern in ("WALKMAN*", "*/WALKMAN*") for p in base.glob(pattern) if p.is_dir())


def read_player(root: Path) -> Player | None:
    cap = root / "default-capability.xml"
    try:
        text = cap.read_text(encoding="iso-8859-1")
    except OSError:
        return None
    if f"<model>{MODEL}</model>" not in text:
        return None
    m = re.search(r"<firmwareversion>([^<]+)</firmwareversion>", text)
    return Player(root, m.group(1).strip()) if m else None


def find_players() -> list[Player]:
    return [p for root in candidate_roots() if (p := read_player(root))]
