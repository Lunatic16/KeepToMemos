#!/usr/bin/env python3
"""
KeepToMemos - Google Keep to Memos Migration Tool

Migrates Google Keep notes (from Google Takeout) to a self-hosted Memos instance.
Preserves content, timestamps, attachments, labels, and colors.
"""

import argparse
import base64
import hashlib
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from time import sleep, time
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from dotenv import load_dotenv
from markdownify import MarkdownConverter

# Load environment variables from .env file
load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# Configuration Constants
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_PAGE_SIZE = 2000
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_DELAY = 1.0  # seconds
DEFAULT_IMPORT_DELAY = 0.1  # seconds between notes
DEFAULT_WORKERS = 4  # parallel workers for attachments

# Google Keep color mapping (color ID → emoji tag prefix)
KEEP_COLOR_MAP = {
    "DEFAULT": "",
    "RED": "🔴",
    "ORANGE": "🟠",
    "YELLOW": "🟡",
    "GREEN": "🟢",
    "TEAL": "🔵",
    "BLUE": "🔷",
    "DARK_BLUE": "🟣",
    "PURPLE": "🟣",
    "PINK": "🩷",
    "BROWN": "🟤",
    "GRAY": "⚪",
}


# ─────────────────────────────────────────────────────────────────────────────
# Logging Setup
# ─────────────────────────────────────────────────────────────────────────────

def setup_logging(verbose: bool = False, log_file: Optional[str] = None) -> logging.Logger:
    """Configure logging with console and optional file output."""
    logger = logging.getLogger("keepsake")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_format = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S")
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(console_format)
        logger.addHandler(file_handler)
    
    return logger


# ─────────────────────────────────────────────────────────────────────────────
# Configuration Management
# ─────────────────────────────────────────────────────────────────────────────

class Config:
    """Configuration management for KeepToMemos."""
    
    def __init__(self, args: argparse.Namespace):
        # CLI args take precedence, then env vars, then defaults
        self.base_url = args.base_url or os.getenv("MEMOS_BASE_URL", "http://localhost:5230/api/v1/")
        self.access_token = args.access_token or os.getenv("MEMOS_ACCESS_TOKEN", "")
        self.takeout_dir = args.takeout_dir or os.getenv("KEEP_TAKEOUT_DIR", "./")
        
        # Load from config file if provided
        self.config_file = args.config
        self.config_data = self._load_config_file()
        
        # Settings with defaults
        self.visibility = args.visibility or self._get("visibility", "PRIVATE")
        self.import_delay = float(args.delay) if args.delay else float(self._get("import_delay", DEFAULT_IMPORT_DELAY))
        self.retry_attempts = int(self._get("retry_attempts", DEFAULT_RETRY_ATTEMPTS))
        self.retry_delay = float(self._get("retry_delay", DEFAULT_RETRY_DELAY))
        self.page_size = int(self._get("page_size", DEFAULT_PAGE_SIZE))
        self.workers = int(args.workers) if args.workers else int(self._get("workers", DEFAULT_WORKERS))
        
        # Filters
        self.skip_archived = args.skip_archived or self._get("skip_archived", False)
        self.skip_pinned = args.skip_pinned or self._get("skip_pinned", False)
        self.skip_trashed = args.skip_trashed or self._get("skip_trashed", True)
        self.only_with_attachments = args.only_with_attachments or self._get("only_with_attachments", False)
        
        # Features
        self.import_labels = args.import_labels or self._get("import_labels", True)
        self.import_colors = args.import_colors or self._get("import_colors", True)
        self.dry_run = args.dry_run or self._get("dry_run", False)
        self.resume = args.resume or self._get("resume", True)
        
        # Label mapping (Keep label → Memos tag)
        self.label_mapping = self._get("label_mapping", {})
        
        # Validate required settings
        if not self.access_token:
            raise ValueError("ACCESS_TOKEN is required. Set via --access-token, MEMOS_ACCESS_TOKEN env var, or config file.")
        
        if not self.base_url.endswith("/"):
            self.base_url += "/"
    
    def _load_config_file(self) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        if not self.config_file:
            return {}
        
        config_path = Path(self.config_file)
        if not config_path.exists():
            logging.warning(f"Config file not found: {config_path}")
            return {}
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON in config file: {e}")
            return {}
    
    def _get(self, key: str, default: Any = None) -> Any:
        """Get config value from file or return default."""
        return self.config_data.get(key, default)
    
    def map_label(self, label: str) -> str:
        """Map a Google Keep label to a Memos tag."""
        return self.label_mapping.get(label, label)


