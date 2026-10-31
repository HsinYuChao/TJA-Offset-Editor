# TJA OFFSET EDITOR

TJA is a file format created for Taiko simulators to have playable charts. This is a small Windows tool for adjusting the `OFFSET` value of many TJA chart files at once, with a simple point-and-click interface.

## Features

- **Adjust OFFSET** – shift the `OFFSET` of every TJA file in your Songs folder by the same amount, using `−` / `+` buttons or by typing a value.
- **Check** – shows the adjustment `x` currently applied to your songs.
- **Restore & Clean Up** – puts every file back to its original `OFFSET` and removes leftover `OFFSET` lines and the blank lines after them.
- Works recursively: all TJA files in subfolders of the chosen folder are processed.
- No installation and no extra dependencies (standard Python library only).

## How it works

The tool keeps your original value in a commented line so it can always be restored.

Before:

```
OFFSET:-1.000
```

After applying `x = -0.050`:

```
//OFFSET: -1.000
OFFSET: -1.050
```

- `x` is the **total** adjustment relative to the original value, not a running total. Applying `-0.050` and then `-0.030` results in the original `OFFSET − 0.030`.
- A more negative `x` makes hits more likely to be judged **too early**; a more positive `x` makes them more likely to be judged **too late**.
- Restore uses the first `//OFFSET:` line as the original value. If there is none, the first `OFFSET:` line is kept.

## Download and usage

1. Download the latest `tja_offset_editor.exe` from the [Releases](../../releases) page.
2. Put the exe **next to your `Songs` folder** (so that `Songs` is in the same folder as the exe), then double-click it.
   Alternatively, click **Select Folder** in the app and choose any folder that contains your TJA files.
3. Use the three sections:
   1. Set `x` with `−` / `+` or type it, then click **Apply to All TJA**.
   2. Click **Check** to see the current `x`.
   3. Click **Restore & Clean Up** to go back to the original `OFFSET`.

The log at the bottom shows what happened to each file.

## Run from source

Requires Python 3.8+ with Tkinter (included in the standard Windows installer from python.org).

```bash
python tja_offset_editor.py
```

`icon.ico` should be in the same folder as the script (the app still runs without it, just with the default icon).

## Build the exe

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --clean --icon=icon.ico --add-data "icon.ico;." tja_offset_editor.py
```

The executable is created in `dist/`.

## Notes

- Windows only.
- Some antivirus programs flag PyInstaller executables as suspicious. This is a known false positive; you can build the exe yourself from the source above.