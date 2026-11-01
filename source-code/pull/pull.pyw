#!/usr/bin/env python3
"""Pull - yt-dlp downloader (Ruvex Software Supply).

Fonts: Jersey 25 (display), Silkscreen (pixel labels), Departure Mono (text).
They live in ./fonts and are bundled into the .exe when built with --onefile.
"""
import os
import re
import sys
import shutil
import tempfile
import threading
import subprocess
import tkinter as tk
import tkinter.font as tkfont
import urllib.request
import zipfile
from pathlib import Path
from tkinter import ttk, messagebox

APP_TITLE = "Pull — yt-dlp Downloader"

# A windowed (--noconsole) build has no stdout/stderr; yt-dlp must not crash on that.
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
BROWN = "#3C3126"
MUTED = "#A39B8E"
ORANGE = "#F16D0B"

# ---------------------------------------------------------------- paths
def resource_dir():
    """Folder holding bundled data (fonts, icon).

    --onefile unpacks everything to a temp folder exposed as sys._MEIPASS.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def exe_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def data_dir():
    """Writable per-user folder (ffmpeg is stored here, not next to the .exe)."""
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    p = Path(base) / "Pull"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------- fonts
FONT_DISPLAY = "Jersey 25"
FONT_PIXEL = "Silkscreen"
FONT_MONO = "Departure Mono"


def load_fonts():
    """Register the bundled fonts for this process only (Windows, no install)."""
    fonts = resource_dir() / "fonts"
    if not fonts.is_dir() or os.name != "nt":
        return
    try:
        import ctypes
        add = ctypes.windll.gdi32.AddFontResourceExW
        add.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
        add.restype = ctypes.c_int
        FR_PRIVATE = 0x10
        for pattern in ("*.ttf", "*.otf"):
            for f in fonts.glob(pattern):
                add(str(f), FR_PRIVATE, None)
    except Exception:
        pass


def pick(family, fallback, available):
    return family if family in available else fallback


# Sizes are negative = pixels, so pixel fonts stay crisp at their native grid.
def F(family, px, bold=False):
    return (family, -px, "bold") if bold else (family, -px)


# ---------------------------------------------------------------- ffmpeg
_ffmpeg_lock = threading.Lock()
_ffmpeg_checked = False
_ffmpeg_path = None


def _use_ffmpeg(path):
    global _ffmpeg_path, _ffmpeg_checked
    _ffmpeg_path = str(path)
    os.environ["PATH"] = str(Path(path).parent) + os.pathsep + os.environ.get("PATH", "")
    _ffmpeg_checked = True
    return _ffmpeg_path


def ensure_ffmpeg(progress=None):
    """Find ffmpeg, or (Windows) download it once into %LOCALAPPDATA%\\Pull."""
    global _ffmpeg_checked, _ffmpeg_path
    with _ffmpeg_lock:
        if _ffmpeg_checked:
            return _ffmpeg_path
        found = shutil.which("ffmpeg")
        if found:
            return _use_ffmpeg(found)
        names = ["ffmpeg.exe", "ffmpeg"]
        for root in (data_dir(), exe_dir()):
            for d in (root / "ffmpeg" / "bin", root / "ffmpeg", root / "bin", root):
                for n in names:
                    if (d / n).is_file():
                        return _use_ffmpeg(d / n)
        if os.name == "nt":
            try:
                if progress:
                    progress("Getting ffmpeg, one time only...")
                bin_dir = data_dir() / "ffmpeg" / "bin"
                bin_dir.mkdir(parents=True, exist_ok=True)
                url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
                tmp_zip = Path(tempfile.gettempdir()) / "pull_ffmpeg.zip"
                urllib.request.urlretrieve(url, tmp_zip)
                with zipfile.ZipFile(tmp_zip) as z:
                    for member in z.namelist():
                        base = member.rsplit("/", 1)[-1]
                        if member.endswith(("bin/ffmpeg.exe", "bin/ffprobe.exe")):
                            with z.open(member) as s, open(bin_dir / base, "wb") as t:
                                shutil.copyfileobj(s, t)
                tmp_zip.unlink(missing_ok=True)
                if (bin_dir / "ffmpeg.exe").is_file():
                    return _use_ffmpeg(bin_dir / "ffmpeg.exe")
            except Exception as e:
                print(f"ffmpeg auto-install failed: {e}", flush=True)
        _ffmpeg_checked = True
        return None


# ---------------------------------------------------------------- yt-dlp glue
class JobCancelled(Exception):
    pass


class UiLogger:
    """Feeds yt-dlp's messages into the engine panel."""

    def __init__(self, write):
        self.write = write

    def debug(self, msg):
        if msg.startswith("[debug] "):
            return
        self.write(msg + "\n")

    info = debug

    def warning(self, msg):
        self.write("WARNING: " + msg + "\n")

    def error(self, msg):
        self.write(msg + "\n")


