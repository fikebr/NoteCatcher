# NoteCatcher

Capture text, links, and images from your clipboard and save them as Markdown notes on Windows.

Copy something, press **Ctrl+Alt+N**, make any edits, and press **Ctrl+Enter** to save. NoteCatcher stays in the system tray so it is ready for the next idea.

## Get started

NoteCatcher runs on **Windows 11**. AutoHotkey is not needed.

### Portable Windows app

If you have the portable ZIP, extract the entire archive and double-click
**NoteCatcher.exe** inside its folder. Keep the `_internal` folder beside the EXE;
it contains the files the app needs. No Python installation is required.

The app starts in the notification area near the clock. To choose where notes are
saved, use **File → Output Folder**, or copy `config.example.toml` to `config.toml`
beside the EXE and edit `notes_dir`. Exit and restart after editing settings.
Recovery and logs are kept in your Windows application-data folder.

### Run from the project files

This option requires **Python 3.13 or newer** and **uv**.

1. Install [Python](https://www.python.org/downloads/windows/) and [uv](https://docs.astral.sh/uv/getting-started/installation/).
2. Download this project from [GitHub](https://github.com/fikebr/NoteCatcher) using **Code → Download ZIP**, then extract it.
3. Open PowerShell in the extracted project folder and run:

   ```powershell
   uv sync
   uv run notecatcher
   ```

Look for the NoteCatcher icon in the Windows notification area, near the clock. It may be inside the hidden-icons menu. The editor starts hidden; right-click the icon and choose **Open** to show it.

To start with the editor visible, use:

```powershell
uv run notecatcher --show
```

Keep NoteCatcher running while you use its global capture shortcut. To quit, choose **File → Exit** or **Exit** from the tray menu.

## Capture and save a note

1. Copy text, formatted text, or an image in another application.
2. Press **Ctrl+Alt+N** to open NoteCatcher and import the clipboard.
3. Edit your note. You can also type from scratch or paste more content.
4. Press **Ctrl+Enter**, or choose **File → Save Markdown**.

After saving, the editor clears and hides. NoteCatcher attempts to return you to the application you were using.

Capture again before saving to append another item to the same draft. **Ctrl+V** pastes at the caret instead. An empty or unsupported clipboard leaves the current draft intact.

## Find your saved notes

By default, notes are saved in the **NoteCatcher** folder inside your home directory's **Documents** folder.

Each note is a `.md` file named with the date and time. Images are saved as PNG files in an `assets` subfolder and linked from the note. Existing notes are never overwritten.

You can open the saved files in QOwnNotes or another Markdown editor. QOwnNotes viewing has been validated. Keep the images with their notes when moving or sharing them so the links continue to work.

Choose **File → Reload Saved Note** to preview the most recently saved note. This preview does not replace your current draft.

### Choose a different notes folder

Use **File → Output Folder** to change the destination until you exit NoteCatcher. Existing notes are not moved.

For a permanent choice:

1. Copy `config.example.toml` to `config.toml` in the project folder.
2. Set the notes folder in that file, for example:

   ```toml
   [storage]
   notes_dir = "E:/Notes/NoteCatcher"
   ```

3. Exit NoteCatcher through its tray menu and start it again. For the portable app,
   keep `config.toml` beside `NoteCatcher.exe`; when running from source, keep it in
   the project folder and start the app from there.

Use forward slashes in folder paths, as shown above. You can point NoteCatcher at a folder in your QOwnNotes notebook.

## Editing and menus

**File** lets you save, preview the last saved note, choose the output folder, discard a draft, clear and hide the editor, or exit.

**Insert** lets you:

- **Import Clipboard:** append the clipboard to the current draft.
- **Link:** add a web or email link to selected text, or insert the URL itself.
- **Image:** choose a local image file to insert at the caret.
- **Timestamp:** insert the current local date and time.

**Help → About**, at the right side of the menu bar, shows the app name, version, and a link to this project.

### Keyboard shortcuts

| Shortcut | Action |
|---|---|
| **Ctrl+Alt+N** | Open NoteCatcher and append the clipboard, from any application |
| **Ctrl+Enter** | Save the current note while the editor is focused |
| **Esc** | Discard the current draft and hide the editor, without confirmation |
| **Ctrl+Shift+V** | Append the clipboard while the editor is focused |
| **Ctrl+V** | Paste at the caret |
| **Ctrl+B** / **Ctrl+I** | Toggle bold / italic |
| **Alt+F** / **Alt+I** / **Alt+H** | Open File / Insert / Help |

## Keep or discard an unfinished draft

To keep a draft, close the editor using its **X** button. This hides the window and keeps your work. Open it again from the tray to continue. Exiting the app also preserves the draft for the next launch.

**Esc permanently discards the draft without confirmation and hides the editor.** It also clears undo history and the recovery copy. It does not save a note.

For a confirmation before discarding, choose **File → Discard draft…** or **Discard draft…** from the tray menu. Previously saved notes and images are kept.

NoteCatcher automatically keeps a local recovery copy as you edit. After an unexpected shutdown, it restores that draft on the next launch. By default, the latest half-second of edits may not have reached recovery yet.

## Personalize NoteCatcher

Edit `config.toml` beside the EXE (or in the project folder when running from source),
then exit and restart NoteCatcher to apply changes. The example file lists all
available settings; omitted settings use their defaults.

Some useful options are:

```toml
[hotkeys]
capture = "Ctrl+Alt+N"
save = "Ctrl+Return"
cancel = "Esc"

[behavior]
after_save = "hide"
restore_focus = true
```

`Ctrl+Return` is the main Enter key. Set `after_save` to `"stay_open"` to keep the editor visible after saving. Set `restore_focus` to `false` to disable the attempt to return to the previous application after hiding.

The capture shortcut supports letters, digits, function keys other than F12, and common navigation keys. Include Ctrl, Alt, or Win; Shift may be added. Some combinations are already used by Windows or other applications. Save and cancel shortcuts apply only in the editor.

You can also change the image subfolder name and note filename pattern using the options in [config.example.toml](config.example.toml).

## Troubleshooting

**The capture shortcut does not work.** Check that NoteCatcher is running. If it reports a shortcut conflict, choose another `capture` shortcut in `config.toml` and restart. If you used the older AutoHotkey script, exit it. You can still capture through **Insert → Import Clipboard** or the tray menu.

**The app will not start after changing settings.** Check the setting named in the error message. Keep text values in quotes and use `true` or `false` for switches. Compare your file with `config.example.toml`.

**A note cannot be saved.** Your draft stays in the editor. Check that the destination drive is connected, the folder is writable, and there is enough disk space. A sync tool may temporarily lock files. Choose another output folder if needed.

**The note saved, but a recovery warning appeared.** The saved note exists. Keep the draft open until the storage problem is fixed, then use **Discard draft…** to clear it. Saving again creates another note.

**A recovery file is damaged.** NoteCatcher preserves a backup before starting a new draft. If it cannot make that backup, follow the message to protect the recovery file before continuing.

**A web image is missing or formatting looks different.** NoteCatcher preserves supported text formatting, but Markdown cannot represent every web layout. Images referenced by pasted web pages are not downloaded automatically. Copy the image itself or use **Insert → Image**.

**The previous application does not regain focus.** Windows can restrict focus changes. Your saved note is unaffected.

## Privacy and support

NoteCatcher reads the clipboard only when you request a capture or paste. It does not watch clipboard history or change clipboard contents. Notes and recovery data stay on your computer unless you choose a synced folder. Recovery files are not encrypted.

Diagnostic logs exclude note content and clipboard data. If you need them when reporting a problem, they are normally in `%LOCALAPPDATA%/NoteCatcher/NoteCatcher/logs`.

Report a problem or request a feature through [GitHub Issues](https://github.com/fikebr/NoteCatcher/issues). Include the app version from **Help → About** and what you were doing when the problem occurred.