# ─────────────────────────────────────────────────────────────────────────────
# Retry Logic with Exponential Backoff
# ─────────────────────────────────────────────────────────────────────────────

def retry_with_backoff(func, max_attempts: int = DEFAULT_RETRY_ATTEMPTS, 
                       base_delay: float = DEFAULT_RETRY_DELAY, 
                       exceptions: tuple = (requests.RequestException,)):
    """Decorator for retrying functions with exponential backoff."""
    def wrapper(*args, **kwargs):
        last_exception = None
        for attempt in range(1, max_attempts + 1):
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                last_exception = e
                if attempt < max_attempts:
                    delay = base_delay * (2 ** (attempt - 1))  # Exponential backoff
                    logging.debug(f"Attempt {attempt} failed: {e}. Retrying in {delay:.1f}s...")
                    sleep(delay)
                else:
                    logging.debug(f"All {max_attempts} attempts failed.")
        raise last_exception
    return wrapper


# ─────────────────────────────────────────────────────────────────────────────
# Import State Tracking (Resume Support)
# ─────────────────────────────────────────────────────────────────────────────

class ImportState:
    """Tracks import progress for resume capability."""
    
    def __init__(self, state_file: str = ".keepsake_state.json"):
        self.state_file = Path(state_file)
        self.processed: Set[str] = set()
        self.failed: Set[str] = set()
        self.stats = {
            "imported": 0,
            "skipped_trashed": 0,
            "skipped_empty": 0,
            "skipped_archived": 0,
            "skipped_pinned": 0,
            "skipped_no_attachments": 0,
            "failed": 0,
            "attachments_uploaded": 0,
        }
        self._load()
    
    def _load(self):
        """Load state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.processed = set(data.get("processed", []))
                    self.failed = set(data.get("failed", []))
                    self.stats = data.get("stats", self.stats)
                logging.debug(f"Loaded import state: {len(self.processed)} processed, {len(self.failed)} failed")
            except (json.JSONDecodeError, IOError) as e:
                logging.warning(f"Could not load state file: {e}")
    
    def save(self):
        """Save state to file."""
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump({
                    "processed": list(self.processed),
                    "failed": list(self.failed),
                    "stats": self.stats,
                }, f, indent=2)
            logging.debug("Import state saved.")
        except IOError as e:
            logging.error(f"Could not save state file: {e}")
    
    def is_processed(self, file_hash: str) -> bool:
        """Check if a file has been processed."""
        return file_hash in self.processed
    
    def mark_processed(self, file_hash: str):
        """Mark a file as successfully processed."""
        self.processed.add(file_hash)
        self.stats["imported"] += 1
    
    def mark_failed(self, file_hash: str):
        """Mark a file as failed."""
        self.failed.add(file_hash)
        self.stats["failed"] += 1
    
    def increment(self, key: str):
        """Increment a stat counter."""
        if key in self.stats:
            self.stats[key] += 1
    
    def clear(self):
        """Clear all state."""
        self.processed.clear()
        self.failed.clear()
        self.stats = {k: 0 for k in self.stats}
        if self.state_file.exists():
            self.state_file.unlink()


# ─────────────────────────────────────────────────────────────────────────────
# Summary Report
# ─────────────────────────────────────────────────────────────────────────────

class SummaryReport:
    """Generates and displays import summary."""
    
    def __init__(self, state: ImportState, start_time: float):
        self.state = state
        self.start_time = start_time
    
    def display(self):
        """Print summary report to console."""
        elapsed = time() - self.start_time
        
        print("\n" + "=" * 60)
        print("📊 IMPORT SUMMARY")
        print("=" * 60)
        print(f"⏱️  Duration:        {elapsed:.1f} seconds")
        print(f"✅ Imported:        {self.state.stats['imported']}")
        print(f"⚠️  Skipped (trashed):  {self.state.stats['skipped_trashed']}")
        print(f"⚠️  Skipped (empty):    {self.state.stats['skipped_empty']}")
        print(f"⚠️  Skipped (archived): {self.state.stats['skipped_archived']}")
        print(f"⚠️  Skipped (pinned):   {self.state.stats['skipped_pinned']}")
        print(f"⚠️  Skipped (no attachments): {self.state.stats['skipped_no_attachments']}")
        print(f"❌ Failed:          {self.state.stats['failed']}")
        print(f"📎 Attachments:     {self.state.stats['attachments_uploaded']}")
        print("=" * 60)
        
        if self.state.failed:
            print(f"\n⚠️  {len(self.state.failed)} file(s) failed. Check logs for details.")
            if len(self.state.failed) <= 10:
                print("Failed files:")
                for f in sorted(self.state.failed):
                    print(f"  - {f}")


# ─────────────────────────────────────────────────────────────────────────────
# Markdown Conversion
# ─────────────────────────────────────────────────────────────────────────────

class IPC(MarkdownConverter):
    """Custom markdown converter for paragraph handling."""
    
    def convert_p(self, el, text, parent_tags):
        return text + "\n"


def md(html: str, **options) -> str:
    """Convert HTML to markdown."""
    if not html:
        return ""
    return IPC(**options).convert(html)


def convert_timestamp(usec_timestamp: int) -> str:
    """Convert Google Keep's microseconds timestamp to ISO format."""
    if not usec_timestamp:
        return datetime.now().astimezone().isoformat()
    seconds = usec_timestamp / 1_000_000
    return datetime.fromtimestamp(seconds).isoformat()


