# LocalScribe — transcribe your recordings on your own computer

LocalScribe turns a folder of audio or video recordings into transcripts
(subtitles and spreadsheets), **entirely on your own computer**. Nothing is
uploaded anywhere. No accounts, no sign-ups.

## What you need

- A Windows 10/11 computer, or a Mac (macOS 13 or newer for Intel Macs,
  macOS 14 or newer for Apple Silicon).
- Internet **for the first run only** (it downloads its own tools, about 1 GB
  total). After that it works offline.
- About 2 GB of free disk space.
- Tip: put this folder somewhere that is **not** synced by OneDrive/Dropbox.

## Setting up (one time, about 5–10 minutes)

1. Download this folder: click the green **Code** button on this page →
   **Download ZIP**, then unzip it. (If you know git: `git clone` works too
   and avoids one security prompt.)
2. Open the unzipped folder.
3. **On a Mac:** double-click **`Start Transcriber.command`**.
   The first time, macOS may say it "cannot verify the developer":
   open **System Settings → Privacy & Security**, scroll down, and click
   **Open Anyway**.
   **On Windows:** double-click **`Start Transcriber.bat`**.
   If a blue "Windows protected your PC" box appears, click
   **More info → Run anyway**.
4. A black text window opens and sets things up (first time only — a few
   minutes). **Leave that window open.** Your web browser then opens the
   LocalScribe page automatically.

## Using it

1. Click **Browse…** and choose the folder with your recordings.
2. Pick how to transcribe:
   - **Non-verbatim** (recommended): cleaned-up text, easiest to read.
   - **Verbatim**: keeps "um", "uh", repetitions and false starts — useful for
     detailed analysis. (It keeps many more hesitations than normal, but no
     software can capture every single one.)
3. Pick accuracy vs speed (**Standard** is right for almost everyone).
4. Click **Start transcription** and leave the laptop plugged in with the lid
   open. You can close the browser tab and come back — the work continues.

### Try it out first

The download from GitHub already includes two sample folders you can point
LocalScribe at straight away:

- **`example_audio/`** — a one-minute sample recording (.wav)
- **`example_video/`** — a short TED talk video (.mp4; see its
  ATTRIBUTION.txt for credits)

### What you get

When it finishes, click **Open output folder**. Each transcript is named
after the recording plus a tag showing how it was transcribed —
`.clean` for Non-verbatim, `.verbatim` for Verbatim — so you can make both
versions of the same recording without one overwriting the other:

| File | What it is |
|---|---|
| `recording.clean.srt` / `recording.clean.vtt` | Subtitle files (timestamps + text) |
| `recording.clean.csv` | Spreadsheet — opens in Excel, one row per sentence with times |
| `recording.clean.json` | Full detail including word-level timestamps |
| `recording.verbatim.srt` … | The same four files, from Verbatim mode |

Already-transcribed files are skipped automatically if you run the same
folder again — so it is always safe to re-run.

## Using an NVIDIA graphics card (Windows, optional)

If your Windows computer has an NVIDIA graphics card, transcription can run
much faster. Tick **"Use NVIDIA graphics card"** on the setup screen — the
app downloads the extra support files (about 1.5 GB, one time) and restarts
itself. If the graphics card is ever unavailable, LocalScribe automatically
falls back to the normal (CPU) mode and tells you, so transcription always
works. Unticking the box switches back to CPU immediately.

This option only appears on Windows computers with an NVIDIA graphics card.
Macs don't support this and don't need any changes.

## Something not working?

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md). The universal fix:
**delete the `.managed` folder inside this folder, then double-click the
launcher again.**
