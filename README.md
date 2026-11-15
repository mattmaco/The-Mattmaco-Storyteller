# Storyteller

Storyteller reads your study PDFs aloud and highlights each sentence and word as you hear it. It runs entirely on your own computer: no account, no usage limits, and no internet once it is installed.

It knows the layout of the study packs it was built for. It skips citations, page footers and table-of-contents tables, reads tables row by row with their headers, and says formulas the way you would say them out loud. Other PDFs with a text layer work too, with a best-effort reading order.

## Install (Windows 10 or 11)

You need about 5 GB of free disk space and an internet connection for the install. An NVIDIA graphics card makes the voice faster but is not required.

1. Download this folder (on GitHub: **Code**, then **Download ZIP**) and unzip it somewhere permanent, such as `Documents\Storyteller`.
2. Double-click `install.bat`.
3. Wait until the window says **Done**. The first install downloads about 3 GB and takes 10 to 20 minutes.

The installer sets up Python and everything else on its own, downloads the voices, and adds a **Storyteller** shortcut to your desktop and Start menu.

Run `install.bat` again any time to update or repair Storyteller. It keeps your packs and settings.

## Use

1. Open **Storyteller** from the desktop or the Start menu. It opens in your browser.
2. Drag a PDF onto the page, or click the drop area to choose one.
3. Click **Start**, then click any sentence to start reading from there, or press **Play**.

Storyteller prepares the audio in the background, starting from where you are. If you scroll away while it reads, **Back to reading** takes you to the current sentence. Your place in each pack is saved.

Use the moon or sun button to switch between light and dark mode. Until you choose, Storyteller follows your Windows setting.

To stop Storyteller, close its window on the taskbar. Opening the shortcut again while it is running just opens the browser tab.

## Where your files are

- Packs, reading positions and settings: `%LOCALAPPDATA%\Storyteller`
- Voice files: `%USERPROFILE%\.cache\huggingface`

## Uninstall

Double-click `uninstall.bat`. It removes the shortcuts and the installed packages and keeps your packs and settings. Delete the folders above to remove those too.

## Troubleshooting

- **"Port 8765 is in use by another program"**: close that program, or set a different port. Open a command prompt in this folder and run `set STORYTELLER_PORT=8766` and then `run.bat`.
- **"This PDF has no text layer"**: the PDF is a scanned image. Storyteller can't read scanned PDFs yet.
- **The voice could not be set up**: check your internet connection and run `install.bat` again.
- **"GPU unavailable, using CPU"**: the voice still works, just more slowly. Updating your NVIDIA driver usually fixes it.

## For developers

Storyteller is a Python package (`storyteller/`) with a FastAPI server and a plain-JavaScript web UI (`storyteller/web/`). It uses [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
```

```bash
uv run pytest
```

```bash
STORYTELLER_VOICE=stub uv run python -m storyteller serve
```

- `STORYTELLER_VOICE=stub` replaces the Kokoro voice with silence and synthetic timings, so you don't need the voice download.
- `STORYTELLER_HOME` moves the data folder; `STORYTELLER_PORT` changes the port (default 8765).
- `python -m storyteller script <pdf>` prints the text that would be spoken for each sentence.
- `python -m storyteller setup` downloads the voice files and reports whether the voice runs on the graphics card or the processor.
- Real study packs are never committed. To run the tests that use one, put it at `tests/fixtures/local/biol2040.pdf` (git-ignored).

The design spec and implementation plan are in `docs/superpowers/`.

## Licences

- Voice: [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache-2.0)
- PDF rendering: [pdf.js](https://mozilla.github.io/pdf.js/) (Apache-2.0), in `storyteller/web/vendor/pdfjs/`
- Typeface: [Atkinson Hyperlegible Next](https://github.com/googlefonts/atkinson-hyperlegible-next) (SIL Open Font License), in `storyteller/web/vendor/fonts/`
