# Google Keep → Memos Importer

A Python script to migrate Google Keep notes (exported via Google Takeout) into a self-hosted [Memos](https://github.com/usememos/memos) instance.

---

## Features

- Imports regular text notes and checklist notes
- Converts HTML note content to Markdown
- Preserves creation, edit, and display timestamps
- Handles pinned, archived, and private visibility states
- Skips trashed and empty notes
- Uploads image/file attachments as Memos resources
- Includes a utility to bulk-delete memos and resources (useful for re-imports)

---

## Requirements

- Python 3.8+
- A running Memos instance with API access
- Google Takeout export of your Keep data (JSON format)

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Configuration

Edit the following constants at the top of `import.py`:

| Variable | Description |
|---|---|
| `BASE_URL` | Full URL to your Memos API, e.g. `http://localhost:5230/api/v1/` |
| `ACCESS_TOKEN` | Your Memos personal access token (PAT) |
| `KEEP_TAKEOUT_DIR` | Path to the directory containing your Google Takeout JSON files |

### Getting a Memos Access Token

1. Log in to your Memos instance
2. Go to **Settings → My Account → Access Tokens**
3. Generate a new token and paste it into `ACCESS_TOKEN`

---

## Usage

### 1. Export from Google Keep

1. Go to [Google Takeout](https://takeout.google.com/)
2. Select only **Keep**
3. Download and extract the archive
4. Locate the folder containing `.json` files (one per note)

### 2. Run the importer

```bash
python import.py
```

The script will process every `.json` file in `KEEP_TAKEOUT_DIR`, printing a `.` for each successful operation.

---

## Deleting Existing Memos (Optional)

If you need to re-run the import and want a clean slate, uncomment the relevant lines at the bottom of `import.py`:

```python
delete_all("memos", "ARCHIVED")
delete_all("memos", "NORMAL")
delete_all("resources", "")
```

> ⚠️ **Warning:** This will permanently delete all memos and/or resources from your Memos instance.

---

## Notes & Limitations

- Notes marked as **trashed** (`isTrashed: true`) are skipped automatically.
- Notes with no content and no attachments are skipped.
- All imported notes are set to **PRIVATE** visibility by default. Change `"visibility": "PRIVATE"` to `"PUBLIC"` in the payload if needed.
- Attachment file paths in the JSON must be accessible on disk relative to where the script is run.
- A 100ms delay (`sleep(0.1)`) is added between imports to avoid overwhelming the API.

---

## Dependencies

| Package | Purpose |
|---|---|
| `requests` | HTTP calls to the Memos API |
| `markdownify` | Converts HTML note content to Markdown |
