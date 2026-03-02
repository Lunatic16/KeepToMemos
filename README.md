# Google Keep → Memos Importer 🗂️

> Migrate your Google Keep notes to a self-hosted [Memos](https://github.com/usememos/memos) instance — preserving content, timestamps, attachments, and structure.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [How It Works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Exporting from Google Keep](#exporting-from-google-keep)
- [Running the Import](#running-the-import)
- [Understanding the Output](#understanding-the-output)
- [Deleting Existing Memos](#deleting-existing-memos)
- [Known Limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)
- [Dependencies](#dependencies)

---

## Overview

KeepSake is a Python migration script that reads Google Keep notes exported via Google Takeout and imports them into a Memos instance using the Memos REST API. It handles both plain text notes and checklist notes, preserves metadata like timestamps and pinned/archived state, and uploads any attached images as Memos resources.

This is useful if you are leaving Google Keep and want to self-host your notes without losing your history.

---

## Features

| Feature | Detail |
|---|---|
| ✅ Text notes | Converts HTML content to clean Markdown |
| ✅ Checklist notes | Renders as Markdown task lists (`- [ ]` / `- [x]`) |
| ✅ Timestamps | Preserves original creation, edit, and display times |
| ✅ Pinned notes | `isPinned` state carried over |
| ✅ Archived notes | `isArchived` maps to Memos `ARCHIVED` state |
| ✅ Attachments | Images uploaded as Memos resources and linked to the note |
| ✅ Trash filtering | Trashed notes are automatically skipped |
| ✅ Empty note filtering | Notes with no content and no attachments are skipped |
| ✅ Bulk delete utility | Helper to wipe all memos/resources before a re-import |

---

## How It Works

For each `.json` file found in the Takeout directory, KeepSake:

1. **Reads** the note JSON and checks if it should be skipped (trashed, empty)
2. **Converts** the content — HTML text notes are converted to Markdown; checklist notes are rendered as Markdown task lists with checked/unchecked state
3. **Posts** the note to the Memos API with full metadata (content, timestamps, visibility, pinned state, archived state)
4. **Uploads** any attachments (images, files) to the Memos resources API and links them to the created memo
5. **Patches** the memo a second time to ensure timestamps are correctly stored (the Memos API sometimes overwrites them on creation)

A short delay of 100ms is added between notes to avoid overloading the API.

---

## Requirements

- Python **3.8** or higher
- A running **Memos** instance (v0.18+) with API access enabled
- A **Google Takeout** export of your Keep data
- Network access from the machine running the script to your Memos instance

---

## Installation

**1. Clone or download the script**

```bash
git clone https://github.com/yourname/keepsake.git
cd keepsake
```

Or simply download `import.py` directly.

**2. (Recommended) Create a virtual environment**

```bash
python -m venv venv
source venv/bin/activate      # macOS/Linux
venv\Scripts\activate         # Windows
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

---

## Configuration

Open `import.py` and edit the three constants near the top of the file:

```python
BASE_URL = "http://your-memos-server/api/v1/"
ACCESS_TOKEN = "memos_pat_your_token_here"
KEEP_TAKEOUT_DIR = "./Takeout/Keep/"
```

### `BASE_URL`

The full URL to your Memos API root. Always include a trailing slash.

| Deployment type | Example value |
|---|---|
| Local (default port) | `http://localhost:5230/api/v1/` |
| Self-hosted with domain | `https://memos.yourdomain.com/api/v1/` |
| Docker on custom port | `http://192.168.1.10:8080/api/v1/` |

### `ACCESS_TOKEN`

A personal access token (PAT) from your Memos account.

To generate one:
1. Log in to your Memos instance
2. Click your avatar → **Settings**
3. Go to **My Account → Access Tokens**
4. Click **Generate New Token**, give it a name (e.g. `keepsake-import`), and copy the value
5. Paste it as the value of `ACCESS_TOKEN` in the script

> ⚠️ **Security note:** Never commit your access token to version control. Consider loading it from an environment variable or a `.env` file.

### `KEEP_TAKEOUT_DIR`

The path to the folder containing your Google Keep JSON files. This can be an absolute path or relative to where you run the script from.

```python
KEEP_TAKEOUT_DIR = "./Takeout/Keep/"           # relative
KEEP_TAKEOUT_DIR = "/Users/you/Downloads/Keep/" # absolute (macOS/Linux)
KEEP_TAKEOUT_DIR = "C:/Users/you/Downloads/Keep/" # absolute (Windows)
```

### Visibility Setting

By default all imported notes are set to `PRIVATE`. To change this, find the following line in the payload inside `import_keep_note()` and update the value:

```python
"visibility": "PRIVATE",  # Change to "PUBLIC" or "PROTECTED" if needed
```

---

## Exporting from Google Keep

You need to export your notes from Google before running KeepSake.

1. Go to [Google Takeout](https://takeout.google.com/)
2. Click **Deselect all** to avoid downloading unneeded data
3. Scroll down and check **Keep** only
4. Click **Next step**, choose your preferred export format (zip is fine), and click **Create export**
5. Google will email you a download link — this can take a few minutes to a few hours depending on how many notes you have
6. Download and extract the archive
7. Inside the extracted folder, find the `Takeout/Keep/` directory — this contains one `.json` file per note, plus any attached media files

Your directory will look something like this:

```
Takeout/
└── Keep/
    ├── My note.json
    ├── My note.jpg          ← attachment referenced by the JSON
    ├── Shopping list.json
    ├── Ideas.json
    └── ...
```

Set `KEEP_TAKEOUT_DIR` to point to this `Keep/` folder.

---

## Running the Import

Once configured, run the script:

```bash
python import.py
```

You will see output like:

```
Starting import from ./Takeout/Keep/
...........
Skipping trashed note: ./Takeout/Keep/deleted note.json
...........
Import completed!
```

Each `.` represents a successful API call (note creation, attachment upload, or timestamp patch). Errors are printed on their own line with details about the failed request.

---

## Understanding the Output

| Output | Meaning |
|---|---|
| `.` | Successful operation (note posted, attachment uploaded, or times patched) |
| `Skipping trashed note: ...` | Note has `isTrashed: true` — skipped intentionally |
| `Skipping empty note without attachments: ...` | Note has no content and no files — skipped |
| `Failed to import ...: 401` | Access token is invalid or missing |
| `Failed to import ...: 404` | `BASE_URL` is incorrect or Memos API path has changed |
| `Failed to upload image: ...` | Attachment file not found or API error |
| `Error importing ...: ...` | Unexpected Python exception — check the message for details |

---

## Deleting Existing Memos

If you need to do a clean re-import, you can delete all existing memos and resources first. Uncomment the relevant lines near the bottom of `import.py`:

```python
delete_all("memos", "ARCHIVED")   # deletes all archived memos
delete_all("memos", "NORMAL")     # deletes all active memos
delete_all("resources", "")       # deletes all uploaded attachments
```

Then run the script once to perform the deletion, re-comment those lines, and run it again to import.

> ⚠️ **Warning:** This permanently deletes data from your Memos instance. There is no undo. Make sure you have a backup before proceeding.

> ℹ️ **Note:** The delete function fetches up to 2000 items at a time. If you have more than 2000 memos or resources, you will need to run it multiple times.

---

## Known Limitations

- **Google Keep labels are not imported.** Keep uses colored labels; these are not currently mapped to Memos tags.
- **Note colors are not preserved.** Keep's background colors have no equivalent in Memos.
- **Nested checklist items are flattened.** Some Keep exports contain hierarchical checklist items; these are imported as flat lists.
- **`textContent` fallback is not implemented.** Older Keep exports may use a plain `textContent` field instead of `textContentHtml`. If your notes appear empty, check the JSON and add a fallback manually.
- **Attachment paths must be resolvable.** The script uses file paths as stored in the JSON. If you move the Keep folder or run the script from a different directory, attachment uploads may fail.
- **No resume support.** If the script is interrupted mid-run, there is no checkpoint. Notes already imported will be duplicated if you run it again. Use the delete utility to reset first.
- **Max 2000 items fetched per delete call.** The `delete_all` function does not paginate — see above.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'markdownify'`**
Run `pip install -r requirements.txt`. If using a virtual environment, make sure it is activated first.

**`Failed to import ...: 401 Unauthorized`**
Your `ACCESS_TOKEN` is wrong, expired, or missing. Re-generate it in Memos settings and update the script.

**`Failed to import ...: 404 Not Found`**
Check your `BASE_URL`. It must end with `/api/v1/` and point to a reachable Memos instance. Verify the URL works in your browser by visiting it directly.

**Notes import but timestamps are wrong**
This can happen if your Memos version handles the `createTime`/`updateTime` fields differently. The script sends a PATCH request after creation to correct this. If timestamps are still wrong, check your Memos version against the API docs.

**Attachments fail with a file not found error**
Make sure you are running the script from the same directory as your Keep export, or use an absolute path for `KEEP_TAKEOUT_DIR`. The JSON files reference attachment filenames as relative paths.

**Notes appear with no content**
Your export may use the plain `textContent` field instead of `textContentHtml`. Open one of the JSON files and check which field contains the note body. If it's `textContent`, update the line in `import_keep_note()`:
```python
content = md(note.get('textContentHtml', ''))
# change to:
content = note.get('textContent', '')
```

**The script is very slow**
The 100ms delay between notes is intentional to avoid rate limiting. For large imports (1000+ notes) this can take 10–20 minutes. Reducing the `sleep(0.1)` value will speed things up but may cause API errors on some servers.

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `requests` | ≥ 2.28.0 | HTTP calls to the Memos REST API |
| `markdownify` | ≥ 0.11.0 | Converts HTML note bodies to Markdown |

All other imports (`json`, `os`, `base64`, `datetime`, `time`) are part of the Python standard library and require no installation.
