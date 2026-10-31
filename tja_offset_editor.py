import os
import re
import sys
import queue
import threading
import tkinter as tk
from tkinter import messagebox, filedialog
from tkinter.scrolledtext import ScrolledText

# ============================================================
# Settings
# ============================================================

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_SONGS_FOLDER = os.path.join(BASE_DIR, "Songs")

APP_ID = "tja.offset.editor"


def resource_path(name):
    # When packaged as an exe, bundled files are extracted to sys._MEIPASS
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


# ============================================================
# OFFSET regular expression
# ============================================================

OFFSET_PATTERN = re.compile(
    r"^\s*(//\s*)?OFFSET\s*:\s*"
    r"([-+]?(?:\d+(?:\.\d*)?|\.\d+))"
    r"\s*$",
    re.IGNORECASE
)

# ============================================================
# Core logic
# ============================================================


def find_offsets(lines):
    offsets = []
    for i, line in enumerate(lines):
        match = OFFSET_PATTERN.match(line)
        if match:
            offsets.append({
                "index": i,
                "commented": match.group(1) is not None,
                "value": float(match.group(2))
            })
    return offsets


def remove_blank_lines_after_offset(lines):
    result = []
    offset_found = False

    for line in lines:
        if OFFSET_PATTERN.match(line):
            offset_found = True
            result.append(line)
            continue

        if offset_found and line.strip() == "":
            continue

        if offset_found and line.strip() != "":
            offset_found = False

        result.append(line)

    return result


def _rebuild_without_offsets(lines, offsets):
    """Remove all OFFSET lines. Returns (new lines, index where the first OFFSET belongs)."""
    offset_indices = {item["index"] for item in offsets}
    new_lines = [l for i, l in enumerate(lines) if i not in offset_indices]

    first_offset_index = offsets[0]["index"]
    insert_index = sum(
        1 for i in range(first_offset_index) if i not in offset_indices
    )
    return new_lines, insert_index