def create_text_node(content: str) -> Dict[str, Any]:
    """Create a simple text node for memo content."""
    return {
        "type": "TEXT",
        "textNode": {"content": content}
    }


def convert_checklist_to_markdown(list_content: List[Dict]) -> str:
    """Convert Google Keep checklist items to markdown task list."""
    markdown_lines = []
    for item in list_content:
        text = item.get("text", "").strip()
        if not text:
            continue
        is_checked = item.get("isChecked", False)
        checkbox = "- [x] " if is_checked else "- [ ] "
        markdown_lines.append(checkbox + text)
    return "\n".join(markdown_lines)


# ─────────────────────────────────────────────────────────────────────────────
# KeepToMemos Importer Class
# ─────────────────────────────────────────────────────────────────────────────

class KeepToMemosImporter:
    """Main importer class for Google Keep to Memos migration."""
    
    def __init__(self, config: Config, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {config.access_token}",
            "Content-Type": "application/json",
        })
        self.state = ImportState() if config.resume else ImportState()
        self.start_time = time()
        
        # Clear state if not resuming
        if not config.resume:
            self.state.clear()
    
    def _file_hash(self, file_path: str) -> str:
        """Generate hash for a file based on its path and content."""
        hasher = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                hasher.update(f.read())
            return hasher.hexdigest()
        except IOError:
            return hashlib.md5(file_path.encode()).hexdigest()
    
    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make HTTP request with retry logic."""
        def _make_request():
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        
        wrapped_request = retry_with_backoff(
            _make_request,
            max_attempts=self.config.retry_attempts,
            base_delay=self.config.retry_delay,
            exceptions=(requests.RequestException, requests.ConnectionError)
        )
        return wrapped_request()
    
    def delete_all(self, resource_type: str, state: str = "") -> int:
        """Delete all resources of a given type."""
        deleted_count = 0
        
        try:
            response = self._request(
                "GET",
                f"{self.config.base_url}{resource_type}",
                params={"pageSize": self.config.page_size, "state": state}
            )

            if response.status_code == 200:
                items = response.json().get(resource_type, [])
                self.logger.info(f"\nDeleting {len(items)} {resource_type}...")

                for item in items:
                    item_name = item.get("name", "")
                    delete_url = f"{self.config.base_url}{item_name}"

                    if self.config.dry_run:
                        self.logger.info(f"[DRY RUN] Would delete: {item_name}")
                        deleted_count += 1
                        continue

                    delete_response = self.session.delete(delete_url)
                    if delete_response.status_code == 200:
                        print(".", end="", flush=True)
                        deleted_count += 1
                    else:
                        self.logger.error(f"\nFailed to delete {resource_type}: {item_name} - {delete_response.status_code}")
            else:
                self.logger.error(f"Failed to fetch {resource_type}: {response.status_code}")

        except requests.RequestException as e:
            self.logger.error(f"Error deleting {resource_type}: {e}")

        return deleted_count
    
    def convert_timestamp(self, usec_timestamp: int) -> str:
        """Convert Google Keep's microseconds timestamp to ISO format."""
        if not usec_timestamp:
            return datetime.utcnow().isoformat() + "Z"
        seconds = usec_timestamp / 1_000_000
        return datetime.fromtimestamp(seconds).isoformat() + "Z"
    
    def create_text_node(self, content: str) -> Dict[str, Any]:
        """Create a simple text node for memo content."""
        return {
            "type": "TEXT",
            "textNode": {"content": content}
        }
    
    def convert_checklist_to_markdown(self, list_content: List[Dict]) -> str:
        """Convert Google Keep checklist items to markdown task list."""
        markdown_lines = []
        for item in list_content:
            text = item.get("text", "").strip()
            if not text:
                continue
            is_checked = item.get("isChecked", False)
            checkbox = "- [x] " if is_checked else "- [ ] "
            markdown_lines.append(checkbox + text)
        return "\n".join(markdown_lines)
    
    def build_content(self, note: Dict) -> Tuple[str, bool]:
        """
        Build memo content from note.
        Returns (content, has_content) tuple.
        """
        title = note.get("title", "")
        
        # Handle checklist notes
        if note.get("listContent"):
            checklist_md = self.convert_checklist_to_markdown(note["listContent"])
            full_content = f"### {title}\n{checklist_md}" if title else checklist_md
        else:
            # Regular note - convert HTML to markdown
            content_html = note.get("textContentHtml", "")
            content = md(content_html) if content_html else note.get("textContent", "")
            full_content = f"### {title}\n{content}" if title else content
        
        # Add color emoji as tag prefix if enabled
        if self.config.import_colors:
            color = note.get("color", "DEFAULT")
            color_emoji = KEEP_COLOR_MAP.get(color, "")
            if color_emoji:
                full_content = f"{color_emoji} {full_content}"
        
        # Add labels as tags if enabled
        if self.config.import_labels and note.get("labelList"):
            tags = []
            for label in note.get("labelList", []):
                mapped_label = self.config.map_label(label)
                tags.append(f"#{mapped_label.replace(' ', '')}")
            if tags:
                full_content = f"{full_content}\n\n{' '.join(tags)}"
        
        has_content = bool(full_content.strip())
        return full_content, has_content
    
    def validate_attachment(self, file_path: str) -> Optional[str]:
        """Validate and resolve attachment path. Returns resolved path or None."""
        if not file_path:
            return None
        
        # Try absolute path first
        if os.path.isabs(file_path) and os.path.exists(file_path):
            return file_path
        
        # Try relative to takeout directory
        takeout_path = os.path.join(self.config.takeout_dir, file_path)
        if os.path.exists(takeout_path):
            return takeout_path
        
        # Try just the filename in takeout directory
        filename = os.path.basename(file_path)
        filename_path = os.path.join(self.config.takeout_dir, filename)
        if os.path.exists(filename_path):
            return filename_path
        
        self.logger.warning(f"Attachment not found: {file_path}")
        return None
    
    def upload_attachment(self, file_path: str, memo_name: str, mime_type: str) -> bool:
        """Upload an attachment as a Memos resource."""
        try:
            with open(file_path, "rb") as f:
                file_data = f.read()

            base64_data = base64.b64encode(file_data).decode("utf-8")
            filename = os.path.basename(file_path)

            payload = {
                "filename": filename,
                "type": mime_type,
                "content": base64_data,
                "memo": memo_name,
            }

            if self.config.dry_run:
                self.logger.info(f"[DRY RUN] Would upload: {filename}")
                return True

            # Use correct Memos v1 API endpoint for attachments
            post_url = f"{self.config.base_url}attachments"
            response = self.session.post(post_url, json=payload)

            if response.status_code == 200:
                self.logger.debug(f"✓ Uploaded: {filename}")
                return True
            else:
                self.logger.error(f"Failed to upload {filename}: {response.status_code} - {response.text}")
                return False

        except IOError as e:
            self.logger.error(f"Error reading file {file_path}: {e}")
            return False
        except requests.RequestException as e:
            self.logger.error(f"Error uploading {file_path}: {e}")
            return False

    def upload_attachments(self, attachments: List[Dict], memo_name: str) -> int:
        """Upload attachments in parallel."""
        if not attachments:
            return 0
        
        uploaded = 0
        
        if self.config.workers > 1:
            # Parallel upload
            with ThreadPoolExecutor(max_workers=self.config.workers) as executor:
                futures = {}
                for attachment in attachments:
                    file_path = self.validate_attachment(attachment.get("filePath", ""))
                    if file_path:
                        mime_type = attachment.get("mimetype", "application/octet-stream")
                        future = executor.submit(self.upload_attachment, file_path, memo_name, mime_type)
                        futures[future] = file_path
                
                for future in as_completed(futures):
                    if future.result():
                        uploaded += 1
        else:
            # Sequential upload
            for attachment in attachments:
                file_path = self.validate_attachment(attachment.get("filePath", ""))
                if file_path:
                    mime_type = attachment.get("mimetype", "application/octet-stream")
                    if self.upload_attachment(file_path, memo_name, mime_type):
                        uploaded += 1
        
        return uploaded
    
    def import_keep_note(self, json_file_path: str) -> bool:
        """Import a single Google Keep note into Memos."""
        file_hash = self._file_hash(json_file_path)
        
        # Check if already processed (resume support)
        if self.config.resume and self.state.is_processed(file_hash):
            self.logger.debug(f"Skipping already processed: {json_file_path}")
            return True
        
        try:
            with open(json_file_path, "r", encoding="utf-8") as f:
                note = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            self.logger.error(f"Error reading {json_file_path}: {e}")
            self.state.mark_failed(file_hash)
            return False
        
        # Skip trashed notes
        if self.config.skip_trashed and note.get("isTrashed", False):
            self.logger.debug(f"Skipping trashed note: {json_file_path}")
            self.state.increment("skipped_trashed")
            return True
        
        # Skip archived notes if configured
        if self.config.skip_archived and note.get("isArchived", False):
            self.logger.debug(f"Skipping archived note: {json_file_path}")
            self.state.increment("skipped_archived")
            return True
        
        # Skip pinned notes if configured
        if self.config.skip_pinned and note.get("isPinned", False):
            self.logger.debug(f"Skipping pinned note: {json_file_path}")
            self.state.increment("skipped_pinned")
            return True
        
        # Build content
        full_content, has_content = self.build_content(note)
        attachments = note.get("attachments", [])
        
        # Check if empty (no content and no attachments)
        if not has_content and not attachments:
            self.logger.debug(f"Skipping empty note: {json_file_path}")
            self.state.increment("skipped_empty")
            return True
        
        # Skip if no attachments and filter is enabled
        if self.config.only_with_attachments and not attachments:
            self.logger.debug(f"Skipping note without attachments: {json_file_path}")
            self.state.increment("skipped_no_attachments")
            return True
        
        # Get timestamps
        created_time = note.get("createdTimestampUsec", note.get("userEditedTimestampUsec", 0))
        edited_time = note.get("userEditedTimestampUsec", created_time)
        
        # Prepare payload
        payload = {
            "content": full_content,
            "nodes": [self.create_text_node(full_content)],
            "createTime": self.convert_timestamp(created_time),
            "updateTime": self.convert_timestamp(edited_time),
            "displayTime": self.convert_timestamp(edited_time),
            "visibility": self.config.visibility,
            "state": "ARCHIVED" if note.get("isArchived", False) else "NORMAL",
            "pinned": note.get("isPinned", False),
        }
        
        if self.config.dry_run:
            self.logger.info(f"[DRY RUN] Would import: {json_file_path}")
            self.state.mark_processed(file_hash)
            return True
        
        try:
            # Create memo
            url = f"{self.config.base_url}memos"
            response = self._request("POST", url, json=payload)
            
            if response.status_code != 200:
                self.logger.error(f"Failed to create memo {json_file_path}: {response.status_code} - {response.text}")
                self.state.mark_failed(file_hash)
                return False
            
            memo_data = response.json()
            memo_name = memo_data.get("name", "")
            self.logger.debug(f"✓ Created: {os.path.basename(json_file_path)}")
            
            # Upload attachments
            if attachments:
                uploaded = self.upload_attachments(attachments, memo_name)
                self.state.stats["attachments_uploaded"] += uploaded
            
            # Patch to ensure timestamps are correct
            patch_payload = {
                "createTime": self.convert_timestamp(created_time),
                "updateTime": self.convert_timestamp(edited_time),
                "displayTime": self.convert_timestamp(edited_time),
                "state": "ARCHIVED" if note.get("isArchived", False) else "NORMAL",
            }
            patch_url = f"{self.config.base_url}{memo_name}"
            patch_response = self.session.patch(patch_url, json=patch_payload)
            
            if patch_response.status_code != 200:
                self.logger.warning(f"Failed to patch timestamps for {json_file_path}")
            
            self.state.mark_processed(file_hash)
            return True
            
        except requests.RequestException as e:
            self.logger.error(f"Error importing {json_file_path}: {e}")
            self.state.mark_failed(file_hash)
            return False
    
    def process_directory(self, directory_path: str):
        """Process all JSON files in a directory."""
        json_files = [f for f in os.listdir(directory_path) if f.endswith(".json")]
        total = len(json_files)
        
        self.logger.info(f"Found {total} note files to process.")
        
        if self.config.dry_run:
            self.logger.warning("DRY RUN MODE - No changes will be made")
        
        # Process with progress
        for i, filename in enumerate(json_files, 1):
            file_path = os.path.join(directory_path, filename)
            self.logger.debug(f"[{i}/{total}] Processing: {filename}")
            
            self.import_keep_note(file_path)
            
            # Delay between notes (skip in dry run)
            if not self.config.dry_run and self.config.import_delay > 0:
                sleep(self.config.import_delay)
            
            # Save state periodically
            if i % 10 == 0:
                self.state.save()
        
        # Final state save
        self.state.save()
    
    def run(self):
        """Run the import process."""
        self.logger.info(f"Starting import from {self.config.takeout_dir}")
        self.logger.info(f"Dry run: {self.config.dry_run}, Resume: {self.config.resume}")
        
        if not os.path.isdir(self.config.takeout_dir):
            self.logger.error(f"Takeout directory not found: {self.config.takeout_dir}")
            return
        
        self.process_directory(self.config.takeout_dir)
        
        # Display summary
        report = SummaryReport(self.state, self.start_time)
        report.display()


