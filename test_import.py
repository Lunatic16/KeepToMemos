#!/usr/bin/env python3
"""
Unit tests for KeepToMemos conversion functions.

Run with: python -m pytest test_import.py -v
Or: python test_import.py
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock

# Import functions from import.py
import importlib.util

# Load import.py as a module (suppress main execution)
spec = importlib.util.spec_from_file_location("keepsake", "import.py")
keepsake = importlib.util.module_from_spec(spec)

# Mock sys.argv to prevent argparse from running
import sys
original_argv = sys.argv
sys.argv = ["keepsake", "--help"]

try:
    spec.loader.exec_module(keepsake)
except SystemExit:
    pass  # argparse exits after --help

sys.argv = original_argv

md = keepsake.md
convert_checklist_to_markdown = keepsake.convert_checklist_to_markdown
convert_timestamp = keepsake.convert_timestamp
create_text_node = keepsake.create_text_node
KEEP_COLOR_MAP = keepsake.KEEP_COLOR_MAP


class TestMarkdownConversion(unittest.TestCase):
    """Test HTML to Markdown conversion."""
    
    def test_empty_html(self):
        """Test conversion of empty HTML."""
        result = md("")
        self.assertEqual(result, "")
    
    def test_simple_paragraph(self):
        """Test conversion of simple paragraph."""
        html = "<p>Hello World</p>"
        result = md(html)
        self.assertIn("Hello World", result)
    
    def test_multiple_paragraphs(self):
        """Test conversion of multiple paragraphs."""
        html = "<p>First paragraph</p><p>Second paragraph</p>"
        result = md(html)
        self.assertIn("First paragraph", result)
        self.assertIn("Second paragraph", result)
    
    def test_bold_text(self):
        """Test conversion of bold text."""
        html = "<p>This is <strong>bold</strong> text</p>"
        result = md(html)
        self.assertIn("**bold**", result)
    
    def test_italic_text(self):
        """Test conversion of italic text."""
        html = "<p>This is <em>italic</em> text</p>"
        result = md(html)
        self.assertIn("*italic*", result)
    
    def test_links(self):
        """Test conversion of links."""
        html = '<p>Visit <a href="https://example.com">Example</a></p>'
        result = md(html)
        self.assertIn("[Example](https://example.com)", result)
    
    def test_lists(self):
        """Test conversion of unordered lists."""
        html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
        result = md(html)
        # markdownify uses * for lists by default
        self.assertIn("* Item 1", result)
        self.assertIn("* Item 2", result)


class TestChecklistConversion(unittest.TestCase):
    """Test Google Keep checklist to Markdown conversion."""
    
    def test_empty_checklist(self):
        """Test conversion of empty checklist."""
        result = convert_checklist_to_markdown([])
        self.assertEqual(result, "")
    
    def test_single_unchecked_item(self):
        """Test single unchecked item."""
        checklist = [{"text": "Buy milk", "isChecked": False}]
        result = convert_checklist_to_markdown(checklist)
        self.assertEqual(result, "- [ ] Buy milk")
    
    def test_single_checked_item(self):
        """Test single checked item."""
        checklist = [{"text": "Buy milk", "isChecked": True}]
        result = convert_checklist_to_markdown(checklist)
        self.assertEqual(result, "- [x] Buy milk")
    
    def test_multiple_items(self):
        """Test multiple items with mixed states."""
        checklist = [
            {"text": "Buy milk", "isChecked": True},
            {"text": "Buy bread", "isChecked": False},
            {"text": "Buy eggs", "isChecked": True},
        ]
        result = convert_checklist_to_markdown(checklist)
        lines = result.split("\n")
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0], "- [x] Buy milk")
        self.assertEqual(lines[1], "- [ ] Buy bread")
        self.assertEqual(lines[2], "- [x] Buy eggs")
    
    def test_empty_text_items(self):
        """Test that empty text items are skipped."""
        checklist = [
            {"text": "", "isChecked": False},
            {"text": "Valid item", "isChecked": False},
            {"text": "   ", "isChecked": False},
        ]
        result = convert_checklist_to_markdown(checklist)
        self.assertEqual(result, "- [ ] Valid item")
    
    def test_missing_is_checked(self):
        """Test items without isChecked field default to unchecked."""
        checklist = [{"text": "Item without state"}]
        result = convert_checklist_to_markdown(checklist)
        self.assertEqual(result, "- [ ] Item without state")


class TestTimestampConversion(unittest.TestCase):
    """Test timestamp conversion from Google Keep format."""
    
    def test_valid_timestamp(self):
        """Test conversion of valid microsecond timestamp."""
        # Example: 1672531200000000 = 2023-01-01 00:00:00 UTC
        usec = 1672531200000000
        result = convert_timestamp(usec)
        # Check for either Jan 1 or Dec 31 (timezone dependent)
        self.assertTrue("2023-01-01" in result or "2022-12-31" in result)
    
    def test_zero_timestamp(self):
        """Test conversion of zero timestamp."""
        result = convert_timestamp(0)
        self.assertTrue(len(result) > 0)  # Should return current time
        self.assertIn("T", result)

    def test_none_timestamp(self):
        """Test conversion of None timestamp."""
        result = convert_timestamp(None)
        self.assertTrue(len(result) > 0)
        self.assertIn("T", result)

    def test_recent_timestamp(self):
        """Test conversion of recent timestamp."""
        now_usec = int(datetime.now().timestamp() * 1_000_000)
        result = convert_timestamp(now_usec)
        # Should be close to current time
        self.assertTrue(len(result) > 0)


class TestTextNodeCreation(unittest.TestCase):
    """Test text node creation for Memos API."""
    
    def test_simple_text_node(self):
        """Test creation of simple text node."""
        content = "Hello World"
        result = create_text_node(content)
        self.assertEqual(result["type"], "TEXT")
        self.assertEqual(result["textNode"]["content"], content)
    
    def test_multiline_text_node(self):
        """Test creation of multiline text node."""
        content = "Line 1\nLine 2\nLine 3"
        result = create_text_node(content)
        self.assertEqual(result["type"], "TEXT")
        self.assertIn("\n", result["textNode"]["content"])
    
    def test_empty_text_node(self):
        """Test creation of empty text node."""
        content = ""
        result = create_text_node(content)
        self.assertEqual(result["type"], "TEXT")
        self.assertEqual(result["textNode"]["content"], "")


class TestColorMap(unittest.TestCase):
    """Test Google Keep color mapping."""
    
    def test_all_colors_defined(self):
        """Test that all expected colors are in the map."""
        expected_colors = [
            "DEFAULT", "RED", "ORANGE", "YELLOW", "GREEN",
            "TEAL", "BLUE", "DARK_BLUE", "PURPLE", "PINK", "BROWN", "GRAY"
        ]
        for color in expected_colors:
            self.assertIn(color, KEEP_COLOR_MAP)
    
    def test_default_has_no_emoji(self):
        """Test that DEFAULT color has no emoji."""
        self.assertEqual(KEEP_COLOR_MAP["DEFAULT"], "")
    
    def test_colors_have_emojis(self):
        """Test that color values are emojis."""
        for color, emoji in KEEP_COLOR_MAP.items():
            if color != "DEFAULT":
                self.assertTrue(len(emoji) > 0, f"{color} should have an emoji")


class TestIntegration(unittest.TestCase):
    """Integration tests with sample data."""
    
    @classmethod
    def setUpClass(cls):
        """Create temporary test directory with sample files."""
        cls.test_dir = tempfile.mkdtemp()
        
        # Sample note 1: Simple text note
        cls.note1 = {
            "title": "Test Note",
            "textContentHtml": "<p>This is a test note.</p>",
            "createdTimestampUsec": 1672531200000000,
            "userEditedTimestampUsec": 1672617600000000,
            "isTrashed": False,
            "isArchived": False,
            "isPinned": False,
            "attachments": [],
        }
        
        # Sample note 2: Checklist note
        cls.note2 = {
            "title": "Shopping List",
            "listContent": [
                {"text": "Milk", "isChecked": True},
                {"text": "Bread", "isChecked": False},
            ],
            "createdTimestampUsec": 1672531200000000,
            "userEditedTimestampUsec": 1672617600000000,
            "isTrashed": False,
            "isArchived": False,
            "isPinned": True,
            "color": "YELLOW",
            "labelList": ["Personal", "Shopping"],
            "attachments": [],
        }
        
        # Sample note 3: Note with attachment
        cls.note3 = {
            "title": "Photo Note",
            "textContentHtml": "<p>Check out this photo!</p>",
            "createdTimestampUsec": 1672531200000000,
            "userEditedTimestampUsec": 1672617600000000,
            "isTrashed": False,
            "isArchived": False,
            "isPinned": False,
            "attachments": [
                {"filePath": "test_image.jpg", "mimetype": "image/jpeg"}
            ],
        }
        
        # Write sample files
        with open(os.path.join(cls.test_dir, "note1.json"), "w") as f:
            json.dump(cls.note1, f)
        
        with open(os.path.join(cls.test_dir, "note2.json"), "w") as f:
            json.dump(cls.note2, f)
        
        with open(os.path.join(cls.test_dir, "note3.json"), "w") as f:
            json.dump(cls.note3, f)
    
    @classmethod
    def tearDownClass(cls):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(cls.test_dir)
    
    def test_sample_files_exist(self):
        """Test that sample files were created."""
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "note1.json")))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "note2.json")))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "note3.json")))
    
    def test_load_sample_note1(self):
        """Test loading sample note 1."""
        with open(os.path.join(self.test_dir, "note1.json"), "r") as f:
            note = json.load(f)
        self.assertEqual(note["title"], "Test Note")
        self.assertFalse(note["isTrashed"])
    
    def test_load_sample_note2(self):
        """Test loading sample note 2."""
        with open(os.path.join(self.test_dir, "note2.json"), "r") as f:
            note = json.load(f)
        self.assertEqual(note["title"], "Shopping List")
        self.assertTrue(note["isPinned"])
        self.assertEqual(len(note["listContent"]), 2)
    
    def test_load_sample_note3(self):
        """Test loading sample note 3."""
        with open(os.path.join(self.test_dir, "note3.json"), "r") as f:
            note = json.load(f)
        self.assertEqual(note["title"], "Photo Note")
        self.assertEqual(len(note["attachments"]), 1)


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)
