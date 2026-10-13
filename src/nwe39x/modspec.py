"""A mod is a folder. With a `mod.toml` it says what it holds and what it builds on:

    name = "my-walkman"
    include = ["../theme-dark", "../font-terminus"]   # other mods, applied first, in order
    theme = "mono"                                    # a themes preset, applied to the stock pictures
    hue = 200                                         # with theme = "hue"
    images = ["images"]                               # folders of NNN.png (later folders win)
    fonts = ["fonts"]                                 # folders of glyph sheets
    strings = ["strings.tsv"]
    patches = ["patches.tsv"]

Paths are relative to the folder. Without a mod.toml the folder's own images/, fonts/,
strings.tsv and patches.tsv are used, so the old layout still works. `build --mod` applies
includes depth-first, then the mod's own pieces in the order theme, images, fonts, strings, patches.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import fonts, imageres, patches, strtbl, themes
from .rknanofw import Firmware, FirmwareError


@dataclass
class Mod:
    path: Path
    name: str
    include: list[Mod] = field(default_factory=list)
    theme: str | None = None
    hue: float | None = None
    images: list[Path] = field(default_factory=list)
    fonts: list[Path] = field(default_factory=list)
    strings: list[Path] = field(default_factory=list)
    patches: list[Path] = field(default_factory=list)

    def all_patch_files(self) -> list[Path]:
        return [f for m in self.include for f in m.all_patch_files()] + list(self.patches)

    def describe(self, depth: int = 0) -> str:
        pad = "  " * depth
        bits = [b for b in (f"theme {self.theme}" if self.theme else "", f"{len(self.images)} image folder(s)" if self.images else "",
                            f"{len(self.fonts)} font folder(s)" if self.fonts else "", "strings" if self.strings else "",
                            f"{len(self.patches)} patch file(s)" if self.patches else "") if b]
        lines = [f"{pad}{self.name}: " + (", ".join(bits) or "(nothing of its own)")]
        lines += [m.describe(depth + 1) for m in self.include]
        return "\n".join(lines)


def load(path: Path, _seen: tuple[Path, ...] = ()) -> Mod:
    path = Path(path).resolve()
    if not path.is_dir():
        raise FirmwareError(f"{path} is not a mod folder")
    if path in _seen:
        raise FirmwareError(f"mod {path.name} includes itself")
    toml = path / "mod.toml"
    if not toml.is_file():
        return Mod(path, path.name,
                   images=[path / "images"] if (path / "images").is_dir() else [],
                   fonts=[path / "fonts"] if (path / "fonts").is_dir() else [],
                   strings=[path / "strings.tsv"] if (path / "strings.tsv").is_file() else [],
                   patches=[path / "patches.tsv"] if (path / "patches.tsv").is_file() else [])
    try:
        spec = tomllib.loads(toml.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise FirmwareError(f"{toml}: {e}") from None
    unknown = set(spec) - {"name", "include", "theme", "hue", "images", "fonts", "strings", "patches"}
    if unknown:
        raise FirmwareError(f"{toml}: unknown keys {', '.join(sorted(unknown))}")

    def paths(key: str, must: str) -> list[Path]:
        out = []
        for p in spec.get(key, []):
            q = (path / p).resolve()
            if (must == "dir" and not q.is_dir()) or (must == "file" and not q.is_file()):
                raise FirmwareError(f"{toml}: {key} entry {p} not found (generate it first?)")
            out.append(q)
        return out

    return Mod(path, spec.get("name", path.name),
               include=[load(path / inc, _seen + (path,)) for inc in spec.get("include", [])],
               theme=spec.get("theme"), hue=spec.get("hue"),
               images=paths("images", "dir"), fonts=paths("fonts", "dir"),
               strings=paths("strings", "file"), patches=paths("patches", "file"))


def apply(fw: Firmware, mod: Mod, log=print) -> int:
    """Apply a mod (includes first) to `fw`. Returns the number of changes made."""
    n = 0
    for inc in mod.include:
        n += apply(fw, inc, log)
    if mod.theme:
        changed = themes.apply(fw, themes.transform(mod.theme, mod.hue))
        log(f"{mod.name}: theme {mod.theme}, {len(changed)} pictures recolored")
        n += len(changed)
    for d in mod.images:
        pics = imageres.import_dir(fw, d)
        if pics:
            log(f"{mod.name}: pictures replaced from {d.name}: {', '.join(map(str, pics))}")
        n += len(pics)
    for d in mod.fonts:
        glyphs = [cp for sheet in sorted(d.glob("*.png")) for cp in fonts.import_sheet(fw, sheet)]
        log(f"{mod.name}: {len(glyphs)} glyphs from {d.name}")
        n += len(glyphs)
    for f in mod.strings:
        texts = strtbl.import_tsv(fw, f)
        log(f"{mod.name}: strings changed: {', '.join(f'{lang}:{r}' for lang, r in texts)}")
        n += len(texts)
    for f in mod.patches:
        for p in patches.apply(fw, patches.parse_tsv(f)):
            log(f"{mod.name}: patched {p}")
            n += 1
    return n
