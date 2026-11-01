#!/usr/bin/env python3
"""Stash - folder backups (Ruvex Software Supply).

A backup is one .zip that holds your folders as plain, normal folders under data/,
plus a manifest with their original locations and a Restore script.
Stash can also restore straight from that zip, without extracting it first.

Fonts: Jersey 25 (display), Silkscreen (pixel), Departure Mono (text), bundled in ./fonts.
"""
import os
import sys
import json
import time
import shutil
import socket
import getpass
import threading
import subprocess
import zipfile
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path
from tkinter import ttk, messagebox, filedialog

APP_NAME = "Stash"
APP_VERSION = "1.0"
APP_TITLE = "Stash — Folder Backups"
MANIFEST_NAME = "manifest.json"
DATA_PREFIX = "data/"
CHUNK = 1024 * 1024

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# ---------------------------------------------------------------- palette
INK = "#0D1117"
INK2 = "#151B23"
LINE = "#2A3441"
GREY = "#3A4758"
CREAM = "#F3EBDD"
PAPER = "#EADFCC"
BAND = "#DCCFB8"
BROWN = "#3C3126"
MUTED = "#A39B8E"
ORANGE = "#F16D0B"

FONT_DISPLAY = "Jersey 25"
FONT_PIXEL = "Silkscreen"
FONT_MONO = "Departure Mono"


def resource_dir():
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def load_fonts():
    fonts = resource_dir() / "fonts"
    if not fonts.is_dir() or os.name != "nt":
        return
    try:
        import ctypes
        add = ctypes.windll.gdi32.AddFontResourceExW
        add.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
        add.restype = ctypes.c_int
        for pattern in ("*.ttf", "*.otf"):
            for f in fonts.glob(pattern):
                add(str(f), 0x10, None)  # FR_PRIVATE: this process only
    except Exception:
        pass


def F(family, px):
    return (family, -px)  # negative = pixels, keeps pixel fonts crisp


# ---------------------------------------------------------------- helpers
def long_path(p):
    """Windows: allow paths beyond 260 characters."""
    p = os.path.abspath(p)
    if os.name == "nt" and not p.startswith("\\\\?\\"):
        if p.startswith("\\\\"):
            return "\\\\?\\UNC\\" + p[2:]
        return "\\\\?\\" + p
    return p


def human(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{int(n)} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def safe_label(name):
    bad = '<>:"/\\|?*'
    out = "".join("_" if c in bad or ord(c) < 32 else c for c in name).strip(" .")
    return out or "folder"


def is_hidden(path, name):
    if name.startswith("."):
        return True
    if os.name == "nt":
        try:
            import ctypes
            attrs = ctypes.windll.kernel32.GetFileAttributesW(long_path(path))
            return attrs != -1 and bool(attrs & 0x2 or attrs & 0x4)  # hidden | system
        except Exception:
            return False
    return False


def is_reparse_dir(path):
    """Symlinks and junctions are not followed (avoids loops and double copies)."""
    if os.path.islink(path):
        return True
    isj = getattr(os.path, "isjunction", None)
    return bool(isj and isj(path))


JUNK_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}
JUNK_EXT = (".tmp", ".temp")


class Stopped(Exception):
    pass


# ---------------------------------------------------------------- restore scripts (live inside every backup)
README_TEXT = """STASH BACKUP
============

This zip was made by Stash {version} on {created}
Computer: {computer}

What is inside
  data\\          your folders, as normal folders and files
  manifest.json  where each folder came from
  Restore.bat    puts the folders back where they were (see below)
  restore.ps1    the script Restore.bat runs

Your files are NOT in a special format. You can open data\\ and copy anything out by hand.

How to restore
  Option A (the Stash app): open Stash, go to Restore, pick this zip. No need to extract it.
  Option B (no app): extract this whole zip to any folder, then double-click Restore.bat.
            It asks which folders to restore and what to do with files that already exist.

Folders in this backup
{folder_lines}
"""

RESTORE_BAT = """@echo off
title Stash restore
cd /d "%~dp0"
if not exist "%~dp0manifest.json" (
  echo manifest.json was not found next to this file.
  echo Extract the WHOLE zip first, then run Restore.bat from the extracted folder.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restore.ps1"
echo.
pause
"""