def ytdlp_version():
    try:
        from yt_dlp.version import __version__
        return __version__
    except Exception:
        return "?"


# ---------------------------------------------------------------- app
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1120x860")
        self.minsize(980, 760)
        self.configure(bg=INK)
        ico = resource_dir() / "pull.ico"
        if ico.is_file():
            try:
                self.iconbitmap(str(ico))
            except Exception:
                pass

        families = set(tkfont.families(self))
        self.fd = pick(FONT_DISPLAY, "Courier New", families)
        self.fp = pick(FONT_PIXEL, "Courier New", families)
        self.fm = pick(FONT_MONO, "Consolas", families)

        # Dropdown list font for the comboboxes
        self.option_add("*TCombobox*Listbox.font", F(self.fm, 13))
        self.option_add("*TCombobox*Listbox.background", CREAM)
        self.option_add("*TCombobox*Listbox.foreground", INK)
        self.option_add("*TCombobox*Listbox.selectBackground", ORANGE)
        self.option_add("*TCombobox*Listbox.selectForeground", INK)

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TCombobox", fieldbackground=CREAM, background=PAPER, foreground=INK,
                        bordercolor=INK, lightcolor=PAPER, darkcolor=PAPER, arrowcolor=INK,
                        selectbackground=CREAM, selectforeground=INK, padding=4)
        style.map("TCombobox", fieldbackground=[("readonly", CREAM)],
                  foreground=[("readonly", INK)], selectbackground=[("readonly", CREAM)],
                  selectforeground=[("readonly", INK)])
        style.configure("Pull.Horizontal.TProgressbar", troughcolor=PAPER, background=ORANGE,
                        bordercolor=INK, lightcolor=ORANGE, darkcolor=ORANGE, thickness=14)

        self.url = tk.StringVar()
        self.output_dir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads"))
        self.mode = tk.StringVar(value="video")
        self.video_quality = tk.StringVar(value="best")
        self.audio_format = tk.StringVar(value="mp3")
        self.audio_quality = tk.StringVar(value="192")
        self.container = tk.StringVar(value="mp4")
        self.embed_thumbnail = tk.BooleanVar(value=False)
        self.embed_metadata = tk.BooleanVar(value=True)
        self.playlist = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Ready. Paste a link to begin.")
        self.cancel_flag = threading.Event()

        self._build_ui()

        for v in (self.mode, self.video_quality, self.audio_format, self.audio_quality,
                  self.container, self.output_dir):
            v.trace_add("write", lambda *_: self.update_ticket())

        threading.Thread(target=self._startup_ffmpeg, daemon=True).start()

    # ------------------------------------------------------------ helpers
    def lbl(self, parent, text="", font=None, bg=INK, fg=CREAM, **kw):
        return tk.Label(parent, text=text, font=font or F(self.fm, 12), bg=bg, fg=fg, **kw)

    def btn(self, parent, text, command, bg=PAPER, fg=INK, font=None, **kw):
        return tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                         activebackground=ORANGE, activeforeground=INK,
                         font=font or F(self.fm, 12), relief="solid", bd=1,
                         cursor="hand2", **kw)

    def _startup_ffmpeg(self):
        path = ensure_ffmpeg(progress=lambda m: self.after(0, self.status.set, m))
        self.after(0, self.tff.set, "Ready" if path else "Missing")
        if self.status.get().startswith("Getting ffmpeg"):
            self.after(0, self.status.set, "Ready. Paste a link to begin.")

    # ------------------------------------------------------------ UI
    def _build_ui(self):
        root = tk.Frame(self, bg=INK)
        root.pack(fill="both", expand=True)

        # Top bar
        top = tk.Frame(root, bg=INK, height=56)
        top.pack(fill="x")
        top.pack_propagate(False)
        tk.Frame(top, bg=LINE, height=1).pack(side="bottom", fill="x")
        bar = tk.Frame(top, bg=INK)
        bar.pack(fill="both", expand=True, padx=36)
        self.lbl(bar, "RUVEX", F(self.fp, 24, True)).pack(side="left")
        self.lbl(bar, "Software Supply", F(self.fm, 12), fg=MUTED).pack(side="left", padx=(12, 0))
        self.lbl(bar, "Local tool", F(self.fm, 11), bg=INK2, fg=MUTED, padx=10, pady=3).pack(side="right")

        # Title row
        head = tk.Frame(root, bg=INK)
        head.pack(fill="x", padx=36, pady=(12, 8))
        self.lbl(head, "Pull", F(self.fd, 56)).pack(side="left")
        self.lbl(head, "yt-dlp downloader", F(self.fm, 13), fg=MUTED).pack(side="left", padx=(14, 0), pady=(20, 0))
        self.lbl(head, f"yt-dlp {ytdlp_version()}", F(self.fm, 11), bg=INK2, fg=MUTED,
                 padx=10, pady=3).pack(side="right", anchor="n", pady=(6, 0))
        tk.Frame(root, bg=LINE, height=1).pack(fill="x")

        content = tk.Frame(root, bg=INK)
        content.pack(fill="both", expand=True, padx=36, pady=(14, 18))
        content.columnconfigure(0, weight=3, uniform="c")
        content.columnconfigure(1, weight=2, uniform="c")
        content.rowconfigure(0, weight=1)

        # ---- Work order
        wo = tk.Frame(content, bg=PAPER)
        wo.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        wh = tk.Frame(wo, bg="#DCCFB8", height=32)
        wh.pack(fill="x")
        wh.pack_propagate(False)
        self.lbl(wh, "Work order", F(self.fm, 12), bg="#DCCFB8", fg=INK).pack(side="left", padx=18)
        self.lbl(wh, "RXV-009", F(self.fm, 11), bg="#DCCFB8", fg=BROWN).pack(side="right", padx=18)
        wb = tk.Frame(wo, bg=PAPER)
        wb.pack(fill="both", expand=True, padx=18, pady=12)

        # submit (packed first so it always keeps its space)
        sub = tk.Frame(wb, bg=PAPER)
        sub.pack(fill="x", side="bottom")
        self.dl = self.btn(sub, "Download", self.start_download, bg=ORANGE,
                           font=F(self.fm, 15), pady=7)
        self.dl.pack(fill="x")
        self.can = self.btn(sub, "Cancel", self.cancel_job, font=F(self.fm, 12), pady=3)
        self.lbl(sub, textvariable=self.status, font=F(self.fm, 11), bg=PAPER, fg=BROWN).pack(anchor="w", pady=(6, 0))


        def section(num, title, req=False):
            f = tk.Frame(wb, bg=PAPER)
            f.pack(fill="x", pady=(0, 7))
            h = tk.Frame(f, bg=PAPER)
            h.pack(fill="x")
            self.lbl(h, num, F(self.fm, 11), bg=INK, fg=CREAM, padx=6).pack(side="left")
            self.lbl(h, title, F(self.fm, 13), bg=PAPER, fg=INK, padx=8).pack(side="left")
            if req:
                self.lbl(h, "required", F(self.fm, 11), bg=PAPER, fg=BROWN).pack(side="right")
            tk.Frame(f, bg=BROWN, height=1).pack(fill="x", pady=(4, 5))
            return f

        def hint(parent, text):
            self.lbl(parent, text, F(self.fm, 11), bg=PAPER, fg=BROWN).pack(anchor="w", pady=(4, 0))

        # 01 link
        s = section("01", "Link", req=True)
        row = tk.Frame(s, bg=PAPER)
        row.pack(fill="x")
        self.url_e = tk.Entry(row, textvariable=self.url, bg=CREAM, fg=INK, insertbackground=ORANGE,
                              font=F(self.fm, 13), relief="solid", bd=1)
        self.url_e.pack(side="left", fill="x", expand=True, ipady=6)
        self.btn(row, "Paste", self.paste_url, padx=14).pack(side="left", padx=(8, 0), ipady=2)
        hint(s, "Any link yt-dlp supports: a video, a song or a playlist.")

        # 02 mode
        s = section("02", "What to download")
        mrow = tk.Frame(s, bg=PAPER)
        mrow.pack(fill="x")
        self.bv = self._mode_card(mrow, "Video", "mp4 · mkv · webm", "video")
        self.bv.pack(side="left", fill="x", expand=True)
        self.ba = self._mode_card(mrow, "Audio", "mp3 · m4a · opus · wav · flac", "audio")
        self.ba.pack(side="left", fill="x", expand=True, padx=(8, 0))

        # 03 format
        s = section("03", "Format and quality")
        self.fmt_box = tk.Frame(s, bg=PAPER)
        self.fmt_box.pack(fill="x")
        self.vf = tk.Frame(self.fmt_box, bg=PAPER)
        self._combo_pair(self.vf, "Quality", self.video_quality,
                         ["best", "2160p", "1440p", "1080p", "720p", "480p", "360p"],
                         "Container", self.container, ["mp4", "mkv", "webm"])
        self.af2 = tk.Frame(self.fmt_box, bg=PAPER)
        self._combo_pair(self.af2, "Audio format", self.audio_format,
                         ["mp3", "m4a", "opus", "wav", "flac"],
                         "MP3 bitrate (k)", self.audio_quality, ["320", "256", "192", "128", "96"])
        hint(s, "Best available video and audio, merged into the chosen container.")

        # 04 destination
        s = section("04", "Save to")
        row = tk.Frame(s, bg=PAPER)
        row.pack(fill="x")
        self.out_e = tk.Entry(row, textvariable=self.output_dir, bg=CREAM, fg=INK, insertbackground=ORANGE,
                              font=F(self.fm, 13), relief="solid", bd=1)
        self.out_e.pack(side="left", fill="x", expand=True, ipady=6)
        self.btn(row, "Downloads", self.set_downloads, padx=14).pack(side="left", padx=(8, 0), ipady=2)
        hint(s, "The folder must already exist.")

        # 05 extras
        s = section("05", "Extras")
        for var, title, desc in [
            (self.embed_metadata, "Embed metadata", "title, artist and date inside the file"),
            (self.embed_thumbnail, "Embed thumbnail", "keep the cover art with the file"),
            (self.playlist, "Allow playlists", "download every item in the link"),
        ]:
            tk.Checkbutton(s, text=f"{title}  ·  {desc}", variable=var, bg=PAPER, fg=INK,
                           selectcolor=CREAM, activebackground=PAPER, activeforeground=INK,
                           font=F(self.fm, 11), anchor="w", cursor="hand2", pady=0).pack(fill="x")

        # ---- Right column
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
        self.tm = tk.StringVar(value="Video")
        self.tq = tk.StringVar(value="Best")
        self.ts = tk.StringVar(value="MP4")
        self.tf = tk.StringVar(value="Downloads")
        self.tff = tk.StringVar(value="Checking")
        for l, v in [("Mode", self.tm), ("Quality", self.tq), ("Save as", self.ts),
                     ("Folder", self.tf), ("Engine", tk.StringVar(value=ytdlp_version())), ("ffmpeg", self.tff)]:
            fr = tk.Frame(tb, bg=CREAM)
            fr.pack(fill="x", pady=1)
            self.lbl(fr, l, F(self.fm, 11), bg=CREAM, fg=BROWN).pack(side="left")
            self.lbl(fr, textvariable=v, font=F(self.fm, 11), bg=CREAM, fg=INK).pack(side="right")
            tk.Frame(tb, bg=BROWN, height=1).pack(fill="x", pady=3)
        self.pbar = ttk.Progressbar(tb, mode="determinate", style="Pull.Horizontal.TProgressbar", maximum=100)
        self.pbar.pack(fill="x", pady=(8, 4))
        self.pp = self.lbl(tb, "Idle  0%", F(self.fm, 11), bg=CREAM, fg=INK)
        self.pp.pack(anchor="e")
        self.btn(tb, "Open folder", self.open_folder, bg=PAPER, fg=INK, font=F(self.fm, 12), pady=3).pack(fill="x", pady=(10, 0))

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

        self.set_mode("video")
        self.update_ticket()

    def _mode_card(self, parent, title, sub, mode):
        card = tk.Frame(parent, bg=PAPER, highlightthickness=1, highlightbackground=INK, cursor="hand2")
        t = self.lbl(card, title, F(self.fm, 13), bg=PAPER, fg=INK, cursor="hand2")
        t.pack(pady=(5, 0))
        s = self.lbl(card, sub, F(self.fm, 11), bg=PAPER, fg=INK, cursor="hand2")
        s.pack(pady=(0, 5))
        card.parts = (t, s)
        for w in (card, t, s):
            w.bind("<Button-1>", lambda _e, m=mode: self.set_mode(m))
        return card

    def _paint_card(self, card, active):
        bg, fg = (INK, CREAM) if active else (PAPER, INK)
        card.configure(bg=bg)
        for p in card.parts:
            p.configure(bg=bg, fg=fg)

    def _combo_pair(self, parent, l1, v1, vals1, l2, v2, vals2):
        parent.pack(fill="x")
        parent.columnconfigure(0, weight=1, uniform="cb")
        parent.columnconfigure(1, weight=1, uniform="cb")
        self.lbl(parent, l1, F(self.fm, 11), bg=PAPER, fg=BROWN).grid(row=0, column=0, sticky="w")
        self.lbl(parent, l2, F(self.fm, 11), bg=PAPER, fg=BROWN).grid(row=0, column=1, sticky="w", padx=(16, 0))
        ttk.Combobox(parent, textvariable=v1, values=vals1, state="readonly", font=F(self.fm, 13)
                     ).grid(row=1, column=0, sticky="ew", pady=(3, 0))
        ttk.Combobox(parent, textvariable=v2, values=vals2, state="readonly", font=F(self.fm, 13)
                     ).grid(row=1, column=1, sticky="ew", padx=(16, 0), pady=(3, 0))

    # ------------------------------------------------------------ state
    def set_mode(self, m):
        self.mode.set(m)
        self._paint_card(self.bv, m == "video")
        self._paint_card(self.ba, m == "audio")
        if m == "video":
            self.af2.pack_forget()
            self.vf.pack(fill="x")
        else:
            self.vf.pack_forget()
            self.af2.pack(fill="x")
        self.update_ticket()

    def update_ticket(self):
        self.tm.set(self.mode.get().capitalize())
        if self.mode.get() == "video":
            self.tq.set(self.video_quality.get().capitalize())
            self.ts.set(self.container.get().upper())
        else:
            fmt = self.audio_format.get()
            self.tq.set(f"MP3 {self.audio_quality.get()}k" if fmt == "mp3" else fmt.upper())
            self.ts.set(fmt.upper())
        self.tf.set(Path(self.output_dir.get()).name or "Folder")

    def paste_url(self):
        try:
            self.url.set(self.clipboard_get().strip())
        except tk.TclError:
            pass

    def set_downloads(self):
        self.output_dir.set(os.path.join(os.path.expanduser("~"), "Downloads"))

    def log_write(self, text):
        self.logt.configure(state="normal")
        self.logt.insert("end", text)
        self.logt.see("end")
        self.logt.configure(state="disabled")

    def set_progress(self, pct, label):
        self.pbar.configure(value=pct)
        self.pp.configure(text=label)

    # ------------------------------------------------------------ job
    def start_download(self):
        url = self.url.get().strip()
        if not url:
            messagebox.showinfo("Link needed", "Paste a link first, then press Download.")
            return
        if not os.path.isdir(self.output_dir.get()):
            messagebox.showinfo("Folder not found", "That folder doesn't exist. Pick another one.")
            return
        self.cancel_flag.clear()
        self.dl.configure(state="disabled", bg=PAPER, fg=BROWN)
        self.can.pack(fill="x", pady=(6, 0))
        self.set_progress(0, "Starting  0%")
        self.logt.configure(state="normal")
        self.logt.delete("1.0", "end")
        self.logt.configure(state="disabled")
        self.status.set("Working on it...")
        self.tno.configure(text="Running")
        # Tk variables are read here, on the UI thread; the worker only gets plain values.
        args = self.build_args(url)
        threading.Thread(target=self.download, args=(args,), daemon=True).start()

    def cancel_job(self):
        self.cancel_flag.set()
        self.status.set("Stopping...")

    def build_args(self, url):
        a = ["--ignore-config", "--no-colors", "--newline", "--progress"]
        if self.mode.get() == "audio":
            fmt = self.audio_format.get()
            a += ["-f", "bestaudio/best", "-x", "--audio-format", fmt]
            if fmt == "mp3":
                a += ["--audio-quality", f"{self.audio_quality.get()}K"]
        else:
            q = self.video_quality.get()
            if q == "best":
                fs = "bestvideo+bestaudio/best"
            else:
                h = q[:-1]
                fs = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]"
            a += ["-f", fs, "--merge-output-format", self.container.get()]
        if self.embed_metadata.get():
            a.append("--embed-metadata")
        if self.embed_thumbnail.get():
            a.append("--embed-thumbnail")
        a.append("--yes-playlist" if self.playlist.get() else "--no-playlist")
        a += ["-o", os.path.join(self.output_dir.get(), "%(title)s.%(ext)s"), url]
        return a

    def _hook(self, d):
        if self.cancel_flag.is_set():
            raise JobCancelled()
        st = d.get("status")
        if st == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            pct = (done / total * 100) if total else 0
            speed = d.get("_speed_str", "").strip()
            label = f"Downloading  {int(pct)}%" + (f"  ·  {speed}" if speed else "")
            self.after(0, self.set_progress, pct, label)
        elif st == "finished":
            self.after(0, self.set_progress, 100, "Finishing up...")

    def download(self, args):
        try:
            ff = ensure_ffmpeg(progress=lambda m: self.after(0, self.status.set, m))
            if ff:
                args = args[:-1] + ["--ffmpeg-location", str(Path(ff).parent)] + args[-1:]
            self.after(0, self.status.set, "Working on it...")
            import yt_dlp
            self.after(0, self.log_write, "$ yt-dlp " + subprocess.list2cmdline(args[1:]) + "\n\n")
            parsed = yt_dlp.parse_options(args)
            opts = parsed.ydl_opts
            opts["logger"] = UiLogger(lambda t: self.after(0, self.log_write, t))
            opts["progress_hooks"] = [self._hook]
            opts["noprogress"] = True
            with yt_dlp.YoutubeDL(opts) as ydl:
                code = ydl.download(parsed.urls)
            if code == 0:
                self.after(0, self._done, True, "Done. Your file is in the folder.", "Done")
            else:
                self.after(0, self._done, False, f"That didn't work (code {code}). See the log.", "Failed")
        except JobCancelled:
            self.after(0, self._done, False, "Stopped.", "Stopped")
        except Exception as e:  # yt-dlp wraps a cancelled hook in DownloadError sometimes
            if self.cancel_flag.is_set():
                self.after(0, self._done, False, "Stopped.", "Stopped")
            else:
                self.after(0, self._done, False, "Something went wrong.", "Error", str(e))

    def _done(self, ok, status, ticket, err=None):
        self.status.set(status)
        self.tno.configure(text=ticket)
        self.dl.configure(state="normal", bg=ORANGE, fg=INK)
        self.can.pack_forget()
        self.set_progress(100 if ok else 0, "Done  100%" if ok else "Idle  0%")
        if ok:
            messagebox.showinfo("Done", "Download complete.")
        elif err:
            messagebox.showwarning("Something went wrong", err)

    def open_folder(self):
        path = self.output_dir.get()
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
