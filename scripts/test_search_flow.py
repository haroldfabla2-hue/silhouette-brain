import requests
import json

res = requests.get("http://127.0.0.1:9876/api/memory/semantic?query=código+hiper+secreto&min_score=0.1")
print(json.dumps(res.json(), indent=2))
