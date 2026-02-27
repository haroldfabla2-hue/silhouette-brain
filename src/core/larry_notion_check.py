#!/usr/bin/env python3
"""
Larry checks Notion for approved posts
Run 2x per day: 9am and 6pm
"""
import requests

def check_notion():
    """Check Notion for approved/scheduled posts"""
    NOTION_TOKEN = "ntn_s2485459680a290Y3ITe0BlnQi9A7zJclchiVclfmTW93w"
    headers = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}
    
    # Get database
    r = requests.post("https://api.notion.com/v1/databases/30d09425-1ae0-8166-8efe-d95386f5a5d4/query",
                     headers=headers, json={})
    
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