RESTORE_PS1 = r"""# Stash restore script. Run it through Restore.bat from the extracted backup folder.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$manifestPath = Join-Path $root 'manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath)) {
    Write-Host 'manifest.json not found. Extract the whole zip first.'
    exit 1
}
$m = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$items = @($m.folders)

Write-Host ''
Write-Host 'STASH RESTORE'
Write-Host ('Backup made {0} on {1}' -f $m.created, $m.computer)
Write-Host ''
for ($i = 0; $i -lt $items.Count; $i++) {
    $f = $items[$i]
    if (Test-Path -LiteralPath $f.original_path) { $state = 'folder exists' } else { $state = 'folder is missing, will be created' }
    Write-Host ('{0,2}. {1}  ({2} files)' -f ($i + 1), $f.name, $f.files)
    Write-Host ('      to {0}  [{1}]' -f $f.original_path, $state)
}
Write-Host ''
$sel = Read-Host 'Which folders? Press Enter for all, or type numbers like 1,3'
$chosen = @()
if ([string]::IsNullOrWhiteSpace($sel)) {
    $chosen = 0..($items.Count - 1)
} else {
    foreach ($tok in ($sel -split '[,\s]+')) {
        $n = 0
        if ([int]::TryParse($tok, [ref]$n) -and $n -ge 1 -and $n -le $items.Count) { $chosen += ($n - 1) }
    }
}
if ($chosen.Count -eq 0) { Write-Host 'Nothing selected.'; exit 0 }

Write-Host ''
Write-Host 'If a file already exists at the destination:'
Write-Host '  1) Overwrite it'
Write-Host '  2) Keep whichever is newer (default)'
Write-Host '  3) Skip it, never touch existing files'
$p = Read-Host 'Choose 1, 2 or 3'
switch ($p) {
    '1' { $flags = @() }
    '3' { $flags = @('/XC', '/XN', '/XO') }
    default { $flags = @('/XO') }
}

Write-Host ''
$alt = Read-Host 'Restore into a different folder instead? Type its path, or press Enter for the original locations'

foreach ($idx in $chosen) {
    $f = $items[$idx]
    $src = Join-Path $root ('data\' + $f.zip_name)
    if ([string]::IsNullOrWhiteSpace($alt)) { $dst = $f.original_path } else { $dst = Join-Path $alt $f.name }
    $dst = $dst.TrimEnd('\')
    Write-Host ''
    Write-Host ('Restoring {0}' -f $f.name)
    Write-Host ('   to {0}' -f $dst)
    if (-not (Test-Path -LiteralPath $src)) { Write-Host '   not found in this backup, skipped.'; continue }
    & robocopy $src $dst /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS /NP @flags | Out-Null
    if ($LASTEXITCODE -ge 8) {
        Write-Host '   some files could not be copied (try running as administrator).'
    } else {
        Write-Host '   done.'
    }
}
Write-Host ''
Write-Host 'Finished.'
"""


# ---------------------------------------------------------------- backup engine
def walk_folder(root, include_hidden, skip_junk, skip_names, stop):
    """Yield ('dir'|'file', abs_path, rel_posix) under root, never following links."""
    root = os.path.abspath(root)
    stack = [root]
    while stack:
        if stop.is_set():
            raise Stopped()
        cur = stack.pop()
        rel_dir = os.path.relpath(cur, root)
        rel_dir = "" if rel_dir == "." else rel_dir.replace("\\", "/")
        if rel_dir:
            yield "dir", cur, rel_dir
        try:
            with os.scandir(long_path(cur)) as it:
                entries = sorted(it, key=lambda e: e.name.lower())
        except OSError as e:
            yield "error", cur, str(e)
            continue
        subdirs = []
        for e in entries:
            name = e.name
            full = os.path.join(cur, name)
            low = name.lower()
            if low in skip_names:
                continue
            if not include_hidden and is_hidden(full, name):
                continue
            rel = (rel_dir + "/" + name) if rel_dir else name
            try:
                if e.is_dir(follow_symlinks=False):
                    if is_reparse_dir(full):
                        continue
                    subdirs.append(full)
                elif e.is_file(follow_symlinks=False):
                    if skip_junk and (low in JUNK_NAMES or low.endswith(JUNK_EXT)):
                        continue
                    yield "file", full, rel
            except OSError as err:
                yield "error", full, str(err)
        stack.extend(reversed(subdirs))


def make_zinfo(path, arcname, compress):
    try:
        zi = zipfile.ZipInfo.from_file(long_path(path), arcname)
    except (ValueError, OSError):
        zi = zipfile.ZipInfo(arcname, (1980, 1, 1, 0, 0, 0))
        zi.external_attr = 0o644 << 16
    zi.compress_type = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    return zi


