# Google Keep → Memos Importer 🗂️

> Migrate your Google Keep notes to a self-hosted [Memos](https://github.com/usememos/memos) instance — preserving content, timestamps, attachments, labels, and colors.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [How It Works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Exporting from Google Keep](#exporting-from-google-keep)
- [Understanding the Output](#understanding-the-output)
- [Testing](#testing)
- [Known Limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)
- [Dependencies](#dependencies)

---

## Overview

KeepToMemos is a Python migration tool that reads Google Keep notes exported via Google Takeout and imports them into a Memos instance using the Memos REST API. It handles both plain text notes and checklist notes, preserves metadata like timestamps and pinned/archived state, uploads attachments, and optionally converts labels to tags and adds color emojis.

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
| ✅ Attachments | Images uploaded as Memos resources (parallel upload) |
| ✅ Labels → Tags | Google Keep labels converted to Memos `#hashtags` |
| ✅ Color preservation | Optional emoji prefixes for note colors |
| ✅ Trash filtering | Trashed notes automatically skipped |
| ✅ Empty note filtering | Notes with no content/attachments skipped |
| ✅ Bulk delete utility | Helper to wipe all memos/resources before re-import |
| ✅ Resume support | Tracks progress, skips already-imported notes |
| ✅ Dry-run mode | Preview what would be imported without making changes |
| ✅ Retry logic | Exponential backoff for failed API calls |
| ✅ Parallel uploads | Multi-threaded attachment uploads |
| ✅ Configurable filters | Skip archived, pinned, or notes without attachments |
| ✅ CLI interface | Full command-line argument support |
| ✅ Logging | Configurable logging with optional file output |
| ✅ Summary report | Detailed statistics at end of import |

---

## How It Works

For each `.json` file found in the Takeout directory, KeepToMemos:

1. **Reads** the note JSON and checks if it should be skipped (trashed, empty, filtered)
2. **Checks** import state to avoid re-processing (resume support)
3. **Converts** the content — HTML text notes → Markdown; checklist notes → Markdown task lists
4. **Adds** color emoji prefix (if enabled) and label hashtags (if enabled)
5. **Posts** the note to the Memos API with full metadata
6. **Uploads** attachments in parallel to the Memos resources API
7. **Patches** the memo to ensure timestamps are correctly stored
8. **Saves** progress state for resume capability
9. **Displays** summary report with statistics

A configurable delay between notes prevents API rate limiting.

---

## Requirements

- Python **3.8** or higher
- A running **Memos** instance (v0.18+) with API access enabled
- A **Google Takeout** export of your Keep data
- Network access from the machine running the script to your Memos instance

---

## Installation

**1. Clone or download the repository**

```bash
git clone https://github.com/yourname/KeepToMemos.git
cd KeepToMemos
```

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

**4. Configure environment**

```bash
cp .env.example .env
# Edit .env with your settings
```

---

## Configuration

KeepToMemos supports three configuration methods (precedence: CLI > Env > Config file):

### Method 1: Environment Variables (Recommended)

Copy `.env.example` to `.env` and edit:

```bash
# .env
MEMOS_BASE_URL=http://localhost:5230/api/v1/
MEMOS_ACCESS_TOKEN=memos_pat_your_token_here
KEEP_TAKEOUT_DIR=./Takeout/Keep/
```

### Method 2: Configuration File

Create a `config.json` file:

```json
{
  "visibility": "PRIVATE",
  "import_delay": 0.1,
  "retry_attempts": 3,
  "workers": 4,
  "skip_archived": false,
  "skip_pinned": false,
  "skip_trashed": true,
  "import_labels": true,
  "import_colors": true,
  "resume": true,
  "label_mapping": {
    "Personal": "personal",
    "Work": "work",
    "Ideas": "ideas"
  }
}
```

Use with: `python import.py --config config.json`

### Method 3: Command-Line Arguments

See [Usage](#usage) for full CLI options.

### Configuration Options

| Option | Env Var | CLI Flag | Default | Description |
|---|---|---|---|---|
| `MEMOS_BASE_URL` | `--base-url` | API base URL | `http://localhost:5230/api/v1/` |
| `MEMOS_ACCESS_TOKEN` | `--access-token` | Personal access token | *(required)* |
| `KEEP_TAKEOUT_DIR` | `--takeout-dir` | Takeout directory | `./` |
| `visibility` | `--visibility` | Note visibility | `PRIVATE` |
| `import_delay` | `--delay` | Delay between notes (sec) | `0.1` |
| `workers` | `--workers` | Parallel upload workers | `4` |
| `retry_attempts` | - | API retry attempts | `3` |
| `skip_archived` | `--skip-archived` | Skip archived notes | `false` |
| `skip_pinned` | `--skip-pinned` | Skip pinned notes | `false` |
| `skip_trashed` | `--skip-trashed` | Skip trashed notes | `true` |
| `only_with_attachments` | `--only-with-attachments` | Only notes with files | `false` |
| `import_labels` | `--no-labels` | Convert labels to tags | `true` |
| `import_colors` | `--no-colors` | Add color emojis | `true` |
| `dry_run` | `--dry-run` | Preview without changes | `false` |
| `resume` | `--resume` | Resume previous import | `true` |

### Color Mapping

Google Keep colors are optionally converted to emoji prefixes:

| Color | Emoji |
|---|---|
| RED | 🔴 |
| ORANGE | 🟠 |
| YELLOW | 🟡 |
| GREEN | 🟢 |
| TEAL | 🔵 |
| BLUE | 🔷 |
| DARK_BLUE/PURPLE | 🟣 |
| PINK | 🩷 |
| BROWN | 🟤 |
| GRAY | ⚪ |

---

## Usage

### Basic Import

```bash
# Using .env file
python import.py

# Using CLI arguments
python import.py --takeout-dir ./Takeout/Keep --access-token memos_pat_xxx
```

### Dry Run (Preview)

```bash
python import.py --dry-run --verbose
```

### Filtered Import

```bash
# Skip archived and pinned notes
python import.py --skip-archived --skip-pinned

# Only import notes with attachments
python import.py --only-with-attachments

# Import trashed notes (default is to skip)
python import.py --no-skip-trashed
```

### Feature Toggles

```bash
# Disable label import
python import.py --no-labels

# Disable color emojis
python import.py --no-colors

# Disable resume (fresh import)
python import.py --resume false
```

### Delete Mode

```bash
# Delete all memos
python import.py --delete-memos

# Delete all resources (attachments)
python import.py --delete-resources
```

### Logging

```bash
# Verbose output
python import.py --verbose

# Log to file
python import.py --log-file import.log
```

### Full Example

```bash
python import.py \
  --takeout-dir ./Takeout/Keep \
  --config config.json \
  --skip-archived \
  --no-colors \
  --workers 8 \
  --verbose \
  --log-file import.log
```

---

## Exporting from Google Keep

1. Go to [Google Takeout](https://takeout.google.com/)
2. Click **Deselect all**, then check only **Keep**
3. Click **Next step**, choose export settings (zip recommended), click **Create export**
4. Wait for Google's email with download link
5. Download and extract the archive
6. Locate the `Takeout/Keep/` directory

Your directory structure:

```
Takeout/
└── Keep/
    ├── My note.json
    ├── My note.jpg          ← attachment
    ├── Shopping list.json
    └── ...
```

---

## Understanding the Output

### Log Messages

| Message | Meaning |
|---|---|
| `✓ Created: ...` | Note successfully imported |
| `✓ Uploaded: ...` | Attachment successfully uploaded |
| `Skipping trashed note: ...` | Note is in trash (skipped) |
| `Skipping archived note: ...` | Note is archived (if `--skip-archived`) |
| `Skipping empty note: ...` | No content and no attachments |
| `Failed to create memo: 401` | Invalid access token |
| `Failed to create memo: 404` | Incorrect BASE_URL |
| `Attachment not found: ...` | Referenced file doesn't exist |

### Summary Report

```
============================================================
📊 IMPORT SUMMARY
============================================================
⏱️  Duration:        45.3 seconds
✅ Imported:        450
⚠️  Skipped (trashed):  12
⚠️  Skipped (empty):    5
⚠️  Skipped (archived): 0
⚠️  Skipped (pinned):   3
⚠️  Skipped (no attachments): 0
❌ Failed:          2
📎 Attachments:     87
============================================================
```

---

## Testing

### Run Unit Tests

```bash
# Using pytest
pytest test_import.py -v

# Using unittest
python test_import.py
```

### Test with Sample Data

```bash
# Dry run with test data
python import.py --takeout-dir ./test_data --dry-run --verbose
```

### Sample Test Files

The `test_data/` directory includes sample notes:

| File | Description |
|---|---|
| `01_text_note.json` | Simple text note with HTML |
| `02_checklist.json` | Checklist with mixed states |
| `03_archived.json` | Archived note |
| `04_trashed.json` | Trashed note (skipped) |
| `05_ideas.json` | Note with color and labels |

---

## Known Limitations

- **Google Keep labels → Memos tags**: Labels are converted to `#hashtags` (no spaces)
- **Note colors**: Converted to emoji prefixes, not actual colors
- **Nested checklist items**: Flattened to single-level list
- **Attachment paths**: Must be resolvable from takeout directory
- **No checkpoint resume mid-note**: If interrupted, current note may be duplicated
- **Max 2000 items per delete call**: No pagination in delete function

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'dotenv'`

```bash
pip install python-dotenv
```

### `Configuration error: ACCESS_TOKEN is required`

Set your token via:
- `.env` file: `MEMOS_ACCESS_TOKEN=memos_pat_xxx`
- CLI: `--access-token memos_pat_xxx`
- Environment: `export MEMOS_ACCESS_TOKEN=memos_pat_xxx`

### `Failed to import: 401 Unauthorized`

Your access token is invalid or expired. Generate a new one in Memos settings.

### `Failed to import: 404 Not Found`

Check your `BASE_URL`. It must:
- Point to a reachable Memos instance
- End with `/api/v1/`
- Include the correct port

### `Attachment not found`

Ensure you're running from the correct directory or use absolute paths:

```bash
python import.py --takeout-dir /absolute/path/to/Takeout/Keep
```

### Notes appear with wrong timestamps

The script sends a PATCH request after creation. If timestamps are still wrong, check your Memos version compatibility.

### Import was interrupted, how do I resume?

By default, resume is enabled. Just run again — already-processed notes are skipped.

To force a fresh import:

```bash
python import.py --resume false
```

Or delete the state file:

```bash
rm .keepsake_state.json
```

### Slow import speed

Increase parallel workers:

```bash
python import.py --workers 8
```

Or reduce delay (may cause rate limiting):

```bash
python import.py --delay 0.05
```

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `requests` | ≥ 2.28.0 | HTTP client for Memos API |
| `markdownify` | ≥ 0.11.0 | HTML to Markdown conversion |
| `python-dotenv` | ≥ 1.0.0 | Environment variable loading |

Standard library modules used: `json`, `os`, `base64`, `datetime`, `time`, `hashlib`, `logging`, `argparse`, `concurrent.futures`, `pathlib`, `tempfile`, `unittest`.

---

## License

MIT License — feel free to modify and distribute.