# ─────────────────────────────────────────────────────────────────────────────
# CLI Argument Parser
# ─────────────────────────────────────────────────────────────────────────────

def create_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="keepsake",
        description="Migrate Google Keep notes to Memos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python import.py --takeout-dir ./Takeout/Keep
  python import.py --dry-run --verbose
  python import.py --skip-archived --skip-pinned
  python import.py --config config.json --workers 8
  python import.py --resume false  # Fresh import
        """
    )
    
    # Connection settings
    parser.add_argument("--base-url", help="Memos API base URL")
    parser.add_argument("--access-token", help="Memos access token (PAT)")
    parser.add_argument("--takeout-dir", help="Google Keep Takeout directory")
    parser.add_argument("--config", help="Path to JSON config file")
    
    # Import settings
    parser.add_argument("--visibility", choices=["PRIVATE", "PUBLIC", "PROTECTED"], 
                        help="Default visibility for imported notes")
    parser.add_argument("--delay", type=float, help="Delay between imports (seconds)")
    parser.add_argument("--workers", type=int, help="Parallel workers for attachments")
    
    # Filters
    filter_group = parser.add_argument_group("Filter options")
    filter_group.add_argument("--skip-archived", action="store_true", help="Skip archived notes")
    filter_group.add_argument("--skip-pinned", action="store_true", help="Skip pinned notes")
    filter_group.add_argument("--skip-trashed", action="store_true", default=True, help="Skip trashed notes (default)")
    filter_group.add_argument("--no-skip-trashed", action="store_false", dest="skip_trashed", help="Include trashed notes")
    filter_group.add_argument("--only-with-attachments", action="store_true", help="Only import notes with attachments")
    
    # Features
    feature_group = parser.add_argument_group("Feature options")
    feature_group.add_argument("--no-labels", action="store_false", dest="import_labels", help="Don't import labels as tags")
    feature_group.add_argument("--no-colors", action="store_false", dest="import_colors", help="Don't add color emojis")
    feature_group.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    feature_group.add_argument("--resume", type=lambda x: x.lower() == "true", default=True, help="Resume previous import")
    
    # Logging
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    parser.add_argument("--log-file", help="Path to log file")
    
    # Delete mode
    parser.add_argument("--delete-memos", action="store_true", help="Delete all memos instead of importing")
    parser.add_argument("--delete-resources", action="store_true", help="Delete all resources instead of importing")
    
    return parser


# ─────────────────────────────────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(verbose=args.verbose, log_file=args.log_file)
    
    try:
        # Load configuration
        config = Config(args)
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    
    # Create importer
    importer = KeepToMemosImporter(config, logger)
    
    # Handle delete mode
    if args.delete_memos:
        count = importer.delete_all("memos", "NORMAL")
        logger.info(f"Deleted {count} memos")
        return
    
    if args.delete_resources:
        count = importer.delete_all("resources", "")
        logger.info(f"Deleted {count} resources")
        return
    
    # Run import
    importer.run()


if __name__ == "__main__":
    main()