def run_backup(folders, dest_dir, opts, ui):
    """folders: list of paths. ui: object with log(), progress(done,total,label), stop (Event)."""
    stop = ui.stop
    skip_names = {n.strip().lower() for n in opts["skip_names"].split(",") if n.strip()}
    stamp = datetime.now()
    final = Path(dest_dir) / f"Stash-{stamp:%Y-%m-%d_%H%M}.zip"
    n = 2
    while final.exists():
        final = Path(dest_dir) / f"Stash-{stamp:%Y-%m-%d_%H%M}-{n}.zip"
        n += 1
    partial = final.with_name(final.name + ".partial")
    partial_abs = os.path.abspath(str(partial)).lower()

    # unique labels for the folders inside data/
    labels, used = [], set()
    for f in folders:
        base = safe_label(os.path.basename(os.path.normpath(f)))
        label, k = base, 2
        while label.lower() in used:
            label = f"{base}_{k}"
            k += 1
        used.add(label.lower())
        labels.append(label)

    # ---- scan
    ui.log("Scanning folders...\n")
    plan = []  # (folder_index, kind, abs, rel)
    total_bytes = total_files = 0
    skipped = []
    for i, f in enumerate(folders):
        for kind, p, rel in walk_folder(f, opts["hidden"], opts["junk"], skip_names, stop):
            if kind == "error":
                skipped.append((p, rel))
                continue
            if kind == "file" and os.path.abspath(p).lower() == partial_abs:
                continue
            plan.append((i, kind, p, rel))
            if kind == "file":
                total_files += 1
                try:
                    total_bytes += os.path.getsize(long_path(p))
                except OSError:
                    pass
        ui.log(f"  {labels[i]}: scanned\n")
    ui.progress(0, total_bytes, f"0 of {total_files} files")

    # ---- write
    per_folder = [{"files": 0, "bytes": 0} for _ in folders]
    done_bytes = done_files = 0
    last_ui = 0.0
    try:
        with zipfile.ZipFile(str(partial), "w", allowZip64=True) as zf:
            for i, kind, p, rel in plan:
                if stop.is_set():
                    raise Stopped()
                arc = f"{DATA_PREFIX}{labels[i]}/{rel}"
                if kind == "dir":
                    zi = zipfile.ZipInfo(arc + "/", (1980, 1, 1, 0, 0, 0))
                    try:
                        st = os.stat(long_path(p))
                        t = time.localtime(st.st_mtime)
                        if t.tm_year >= 1980:
                            zi.date_time = tuple(t)[:6]
                    except OSError:
                        pass
                    zi.external_attr = (0o40755 << 16) | 0x10
                    zf.writestr(zi, b"")
                    continue
                try:
                    size = os.path.getsize(long_path(p))
                    zi = make_zinfo(p, arc, opts["compress"])
                    with open(long_path(p), "rb") as src, zf.open(zi, "w", force_zip64=size >= 2 ** 31) as dst:
                        while True:
                            if stop.is_set():
                                raise Stopped()
                            chunk = src.read(CHUNK)
                            if not chunk:
                                break
                            dst.write(chunk)
                            done_bytes += len(chunk)
                            now = time.monotonic()
                            if now - last_ui > 0.1:
                                last_ui = now
                                ui.progress(done_bytes, total_bytes, f"{done_files} of {total_files} files")
                    per_folder[i]["files"] += 1
                    per_folder[i]["bytes"] += size
                    done_files += 1
                except Stopped:
                    raise
                except (OSError, PermissionError) as e:
                    skipped.append((p, str(e)))
                    ui.log(f"Skipped (in use or unreadable): {p}\n")
            ui.progress(done_bytes, total_bytes, "Writing restore files...")

            manifest = {
                "app": APP_NAME,
                "version": APP_VERSION,
                "format": 1,
                "created": f"{stamp:%Y-%m-%d %H:%M}",
                "computer": socket.gethostname(),
                "user": getpass.getuser(),
                "folders": [
                    {
                        "name": labels[i],
                        "zip_name": labels[i],
                        "original_path": os.path.abspath(folders[i]),
                        "files": per_folder[i]["files"],
                        "bytes": per_folder[i]["bytes"],
                    }
                    for i in range(len(folders))
                ],
                "skipped": [{"path": p, "reason": r} for p, r in skipped][:500],
            }
            zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2, ensure_ascii=True))
            lines = "\n".join(
                f"  {m['name']}  ->  {m['original_path']}  ({m['files']} files)" for m in manifest["folders"]
            )
            readme = README_TEXT.format(version=APP_VERSION, created=manifest["created"],
                                        computer=manifest["computer"], folder_lines=lines)
            zf.writestr("README.txt", readme.encode("utf-8-sig"))
            zf.writestr("Restore.bat", RESTORE_BAT.replace("\n", "\r\n"))
            zf.writestr("restore.ps1", RESTORE_PS1.replace("\r\n", "\n").replace("\n", "\r\n"))
    except BaseException:
        try:
            partial.unlink()
        except OSError:
            pass
        raise

    # ---- verify
    if opts["verify"]:
        ui.log("Checking the zip...\n")
        try:
            verify_zip(str(partial), ui)
        except BaseException:
            try:
                partial.unlink()
            except OSError:
                pass
            raise

    os.replace(str(partial), str(final))
    return final, done_files, done_bytes, skipped


def verify_zip(path, ui):
    stop = ui.stop
    with zipfile.ZipFile(path) as zf:
        infos = zf.infolist()
        total = sum(i.file_size for i in infos) or 1
        done = 0
        last = 0.0
        for info in infos:
            if stop.is_set():
                raise Stopped()
            if info.is_dir():
                continue
            with zf.open(info) as f:
                while True:
                    chunk = f.read(CHUNK)  # raises BadZipFile on a CRC mismatch
                    if not chunk:
                        break
                    done += len(chunk)
                    now = time.monotonic()
                    if now - last > 0.1:
                        last = now
                        ui.progress(done, total, "Checking...")


# ---------------------------------------------------------------- restore engine
def read_manifest(zip_path):
    with zipfile.ZipFile(zip_path) as zf:
        try:
            m = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
        except KeyError:
            raise ValueError("This zip has no manifest.json, so it isn't a Stash backup.")
        if m.get("app") != APP_NAME or "folders" not in m:
            raise ValueError("This zip wasn't made by Stash.")
        return m


def safe_join(base, rel):
    """Join rel (from a zip) under base, refusing anything that escapes it."""
    parts = [p for p in rel.replace("\\", "/").split("/") if p not in ("", ".")]
    if any(p == ".." or ":" in p for p in parts):
        raise ValueError(f"Unsafe path in zip: {rel}")
    return os.path.join(base, *parts) if parts else base


