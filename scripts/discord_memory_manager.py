"""
Discord Memory Manager - Guarda mensajes de Discord en silhouette-brain
"""
import requests
import json
import datetime
import os

BRAIN_API_URL = os.getenv("BRAIN_API_URL", "http://localhost:9876/api/memory")

def save_discord_message(content: str, channel: str, message_type: str, metadata: dict = None):
    """
    Guarda un mensaje de Discord en la Brain API.
    
    Args:
        content: Contenido del mensaje
        channel: Canal de Discord
        message_type: "incoming" o "outgoing"
        metadata: Metadatos adicionales
    """
    if message_type not in ["incoming", "outgoing"]:
        print(f"Error: Invalid message_type '{message_type}'")
        return False
    
    timestamp = datetime.datetime.now().isoformat()
    tags = ["discord", message_type]
    
    payload = {
        "text": content[:500],  # Limitar a 500 chars
        "importance": 0.7,
        "tier": "MEDIUM",
        "metadata": {
            "channel": channel,
            "timestamp": timestamp,
            "discord_type": message_type,
            **(metadata if metadata else {})
        },
        "tags": tags
    }
    
    try:
        response = requests.post(BRAIN_API_URL, json=payload, timeout=10)
        if response.status_code in [200, 201]:
            print(f"✅ {message_type} message saved to memory")
            return True
        else:
            print(f"❌ Error: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

if __name__ == "__main__":
    # Test
    print("--- Testing outgoing ---")
    save_discord_message("Test from CLI", "1476353920984023103", "outgoing")
    print("--- Testing incoming ---")  
    save_discord_message("Test from user", "1476353920984023103", "incoming")
