#!/usr/bin/env python3
import os
import sys
# Añadir el directorio raíz al path para encontrar módulos internos
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path: sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path: sys.path.append(core_dir)
"""
Larry checks Notion for approved posts
Run 2x per day: 9am and 6pm
"""
import os

import requests

NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")


def check_notion():
    """Check Notion for approved/scheduled posts"""
    notion_token = os.getenv("NOTION_TOKEN", "")
    if not notion_token or not NOTION_DATABASE_ID:
        print("NOTION_TOKEN / NOTION_DATABASE_ID no configurados — omitiendo check")
        return

    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    r = requests.post(
        f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query",
        headers=headers,
        json={},
    )
    
    if r.status_code == 200:
        results = r.json().get("results", [])
        
        approved = 0
        pending = 0
        scheduled = 0
        
        for item in results:
            try:
                props = item.get("properties", {})
                status_field = props.get("Status", {}) or props.get("status", {})
                if isinstance(status_field, dict):
                    status = status_field.get("select", {}).get("name", "") or status_field.get("name", "")
                else:
                    status = ""
            except:
                status = ""
            
            if status == "Approved":
                approved += 1
            elif status == "Pending Approval":
                pending += 1
            elif status == "Scheduled":
                scheduled += 1
        
        print(f"📋 Notion Posts: {pending} pending, {approved} approved, {scheduled} scheduled")
        
        if approved > 0:
            print(f"   ⚠️ {approved} posts ready to publish!")
    else:
        print(f"Error: {r.status_code}")

if __name__ == "__main__":
    check_notion()