def run_restore(zip_path, manifest, picks, mode, alt_dir, policy, ui):
    """picks: indexes into manifest['folders']. mode: 'original'|'other'. policy: overwrite|newer|skip."""
    stop = ui.stop
    restored = skipped = failed = 0
    with zipfile.ZipFile(zip_path) as zf:
        wanted = []
        total = 0
        for idx in picks:
            fd = manifest["folders"][idx]
            prefix = f"{DATA_PREFIX}{fd['zip_name']}/"
            target = fd["original_path"] if mode == "original" else os.path.join(alt_dir, fd["name"])
            members = [i for i in zf.infolist() if i.filename.startswith(prefix) and i.filename != prefix]
            wanted.append((fd, prefix, target, members))
            total += sum(i.file_size for i in members)
        done = 0
        last = 0.0
        for fd, prefix, target, members in wanted:
            ui.log(f"Restoring {fd['name']}\n   to {target}\n")
            os.makedirs(long_path(target), exist_ok=True)
            for info in members:
                if stop.is_set():
                    raise Stopped()
                rel = info.filename[len(prefix):]
                try:
                    dest = safe_join(target, rel)
                    if info.is_dir():
                        os.makedirs(long_path(dest), exist_ok=True)
                        continue
                    zt = time.mktime(tuple(info.date_time) + (0, 0, -1))
                    if os.path.exists(long_path(dest)):
                        if policy == "skip":
                            skipped += 1
                            done += info.file_size
                            continue
                        if policy == "newer" and os.path.getmtime(long_path(dest)) >= zt - 2:
                            skipped += 1
                            done += info.file_size
                            continue
                    os.makedirs(long_path(os.path.dirname(dest)), exist_ok=True)
                    tmp = dest + ".stash-tmp"
                    with zf.open(info) as src, open(long_path(tmp), "wb") as out:
                        while True:
                            if stop.is_set():
                                raise Stopped()
                            chunk = src.read(CHUNK)
                            if not chunk:
                                break
                            out.write(chunk)
                            done += len(chunk)
                            now = time.monotonic()
                            if now - last > 0.1:
                                last = now
                                ui.progress(done, total, f"{restored} files restored")
                    if os.path.exists(long_path(dest)):
                        try:
                            os.chmod(long_path(dest), 0o666)
                        except OSError:
                            pass
                    os.replace(long_path(tmp), long_path(dest))
                    try:
                        os.utime(long_path(dest), (zt, zt))
                    except OSError:
                        pass
                    restored += 1
                except Stopped:
                    try:
                        os.remove(long_path(dest + ".stash-tmp"))
                    except OSError:
                        pass
                    raise
                except (OSError, ValueError) as e:
                    failed += 1
                    ui.log(f"Could not restore {rel}: {e}\n")
        ui.progress(total, total or 1, f"{restored} files restored")
    return restored, skipped, failed


