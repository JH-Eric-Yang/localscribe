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

Want to try it out first? Point it at the included `example_audio` (or
`example_video`) folder — each contains a one-minute sample recording.

When it finishes, click **Open output folder**. For each recording you get:

| File | What it is |
|---|---|
| `recording.srt` / `recording.vtt` | Subtitle files (timestamps + text) |
| `recording.csv` | Spreadsheet — opens in Excel, one row per sentence with times |
| `recording.json` | Full detail including word-level timestamps |

Already-transcribed files are skipped automatically if you run the same
folder again — so it is always safe to re-run.

## Something not working?

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md). The universal fix:
**delete the `.managed` folder inside this folder, then double-click the
launcher again.**
