# Troubleshooting

**The universal fix for almost everything:** close the black text window,
delete the `.managed` folder inside the LocalScribe folder, and double-click
the launcher again. Setup re-runs from scratch and resumes any finished work.

## "Nothing happened" when I double-clicked

- A LocalScribe browser tab may already be open — double-clicking again just
  reopens the existing page. Check your browser tabs.
- **Mac:** if you saw a security warning, go to System Settings → Privacy &
  Security → click **Open Anyway**, then double-click again. If that option
  never appears, drag `Start Transcriber.command` onto the Terminal app icon
  and press Return.
- **Windows:** click **More info → Run anyway** on the blue SmartScreen box.
  If nothing appears at all, right-click the `.bat` file → Properties → tick
  **Unblock** → OK, then try again.

## "Could not download the setup tool" / "Could not download the speech model"

The first run needs internet access to `astral.sh`, `github.com`, and
`huggingface.co`. University networks sometimes block these:
- Try again on a different network (home Wi-Fi or a phone hotspot). This is a
  **one-time** download; afterwards LocalScribe works offline.
- Downloads resume where they left off — just double-click again.
- If the download bar stops moving, leave it alone for a couple of minutes:
  LocalScribe notices a stuck connection, reconnects by itself, and carries on
  from where it stopped. If it gives up, press **Retry** — nothing already
  downloaded is lost.

## It seems stuck / is it frozen?

Transcription on an ordinary laptop takes roughly as long as the recording
itself (Standard model). Watch the progress bar and the time estimate; the
browser tab title also shows progress. Keep the laptop plugged in with the
lid open.

## One file failed but the others worked

The file is probably damaged or in an unusual format. The page shows a
plain-language reason per file. Everything else still completes.

## My antivirus complained

The setup tool (`uv.exe`) is a well-known open-source program from
astral.sh. If your antivirus quarantined it, restore it or just delete
`.managed` and re-run — setup detects the damage and re-downloads.

## Where are the logs? (for emailing support)

`.managed/logs/bootstrap.log` (setup) and `.managed/logs/app.log` (the app).
The page footer shows the exact path.