def adjust_offset_file(filepath, x, log):
    with open(filepath, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

    offsets = find_offsets(lines)

    if not offsets:
        log(f"  [Skipped] No OFFSET found: {filepath}")
        return False

    original = next((o for o in offsets if o["commented"]), offsets[0])
    original_value = original["value"]
    new_offset = original_value + x

    new_lines, insert_index = _rebuild_without_offsets(lines, offsets)

    new_lines.insert(insert_index, f"//OFFSET: {original_value:.3f}\n")
    new_lines.insert(insert_index + 1, f"OFFSET: {new_offset:.3f}\n")

    lines = remove_blank_lines_after_offset(new_lines)

    with open(filepath, "w", encoding="utf-8-sig") as f:
        f.writelines(lines)

    return True


def restore_offset_file(filepath, log):
    with open(filepath, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

    offsets = find_offsets(lines)

    if not offsets:
        log(f"  [Skipped] No OFFSET found: {filepath}")
        return False

    original = next((o for o in offsets if o["commented"]), offsets[0])
    original_value = original["value"]

    new_lines, insert_index = _rebuild_without_offsets(lines, offsets)
    new_lines.insert(insert_index, f"OFFSET: {original_value:.3f}\n")

    lines = remove_blank_lines_after_offset(new_lines)

    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(lines)

    return True


def check_offset_file(filepath, log):
    with open(filepath, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

    offsets = find_offsets(lines)

    if not offsets:
        log(f"  [Skipped] No OFFSET found: {filepath}")
        return None

    original = next((o for o in offsets if o["commented"]), None)

    if original is not None:
        active = [o for o in offsets if not o["commented"]]
        if not active:
            log(f"  [Cannot determine x] No active OFFSET: {filepath}")
            return None
        return active[0]["value"] - original["value"]

    if len(offsets) == 1:
        return 0.0

    log(f"  [Cannot determine x] Multiple OFFSET lines but no //OFFSET: {filepath}")
    return None


def find_tja_files(folder):
    tja_files = []
    if not os.path.isdir(folder):
        return tja_files

    for root, dirs, files in os.walk(folder):
        for filename in files:
            if filename.lower().endswith(".tja"):
                tja_files.append(os.path.join(root, filename))

    return tja_files


# ============================================================
# GUI
# ============================================================

FONT = "Segoe UI"

BG = "#f4f6fb"
CARD = "#ffffff"
ACCENT = "#3b6fe0"
ACCENT_DARK = "#2f5bc0"
TEXT = "#222a3a"
SUBTEXT = "#6b7385"
BORDER = "#dfe3ee"
DANGER = "#d9534f"
DANGER_DARK = "#b9403c"


class FlatButton(tk.Button):
    """Flat-style button with a hover effect"""

    def __init__(self, master, bg=ACCENT, hover=ACCENT_DARK, fg="white", **kw):
        super().__init__(
            master,
            bg=bg, fg=fg,
            activebackground=hover, activeforeground=fg,
            disabledforeground="#c9cfdd",
            relief="flat", bd=0, cursor="hand2",
            **kw
        )
        self._bg, self._hover = bg, hover
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))

    def _set_hover(self, on):
        if str(self["state"]) == "normal":
            self.config(bg=self._hover if on else self._bg)


class App(tk.Tk):

    def __init__(self):
        # Tell Windows this is its own app so the taskbar uses our icon
        # (must be done before the window is created)
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass

        super().__init__()

        # default=... applies the icon to every window of this app
        # (main window, taskbar, and any dialog that is a child of it)
        try:
            self.iconbitmap(default=resource_path("icon.ico"))
        except Exception:
            pass

        self.title("TJA OFFSET EDITOR")
        self.geometry("640x740")
        self.minsize(560, 640)
        self.configure(bg=BG)

        self.songs_folder = DEFAULT_SONGS_FOLDER
        self.q = queue.Queue()
        self.busy = False
        self.action_buttons = []
        self._repeat_job = None

        self._build_ui()
        self.after(50, self._poll_queue)

    # --------------------------------------------------------
    # Build UI
    # --------------------------------------------------------

    def _card(self, parent, title):
        outer = tk.Frame(parent, bg=BORDER)
        outer.pack(fill="x", pady=(0, 12))

        card = tk.Frame(outer, bg=CARD)
        card.pack(fill="x", padx=1, pady=1)

        tk.Label(
            card, text=title, bg=CARD, fg=TEXT,
            font=(FONT, 12, "bold"), anchor="w"
        ).pack(fill="x", padx=16, pady=(12, 4))

        body = tk.Frame(card, bg=CARD)
        body.pack(fill="x", padx=16, pady=(0, 14))
        return body

    def _build_ui(self):

        root = tk.Frame(self, bg=BG)
        root.pack(fill="both", expand=True, padx=18, pady=16)

        tk.Label(
            root, text="TJA OFFSET EDITOR", bg=BG, fg=TEXT,
            font=(FONT, 18, "bold"), anchor="w"
        ).pack(fill="x")

        # ---- Songs folder ----
        folder_row = tk.Frame(root, bg=BG)
        folder_row.pack(fill="x", pady=(6, 12))

        self.folder_var = tk.StringVar(value=self.songs_folder)

        tk.Label(
            folder_row, textvariable=self.folder_var, bg=BG, fg=SUBTEXT,
            font=(FONT, 9), anchor="w", justify="left"
        ).pack(side="left", fill="x", expand=True)

        FlatButton(
            folder_row, text="Select Folder", bg="#8791a8", hover="#6f7890",
            font=(FONT, 9), padx=10, pady=3,
            command=self.choose_folder
        ).pack(side="right")

        # ---- Function 1: Adjust OFFSET ----
        body1 = self._card(root, "1. Adjust OFFSET")

        tk.Label(
            body1,
            text="The more negative x is, the more likely hits are judged too early; "
                 "the more positive, the more likely too late (seconds).",
            bg=CARD, fg=SUBTEXT, font=(FONT, 9), anchor="w",
            justify="left", wraplength=540
        ).pack(fill="x", pady=(0, 8))

        row = tk.Frame(body1, bg=CARD)
        row.pack()

        self.x_var = tk.StringVar(value="0.000")

        btn_minus = FlatButton(row, text="−", font=(FONT, 18, "bold"), width=3)
        btn_minus.pack(side="left")
        self._bind_repeat(btn_minus, -0.001)

        self.x_entry = tk.Entry(
            row, textvariable=self.x_var, width=9, justify="center",
            font=(FONT, 20, "bold"), relief="solid", bd=1,
            highlightthickness=0, fg=TEXT
        )
        self.x_entry.pack(side="left", padx=12, ipady=4)

        btn_plus = FlatButton(row, text="+", font=(FONT, 18, "bold"), width=3)
        btn_plus.pack(side="left")
        self._bind_repeat(btn_plus, +0.001)

        self.action_buttons += [btn_minus, btn_plus]

        apply_btn = FlatButton(
            body1, text="Apply to All TJA", font=(FONT, 11, "bold"),
            pady=7, command=self.on_adjust
        )
        apply_btn.pack(fill="x", pady=(12, 0))
        self.action_buttons.append(apply_btn)

        # ---- Function 2: Check ----
        body2 = self._card(root, "2. Check Current OFFSET Adjustment (x)")

        row2 = tk.Frame(body2, bg=CARD)
        row2.pack(fill="x")

        query_btn = FlatButton(
            row2, text="Check", font=(FONT, 11, "bold"),
            padx=24, pady=7, command=self.on_query
        )
        query_btn.pack(side="left")
        self.action_buttons.append(query_btn)

        self.result_var = tk.StringVar(value="—")
        tk.Label(
            row2, textvariable=self.result_var, bg=CARD, fg=ACCENT,
            font=(FONT, 20, "bold")
        ).pack(side="left", padx=20)

        # ---- Function 3: Restore ----
        body3 = self._card(root, "3. Restore Original OFFSET + Clean Up")

        tk.Label(
            body3,
            text="Restores the original OFFSET and removes extra OFFSET lines "
                 "and the blank lines after them.",
            bg=CARD, fg=SUBTEXT, font=(FONT, 9), anchor="w",
            justify="left", wraplength=540
        ).pack(fill="x", pady=(0, 8))

        restore_btn = FlatButton(
            body3, text="Restore & Clean Up", bg=DANGER, hover=DANGER_DARK,
            font=(FONT, 11, "bold"), pady=7, command=self.on_restore
        )
        restore_btn.pack(fill="x")
        self.action_buttons.append(restore_btn)

        # ---- Log ----
        log_header = tk.Frame(root, bg=BG)
        log_header.pack(fill="x")

        tk.Label(
            log_header, text="Log", bg=BG, fg=SUBTEXT,
            font=(FONT, 9), anchor="w"
        ).pack(side="left")

        clear_lbl = tk.Label(
            log_header, text="Clear", bg=BG, fg=ACCENT,
            font=(FONT, 9, "underline"), cursor="hand2"
        )
        clear_lbl.pack(side="right")
        clear_lbl.bind("<Button-1>", lambda e: self._clear_log())

        self.log_box = ScrolledText(
            root, height=8, font=("Consolas", 9), bg=CARD, fg=TEXT,
            relief="solid", bd=1, state="disabled", wrap="none"
        )
        self.log_box.pack(fill="both", expand=True, pady=(4, 0))

    # --------------------------------------------------------
    # Hold-to-repeat +/-
    # --------------------------------------------------------

    def _bind_repeat(self, button, delta):
        button.bind("<ButtonPress-1>", lambda e: self._start_repeat(delta))
        button.bind("<ButtonRelease-1>", lambda e: self._stop_repeat())

    def _start_repeat(self, delta):
        if self.busy:
            return
        self._step(delta)
        self._repeat_job = self.after(400, lambda: self._repeat(delta))

    def _repeat(self, delta):
        self._step(delta)
        self._repeat_job = self.after(40, lambda: self._repeat(delta))

    def _stop_repeat(self):
        if self._repeat_job is not None:
            self.after_cancel(self._repeat_job)
            self._repeat_job = None

    def _step(self, delta):
        value = self._read_x(silent=True)
        if value is None:
            value = 0.0
        new_value = round(value + delta, 3)
        if abs(new_value) < 0.0005:
            new_value = 0.0
        self.x_var.set(f"{new_value:.3f}")

    def _read_x(self, silent=False):
        try:
            return float(self.x_var.get().strip())
        except ValueError:
            if not silent:
                messagebox.showerror("Error", "x is not a valid number.", parent=self)
            return None

    # --------------------------------------------------------
    # Log / busy state
    # --------------------------------------------------------

    def _log(self, text):
        self.log_box.config(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def _clear_log(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")

    def _set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for b in self.action_buttons:
            b.config(state=state)
        self.x_entry.config(state=state)
        self.config(cursor="watch" if busy else "")

    def _poll_queue(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "log":
                    self._log(data)
                elif kind == "result":
                    self.result_var.set(data)
                elif kind == "x":
                    self.x_var.set(data)
                elif kind == "done":
                    self._set_busy(False)
        except queue.Empty:
            pass
        self.after(50, self._poll_queue)

    def _run_in_thread(self, func):
        if self.busy:
            return
        self._set_busy(True)

        def worker():
            try:
                func(lambda s: self.q.put(("log", s)))
            except Exception as e:
                self.q.put(("log", f"[Error] {e}"))
            finally:
                self.q.put(("done", None))

        threading.Thread(target=worker, daemon=True).start()

    # --------------------------------------------------------
    # Choose folder
    # --------------------------------------------------------

    def choose_folder(self):
        initial = self.songs_folder if os.path.isdir(self.songs_folder) else BASE_DIR
        folder = filedialog.askdirectory(
            title="Select Songs Folder", initialdir=initial, parent=self
        )
        if folder:
            self.songs_folder = os.path.normpath(folder)
            self.folder_var.set(self.songs_folder)

    def _get_tja_files(self):
        files = find_tja_files(self.songs_folder)
        if not files:
            messagebox.showwarning(
                "No TJA Found",
                f"No TJA files were found in:\n{self.songs_folder}\n\n"
                "Please check the Songs folder location, or click \"Select Folder\".",
                parent=self
            )
        return files

    # --------------------------------------------------------
    # Function 1: Adjust
    # --------------------------------------------------------

    def on_adjust(self):
        x = self._read_x()
        if x is None:
            return

        files = self._get_tja_files()
        if not files:
            return

        folder = self.songs_folder

        def task(log):
            log("------------------------------------")
            log(f"Adjusting: original OFFSET + ({x:+.3f})")
            log(f"Found {len(files)} TJA file(s)")
            ok = 0
            for filepath in files:
                rel = os.path.relpath(filepath, folder)
                try:
                    if adjust_offset_file(filepath, x, log):
                        ok += 1
                        log(f"  [Done] {rel}")
                except Exception as e:
                    log(f"  [Error] {rel}: {e}")
            log(f"OFFSET adjustment finished ({ok}/{len(files)}).")

        self._run_in_thread(task)

    # --------------------------------------------------------
    # Function 2: Check
    # --------------------------------------------------------

    def on_query(self):
        files = self._get_tja_files()
        if not files:
            return

        folder = self.songs_folder

        def task(log):
            log("------------------------------------")
            log(f"Checking x ({len(files)} TJA file(s))")
            x_values = []
            for filepath in files:
                rel = os.path.relpath(filepath, folder)
                try:
                    x = check_offset_file(filepath, log)
                    if x is None:
                        continue
                    x_values.append(round(x, 3))
                    log(f"  {rel}    x = {x:+.3f}")
                except Exception as e:
                    log(f"  [Error] {rel}: {e}")

            if not x_values:
                self.q.put(("result", "Unknown"))
                log("No songs could be determined.")
                return

            unique = sorted(set(x_values))

            if len(unique) == 1:
                self.q.put(("result", f"x = {unique[0]:+.3f}"))
                self.q.put(("x", f"{unique[0]:.3f}"))
                log(f"x for all determinable songs = {unique[0]:+.3f}")
            else:
                self.q.put(("result", f"{len(unique)} different values"))
                log("x values across songs:")
                for v in unique:
                    log(f"  x = {v:+.3f}  ({x_values.count(v)} song(s))")

            log("Check finished.")

        self._run_in_thread(task)

    # --------------------------------------------------------
    # Function 3: Restore + clean up
    # --------------------------------------------------------

    def on_restore(self):
        files = self._get_tja_files()
        if not files:
            return

        if not messagebox.askyesno(
            "Confirm",
            f"Restore and clean up {len(files)} TJA file(s)?",
            parent=self
        ):
            return

        folder = self.songs_folder

        def task(log):
            log("------------------------------------")
            log("Restore original OFFSET + clean up")
            log(f"Found {len(files)} TJA file(s)")
            ok = 0
            for filepath in files:
                rel = os.path.relpath(filepath, folder)
                try:
                    if restore_offset_file(filepath, log):
                        ok += 1
                        log(f"  [Done] {rel}")
                except Exception as e:
                    log(f"  [Error] {rel}: {e}")
            log(f"Restore and clean up finished ({ok}/{len(files)}).")
            self.q.put(("result", "x = +0.000"))
            self.q.put(("x", "0.000"))

        self._run_in_thread(task)


if __name__ == "__main__":
    App().mainloop()