import json
import os
import requests
from datetime import datetime
from time import sleep
import base64
from markdownify import MarkdownConverter

# Memos configuration
BASE_URL = "http://....../api/v1/"  # Change this to your Memos URL
ACCESS_TOKEN = "memos_pat_..... # Add your access token here
KEEP_TAKEOUT_DIR = "./" # json Google Takeout Directory

class IPC(MarkdownConverter):
    def convert_p(self, el, text, parent_tags):
        return text + "\n"

# Create shorthand method for conversion
def md(html, **options):
    return IPC(**options).convert(html)

def delete_all(what, state):
    # Get all of type
    response = requests.get(f"{BASE_URL}{what}?pageSize=2000&state={state}", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"})
    if response.status_code == 200:
        # print(response.text)
        print(f"\nDeleting all {what}...")
        items = response.json()[what]
        print(f"\nFound {len(items)} {what} to delete.")
        for item in items:
            # print(memo)
            item_name = item['name']
            delete_url = f"{BASE_URL}{item_name}"
            delete_response = requests.delete(delete_url, headers={"Authorization": f"Bearer {ACCESS_TOKEN}"})
            if delete_response.status_code == 200:
                print(f".", end="", flush=True)
            else:
                print(f"\nFailed to delete {what} with Name: {item_name} - {delete_response.status_code} - {delete_response.text}")
    else:
        print(f"\nFailed to fetch {what}: {response.status_code} - {response.text}")
        

def convert_timestamp(usec_timestamp):
    """Convert Google Keep's microseconds timestamp to ISO format"""
    seconds = usec_timestamp / 1_000_000
    return datetime.fromtimestamp(seconds).isoformat() + "Z"

def create_text_node(content):
    """Create a simple text node for the memo content"""
    return {
        "type": "TEXT",
        "textNode": {
            "content": content
        }
    }

def convert_checklist_to_markdown(list_content):
    """Convert Google Keep checklist items to markdown"""
    markdown_lines = []
    for item in list_content:
        text = item.get('text', '').strip()
        if not text:  # Skip empty items
            continue
        is_checked = item.get('isChecked', False)
        checkbox = "- [x] " if is_checked else "- [ ] "
        markdown_lines.append(checkbox + text)
    return "\n".join(markdown_lines)

def import_keep_note(json_file_path):
    """Import a single Google Keep note into Memos"""
    with open(json_file_path, 'r', encoding='utf-8') as f:
        note = json.load(f)
    
    # Skip trashed notes
    if note.get('isTrashed', False):
        print(f"\nSkipping trashed note: {json_file_path}")
        return
    
    # Handle checklist notes
    if note.get('listContent'):
        checklist_md = convert_checklist_to_markdown(note['listContent'])
        title = note.get('title', 'Checklist')
        full_content = f"### {title}\n{checklist_md}" if title else checklist_md
    else:
        # Regular note handling (your existing code)
        title = note.get('title', '')
        content = md(note.get('textContentHtml', ''))
        full_content = f"### {title}\n{content}" if title else content


    # Check if there are attached images
    attachments = note.get('attachments', [])
    
    
    # Get creation time (use edited time if creation not available)
    created_time = note.get('createdTimestampUsec', note.get('userEditedTimestampUsec'))

    edited_time = note.get('userEditedTimestampUsec')

    # Check if content is empty
    if not full_content.strip() and not attachments:
        print(f"\nSkipping empty note without attachments: {json_file_path}")
        return

    # Prepare the payload for Memos API
    payload = {
        "content": full_content,
        "nodes": [create_text_node(full_content)],
        "createTime": convert_timestamp(created_time),
        "updateTime": convert_timestamp(edited_time),
        "displayTime": convert_timestamp(edited_time),
        "visibility": "PRIVATE",  # Change to "PUBLIC" if you want notes public
        "state": "ARCHIVED" if note.get('isArchived', False) else "NORMAL",
        "pinned": note.get('isPinned', False)
    
    }

    
    headers = {
        "Content-Type": "text/plain;charset=UTF-8",
        "Authorization": f"Bearer {ACCESS_TOKEN}"  # If your API requires authentication
    }
    
    # Add OpenId to the URL if required by your Memos instance
    url = f"{BASE_URL}memos"
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:

            resources = []
            # Add attachments if any
            for attachment in attachments:
                # Get filepath
                file_path = attachment.get('filePath')
                # Load image as base64
                contents = {}
                with open(file_path, 'rb') as img_file:
                    img_data = img_file.read()
                    base64_image = base64.b64encode(img_data).decode('utf-8')
                    contents[file_path] = base64_image
                    # Post image to resources pai
                    post_url = f"{BASE_URL}resources"
                    post_payload = {
                        "filename": file_path,
                        "type": attachment.get('mimetype'),
                        "content": base64_image,
                        "memo": response.json()['name'],
                    }
                    post_response = requests.post(post_url, json=post_payload, headers=headers)
                    if post_response.status_code == 200:
                        print(f".",  end="", flush=True)
                    else:
                        print(f"\nFailed to upload image: {file_path} - {post_response.status_code} - {post_response.text}")
                
                

            # Send a patch requeest to update the times...
            patch_payload = {
                "createTime": convert_timestamp(created_time),
                "updateTime": convert_timestamp(edited_time),
                "displayTime": convert_timestamp(edited_time),
                "state": "ARCHIVED" if note.get('isArchived', False) else "NORMAL",
            }
            patch_url = f"{BASE_URL}{response.json()['name']}"
            patch_response = requests.patch(patch_url, json=patch_payload, headers=headers)
            if patch_response.status_code == 200:
                print(f"." , end="", flush=True)
            else:
                print(f"\nFailed to update times for {json_file_path}: {patch_response.status_code} - {patch_response.text}")
        else:
            print(f"\nFailed to import {json_file_path}: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"\nError importing {json_file_path}: {str(e)}")

def process_keep_directory(directory_path):
    """Process all JSON files in a directory"""
    for filename in os.listdir(directory_path):
        if filename.endswith('.json'):
            file_path = os.path.join(directory_path, filename)
            import_keep_note(file_path)
            sleep(0.1)

if __name__ == "__main__":
   
    # delete_all("memos", "ARCHIVED")
    # delete_all("memos", "NORMAL")
    # delete_all("resources", "")

    print(f"Starting import from {KEEP_TAKEOUT_DIR}")
    process_keep_directory(KEEP_TAKEOUT_DIR)
    print("\nImport completed!")