# ---------------------------------------------------------------- UI plumbing
class Ui:
    """Thread-safe bridge from a worker back to the Tk window."""

    def __init__(self, app):
        self.app = app
        self.stop = threading.Event()

    def log(self, text):
        self.app.after(0, self.app.log_write, text)

    def progress(self, done, total, label):
        pct = (done / total * 100) if total else 0
        self.app.after(0, self.app.set_progress, pct, f"{label}  ·  {int(pct)}%")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1120x860")
        self.minsize(980, 760)
        self.configure(bg=INK)
        ico = resource_dir() / "stash.ico"
        if ico.is_file():
            try:
                self.iconbitmap(str(ico))
            except Exception:
                pass

        families = set(tkfont.families(self))
        self.fd = FONT_DISPLAY if FONT_DISPLAY in families else "Courier New"
        self.fp = FONT_PIXEL if FONT_PIXEL in families else "Courier New"
        self.fm = FONT_MONO if FONT_MONO in families else "Consolas"

        self.option_add("*TCombobox*Listbox.font", F(self.fm, 13))
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Stash.Horizontal.TProgressbar", troughcolor=PAPER, background=ORANGE,
                        bordercolor=INK, lightcolor=ORANGE, darkcolor=ORANGE, thickness=14)

        # state
        self.sources = []
        self.dest = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Documents"))
        self.opt_compress = tk.BooleanVar(value=True)
        self.opt_verify = tk.BooleanVar(value=True)
        self.opt_junk = tk.BooleanVar(value=True)
        self.opt_hidden = tk.BooleanVar(value=True)
        self.skip_names = tk.StringVar(value="")
        self.zip_path = tk.StringVar()
        self.manifest = None
        self.rest_mode = tk.StringVar(value="original")
        self.rest_alt = tk.StringVar()
        self.rest_policy = tk.StringVar(value="newer")
        self.status = tk.StringVar(value="Ready. Add the folders you want to protect.")
        self.ui = None
        self.busy = False
        self.open_target = None
        self.tab = "backup"

        self._build_ui()
        self.show_tab("backup")

    # ---------------------------------------------------------- widgets
    def lbl(self, parent, text="", font=None, bg=INK, fg=CREAM, **kw):
        return tk.Label(parent, text=text, font=font or F(self.fm, 12), bg=bg, fg=fg, **kw)

    def btn(self, parent, text, command, bg=PAPER, fg=INK, font=None, **kw):
        return tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                         activebackground=ORANGE, activeforeground=INK,
                         font=font or F(self.fm, 12), relief="solid", bd=1, cursor="hand2", **kw)

    def _build_ui(self):
        root = tk.Frame(self, bg=INK)
        root.pack(fill="both", expand=True)

        top = tk.Frame(root, bg=INK, height=56)
        top.pack(fill="x")
        top.pack_propagate(False)
        tk.Frame(top, bg=LINE, height=1).pack(side="bottom", fill="x")
        bar = tk.Frame(top, bg=INK)
        bar.pack(fill="both", expand=True, padx=36)
        self.lbl(bar, "RUVEX", F(self.fp, 24)).pack(side="left")
        self.lbl(bar, "Software Supply", F(self.fm, 12), fg=MUTED).pack(side="left", padx=(12, 0))
        self.lbl(bar, "Local tool", F(self.fm, 11), bg=INK2, fg=MUTED, padx=10, pady=3).pack(side="right")

        head = tk.Frame(root, bg=INK)
        head.pack(fill="x", padx=36, pady=(12, 8))
        self.lbl(head, "Stash", F(self.fd, 56)).pack(side="left")
        self.lbl(head, "folder backups", F(self.fm, 13), fg=MUTED).pack(side="left", padx=(14, 0), pady=(20, 0))
        tabs = tk.Frame(head, bg=INK)
        tabs.pack(side="right", anchor="n", pady=(10, 0))
        self.tab_b = self.btn(tabs, "Back up", lambda: self.show_tab("backup"), padx=16, pady=3)
        self.tab_b.pack(side="left")
        self.tab_r = self.btn(tabs, "Restore", lambda: self.show_tab("restore"), padx=16, pady=3)
        self.tab_r.pack(side="left", padx=(6, 0))
        tk.Frame(root, bg=LINE, height=1).pack(fill="x")

        content = tk.Frame(root, bg=INK)
        content.pack(fill="both", expand=True, padx=36, pady=(14, 18))
        content.columnconfigure(0, weight=3, uniform="c")
        content.columnconfigure(1, weight=2, uniform="c")
        content.rowconfigure(0, weight=1)

        # left: work order
        self.wo = tk.Frame(content, bg=PAPER)
        self.wo.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        wh = tk.Frame(self.wo, bg=BAND, height=32)
        wh.pack(fill="x")
        wh.pack_propagate(False)
        self.wo_title = self.lbl(wh, "Work order", F(self.fm, 12), bg=BAND, fg=INK)
        self.wo_title.pack(side="left", padx=18)
        self.lbl(wh, "RXV-002", F(self.fm, 11), bg=BAND, fg=BROWN).pack(side="right", padx=18)

        # submit area first so it never gets clipped
        sub = tk.Frame(self.wo, bg=PAPER)
        sub.pack(fill="x", side="bottom", padx=18, pady=(0, 12))
        self.go = self.btn(sub, "Back up now", self.start, bg=ORANGE, font=F(self.fm, 15), pady=7)
        self.go.pack(fill="x")
        self.cancel_b = self.btn(sub, "Cancel", self.cancel, font=F(self.fm, 12), pady=3)
        self.lbl(sub, textvariable=self.status, font=F(self.fm, 11), bg=PAPER, fg=BROWN,
                 wraplength=520, justify="left").pack(anchor="w", pady=(6, 0))

        self.body_backup = tk.Frame(self.wo, bg=PAPER)
        self.body_restore = tk.Frame(self.wo, bg=PAPER)
        self._build_backup(self.body_backup)
        self._build_restore(self.body_restore)

        # right: ticket + log
        right = tk.Frame(content, bg=INK)
        right.grid(row=0, column=1, sticky="nsew")
        tkt = tk.Frame(right, bg=CREAM)
        tkt.pack(fill="x")
        th = tk.Frame(tkt, bg=INK, height=30)
        th.pack(fill="x")
        th.pack_propagate(False)
        self.lbl(th, "Job ticket", F(self.fm, 12)).pack(side="left", padx=14)
        self.tno = self.lbl(th, "No job", F(self.fm, 12), fg=MUTED)
        self.tno.pack(side="right", padx=14)
        tb = tk.Frame(tkt, bg=CREAM)
        tb.pack(fill="x", padx=14, pady=10)
        self.t = {k: tk.StringVar(value="-") for k in ("Mode", "Folders", "Files", "Size", "Skipped")}
        for k, v in self.t.items():
            fr = tk.Frame(tb, bg=CREAM)
            fr.pack(fill="x", pady=1)
            self.lbl(fr, k, F(self.fm, 11), bg=CREAM, fg=BROWN).pack(side="left")
            self.lbl(fr, textvariable=v, font=F(self.fm, 11), bg=CREAM, fg=INK).pack(side="right")
            tk.Frame(tb, bg=BROWN, height=1).pack(fill="x", pady=3)
        self.pbar = ttk.Progressbar(tb, mode="determinate", style="Stash.Horizontal.TProgressbar", maximum=100)
        self.pbar.pack(fill="x", pady=(8, 4))
        self.pp = self.lbl(tb, "Idle  ·  0%", F(self.fm, 11), bg=CREAM, fg=INK)
        self.pp.pack(anchor="e")
        self.open_b = self.btn(tb, "Open folder", self.open_folder, font=F(self.fm, 12), pady=3)
        self.open_b.pack(fill="x", pady=(10, 0))

        con = tk.Frame(right, bg=INK2)
        con.pack(fill="both", expand=True, pady=(12, 0))
        ch = tk.Frame(con, bg=INK2, height=30)
        ch.pack(fill="x")
        ch.pack_propagate(False)
        self.lbl(ch, "Log", F(self.fm, 12), bg=INK2, fg=MUTED).pack(side="left", padx=14)
        clf = tk.Frame(con, bg=INK)
        clf.pack(fill="both", expand=True)
        self.logt = tk.Text(clf, bg=INK, fg=MUTED, insertbackground=ORANGE, font=F(self.fm, 11),
                            relief="flat", wrap="word", state="disabled", width=10, height=6,
                            highlightthickness=0)
        sc = tk.Scrollbar(clf, command=self.logt.yview, bg=INK2, troughcolor=INK, bd=0)
        self.logt.configure(yscrollcommand=sc.set)
        self.logt.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        sc.pack(side="right", fill="y", padx=(0, 4), pady=10)

    def section(self, parent, num, title, note=None):
        f = tk.Frame(parent, bg=PAPER)
        f.pack(fill="x", pady=(0, 8))
        h = tk.Frame(f, bg=PAPER)
        h.pack(fill="x")
        self.lbl(h, num, F(self.fm, 11), bg=INK, fg=CREAM, padx=6).pack(side="left")
        self.lbl(h, title, F(self.fm, 13), bg=PAPER, fg=INK, padx=8).pack(side="left")
        if note:
            self.lbl(h, note, F(self.fm, 11), bg=PAPER, fg=BROWN).pack(side="right")
        tk.Frame(f, bg=BROWN, height=1).pack(fill="x", pady=(4, 6))
        return f

    def hint(self, parent, text):
        self.lbl(parent, text, F(self.fm, 11), bg=PAPER, fg=BROWN, wraplength=540,
                 justify="left").pack(anchor="w", pady=(4, 0))

    def check(self, parent, var, title, desc):
        tk.Checkbutton(parent, text=f"{title}  ·  {desc}", variable=var, bg=PAPER, fg=INK,
                       selectcolor=CREAM, activebackground=PAPER, activeforeground=INK,
                       font=F(self.fm, 11), anchor="w", cursor="hand2", pady=0).pack(fill="x")

    def radio(self, parent, var, value, text, command=None):
        tk.Radiobutton(parent, text=text, variable=var, value=value, command=command, bg=PAPER, fg=INK,
                       selectcolor=CREAM, activebackground=PAPER, activeforeground=INK,
                       font=F(self.fm, 11), anchor="w", cursor="hand2", pady=0).pack(fill="x")

    def listbox(self, parent, height, mode):
        fr = tk.Frame(parent, bg=PAPER)
        lb = tk.Listbox(fr, height=height, selectmode=mode, bg=CREAM, fg=INK, font=F(self.fm, 12),
                        relief="solid", bd=1, highlightthickness=0, activestyle="none",
                        selectbackground="#C9B896", selectforeground=INK, exportselection=False)
        sc = tk.Scrollbar(fr, command=lb.yview, bg=PAPER, troughcolor=PAPER, bd=0)
        lb.configure(yscrollcommand=sc.set)
        lb.pack(side="left", fill="both", expand=True)
        sc.pack(side="right", fill="y")
        return fr, lb

    # ---------------------------------------------------------- backup tab
    def _build_backup(self, p):
        s = self.section(p, "01", "Folders to back up", "required")
        fr, self.src_list = self.listbox(s, 5, "extended")
        fr.pack(fill="x")
        row = tk.Frame(s, bg=PAPER)
        row.pack(fill="x", pady=(6, 0))
        self.btn(row, "Add folder", self.add_folder, padx=12).pack(side="left", ipady=2)
        self.btn(row, "Remove", self.remove_folder, padx=12).pack(side="left", padx=(6, 0), ipady=2)
        self.btn(row, "Clear", self.clear_folders, padx=12).pack(side="left", padx=(6, 0), ipady=2)
        self.hint(s, "Pick as many folders as you like. Links and junctions are not followed.")

        s = self.section(p, "02", "Save the backup to")
        row = tk.Frame(s, bg=PAPER)
        row.pack(fill="x")
        tk.Entry(row, textvariable=self.dest, bg=CREAM, fg=INK, insertbackground=ORANGE,
                 font=F(self.fm, 13), relief="solid", bd=1).pack(side="left", fill="x", expand=True, ipady=6)
        self.btn(row, "Choose", self.choose_dest, padx=14).pack(side="left", padx=(8, 0), ipady=2)
        self.hint(s, "The file is named Stash-date-time.zip. An existing backup is never overwritten.")

        s = self.section(p, "03", "Options")
        self.check(s, self.opt_compress, "Compress", "smaller file, a bit slower")
        self.check(s, self.opt_verify, "Check the zip", "re-read it when finished to make sure it is sound")
        self.check(s, self.opt_hidden, "Include hidden files", "hidden and system files too")
        self.check(s, self.opt_junk, "Skip junk", "Thumbs.db, desktop.ini, .tmp files")
        row = tk.Frame(s, bg=PAPER)
        row.pack(fill="x", pady=(6, 0))
        self.lbl(row, "Also skip names", F(self.fm, 11), bg=PAPER, fg=BROWN).pack(side="left")
        tk.Entry(row, textvariable=self.skip_names, bg=CREAM, fg=INK, insertbackground=ORANGE,
                 font=F(self.fm, 12), relief="solid", bd=1).pack(side="left", fill="x", expand=True,
                                                                 padx=(10, 0), ipady=3)
        self.hint(s, "Separate with commas, for example: node_modules, .cache")

    # ---------------------------------------------------------- restore tab
    def _build_restore(self, p):
        s = self.section(p, "01", "Backup file", "required")
        row = tk.Frame(s, bg=PAPER)
        row.pack(fill="x")
        tk.Entry(row, textvariable=self.zip_path, bg=CREAM, fg=INK, insertbackground=ORANGE,
                 font=F(self.fm, 13), relief="solid", bd=1).pack(side="left", fill="x", expand=True, ipady=6)
        self.btn(row, "Choose zip", self.choose_zip, padx=14).pack(side="left", padx=(8, 0), ipady=2)
        self.hint(s, "A zip made by Stash. You don't need to extract it first.")

        s = self.section(p, "02", "Folders in this backup")
        fr, self.rest_list = self.listbox(s, 5, "extended")
        fr.pack(fill="x")
        row = tk.Frame(s, bg=PAPER)
        row.pack(fill="x", pady=(6, 0))
        self.btn(row, "Select all", lambda: self.rest_list.select_set(0, "end"), padx=12).pack(side="left", ipady=2)
        self.rest_info = self.lbl(row, "", F(self.fm, 11), bg=PAPER, fg=BROWN)
        self.rest_info.pack(side="left", padx=(10, 0))

        s = self.section(p, "03", "Where to put them")
        self.radio(s, self.rest_mode, "original", "Original locations, as if nothing happened")
        self.radio(s, self.rest_mode, "other", "Another folder (each folder goes in its own subfolder)")
        row = tk.Frame(s, bg=PAPER)
        row.pack(fill="x", pady=(4, 0))
        tk.Entry(row, textvariable=self.rest_alt, bg=CREAM, fg=INK, insertbackground=ORANGE,
                 font=F(self.fm, 12), relief="solid", bd=1).pack(side="left", fill="x", expand=True, ipady=3)
        self.btn(row, "Choose", self.choose_alt, padx=12).pack(side="left", padx=(8, 0))

        s = self.section(p, "04", "If a file already exists")
        self.radio(s, self.rest_policy, "newer", "Keep whichever is newer (recommended)")
        self.radio(s, self.rest_policy, "overwrite", "Overwrite it with the backup copy")
        self.radio(s, self.rest_policy, "skip", "Skip it, never touch existing files")

    # ---------------------------------------------------------- tabs
    def show_tab(self, tab):
        if self.busy:
            return
        self.tab = tab
        self.body_backup.pack_forget()
        self.body_restore.pack_forget()
        body = self.body_backup if tab == "backup" else self.body_restore
        body.pack(fill="both", expand=True, padx=18, pady=(12, 0))
        for b, on in ((self.tab_b, tab == "backup"), (self.tab_r, tab == "restore")):
            b.configure(bg=PAPER if on else INK2, fg=INK if on else MUTED)
        self.go.configure(text="Back up now" if tab == "backup" else "Restore now")
        self.wo_title.configure(text="Back up folders" if tab == "backup" else "Restore a backup")
        self.t["Mode"].set("Back up" if tab == "backup" else "Restore")
        if tab == "backup":
            self.status.set("Ready. Add the folders you want to protect." if not self.sources
                            else f"{len(self.sources)} folder(s) ready.")
        else:
            self.status.set("Choose a Stash backup to restore from.")

    # ---------------------------------------------------------- pickers
    def add_folder(self):
        d = filedialog.askdirectory(title="Choose a folder to back up", mustexist=True)
        if not d:
            return
        d = os.path.normpath(d)
        if os.path.dirname(d) == d:
            messagebox.showinfo("Pick a folder", "Choose a folder, not a whole drive.")
            return
        if d in self.sources:
            return
        self.sources.append(d)
        self.src_list.insert("end", d)
        self.status.set(f"{len(self.sources)} folder(s) ready.")

    def remove_folder(self):
        for i in reversed(self.src_list.curselection()):
            self.src_list.delete(i)
            del self.sources[i]

    def clear_folders(self):
        self.src_list.delete(0, "end")
        self.sources.clear()

    def choose_dest(self):
        d = filedialog.askdirectory(title="Where should the backup be saved?", mustexist=True)
        if d:
            self.dest.set(os.path.normpath(d))

    def choose_alt(self):
        d = filedialog.askdirectory(title="Restore into which folder?", mustexist=True)
        if d:
            self.rest_alt.set(os.path.normpath(d))
            self.rest_mode.set("other")

    def choose_zip(self):
        f = filedialog.askopenfilename(title="Choose a Stash backup", filetypes=[("Stash backup", "*.zip")])
        if not f:
            return
        self.zip_path.set(os.path.normpath(f))
        self.load_manifest()

    def load_manifest(self):
        self.rest_list.delete(0, "end")
        self.manifest = None
        try:
            m = read_manifest(self.zip_path.get())
        except Exception as e:
            self.status.set("That file can't be restored.")
            messagebox.showinfo("Not a Stash backup", str(e))
            return
        self.manifest = m
        for fd in m["folders"]:
            exists = "exists" if os.path.isdir(fd["original_path"]) else "missing"
            self.rest_list.insert("end", f"{fd['name']}  ->  {fd['original_path']}  [{exists}, {fd['files']} files]")
        self.rest_list.select_set(0, "end")
        self.rest_info.configure(text=f"Made {m.get('created', '?')} on {m.get('computer', '?')}")
        self.t["Folders"].set(str(len(m["folders"])))
        self.t["Files"].set(str(sum(f["files"] for f in m["folders"])))
        self.t["Size"].set(human(sum(f["bytes"] for f in m["folders"])))
        self.status.set("Backup loaded. Choose what to restore.")

    # ---------------------------------------------------------- shared
    def log_write(self, text):
        self.logt.configure(state="normal")
        self.logt.insert("end", text)
        self.logt.see("end")
        self.logt.configure(state="disabled")

    def set_progress(self, pct, label):
        self.pbar.configure(value=pct)
        self.pp.configure(text=label)

    def set_busy(self, busy):
        self.busy = busy
        if busy:
            self.go.configure(state="disabled", bg=PAPER, fg=BROWN)
            self.cancel_b.pack(fill="x", pady=(6, 0))
        else:
            self.go.configure(state="normal", bg=ORANGE, fg=INK)
            self.cancel_b.pack_forget()

    def cancel(self):
        if self.ui:
            self.ui.stop.set()
            self.status.set("Stopping...")

    def start(self):
        if self.busy:
            return
        self.logt.configure(state="normal")
        self.logt.delete("1.0", "end")
        self.logt.configure(state="disabled")
        if self.tab == "backup":
            self.start_backup()
        else:
            self.start_restore()

    # ---------------------------------------------------------- backup job
    def start_backup(self):
        if not self.sources:
            messagebox.showinfo("Folders needed", "Add at least one folder first.")
            return
        dest = self.dest.get().strip()
        if not os.path.isdir(dest):
            messagebox.showinfo("Folder not found", "The folder to save into doesn't exist.")
            return
        for s in self.sources:
            if not os.path.isdir(s):
                messagebox.showinfo("Folder not found", f"This folder no longer exists:\n{s}")
                return
        opts = {"compress": self.opt_compress.get(), "verify": self.opt_verify.get(),
                "junk": self.opt_junk.get(), "hidden": self.opt_hidden.get(),
                "skip_names": self.skip_names.get()}
        self.ui = Ui(self)
        self.set_busy(True)
        self.open_target = dest
        self.t["Folders"].set(str(len(self.sources)))
        for k in ("Files", "Size", "Skipped"):
            self.t[k].set("-")
        self.tno.configure(text="Running")
        self.status.set("Backing up...")
        self.set_progress(0, "Scanning  ·  0%")
        threading.Thread(target=self._backup_worker, args=(list(self.sources), dest, opts, self.ui),
                         daemon=True).start()

    def _backup_worker(self, folders, dest, opts, ui):
        try:
            final, files, size, skipped = run_backup(folders, dest, opts, ui)
            self.after(0, self._backup_done, final, files, size, skipped)
        except Stopped:
            self.after(0, self._finish, "Stopped. No backup was kept.", "Stopped", False)
        except Exception as e:
            self.after(0, self._finish, "Something went wrong.", "Error", False, str(e))

    def _backup_done(self, final, files, size, skipped):
        self.t["Files"].set(str(files))
        self.t["Size"].set(human(size))
        self.t["Skipped"].set(str(len(skipped)))
        self.open_target = str(Path(final).parent)
        self.log_write(f"\nSaved: {final}\n")
        msg = f"Done. {files} files saved to {Path(final).name}."
        if skipped:
            msg += f" {len(skipped)} could not be read."
        self._finish(msg, "Done", True)

    # ---------------------------------------------------------- restore job
    def start_restore(self):
        if not self.manifest:
            messagebox.showinfo("Backup needed", "Choose a Stash backup first.")
            return
        picks = list(self.rest_list.curselection())
        if not picks:
            messagebox.showinfo("Nothing selected", "Select at least one folder to restore.")
            return
        mode = self.rest_mode.get()
        alt = self.rest_alt.get().strip()
        if mode == "other" and not os.path.isdir(alt):
            messagebox.showinfo("Folder not found", "Choose the folder to restore into.")
            return
        policy = self.rest_policy.get()
        if mode == "original" and policy == "overwrite":
            if not messagebox.askyesno("Overwrite files?",
                                       "Files in the original folders will be replaced by the backup copies. Continue?"):
                return
        self.ui = Ui(self)
        self.set_busy(True)
        self.open_target = alt if mode == "other" else self.manifest["folders"][picks[0]]["original_path"]
        self.tno.configure(text="Running")
        self.status.set("Restoring...")
        self.set_progress(0, "Starting  ·  0%")
        threading.Thread(target=self._restore_worker,
                         args=(self.zip_path.get(), self.manifest, picks, mode, alt, policy, self.ui),
                         daemon=True).start()

    def _restore_worker(self, zip_path, manifest, picks, mode, alt, policy, ui):
        try:
            r, s, f = run_restore(zip_path, manifest, picks, mode, alt, policy, ui)
            self.after(0, self._restore_done, r, s, f)
        except Stopped:
            self.after(0, self._finish, "Stopped. Files restored so far were kept.", "Stopped", False)
        except Exception as e:
            self.after(0, self._finish, "Something went wrong.", "Error", False, str(e))

    def _restore_done(self, r, s, f):
        self.t["Files"].set(str(r))
        self.t["Skipped"].set(str(s))
        msg = f"Done. {r} files restored, {s} skipped" + (f", {f} failed." if f else ".")
        self._finish(msg, "Done" if not f else "Partly", not f)

    def _finish(self, status, ticket, ok, err=None):
        self.set_busy(False)
        self.status.set(status)
        self.tno.configure(text=ticket)
        self.set_progress(100 if ok else 0, "Done  ·  100%" if ok else "Idle  ·  0%")
        if ok:
            messagebox.showinfo("Done", status)
        elif err:
            messagebox.showwarning("Something went wrong", err)

    def open_folder(self):
        path = self.open_target or self.dest.get()
        try:
            if os.name == "nt":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass


if __name__ == "__main__":
    load_fonts()
    App().mainloop()
