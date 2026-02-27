#!/usr/bin/env python3
"""
Short-term memory cache using Redis
Like human "working memory" - lasts seconds to minutes
"""
import redis
import json
import time

class ShortTermCache:
    def __init__(self):
        self.redis = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        self.prefix = "working:"
        self.default_ttl = 300  # 5 minutes
    
    def store(self, key, value, ttl=None):
        """Store in working memory"""
        self.redis.setex(
            f"{self.prefix}{key}",
            ttl or self.default_ttl,
            json.dumps(value)
        )
    
    def get(self, key):
        """Retrieve from working memory"""
        data = self.redis.get(f"{self.prefix}{key}")
        return json.loads(data) if data else None
    
    def get_recent(self, limit=10):
        """Get recent working memories"""
        keys = self.redis.keys(f"{self.prefix}*")
        results = []
        for key in keys[:limit]:
            data = self.redis.get(key)
            if data:
                results.append(json.loads(data))
        return results
    
    def clear_expired(self):
        """Clear expired (Redis does this automatically)"""
        pass

_short_cache = None
def get_short_cache():
    global _short_cache
    if _short_cache is None:
        _short_cache = ShortTermCache()
    return _short_cache

if __name__ == "__main__":
    sc = get_short_cache()
    sc.store("current_task", {"task": "testing", "agent": "silhouette"})
    print("Working memory:", sc.get("current_task"))
    print("Recent:", sc.get_recent())
