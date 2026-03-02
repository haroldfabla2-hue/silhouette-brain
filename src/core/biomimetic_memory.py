#!/usr/bin/env python3
"""
Biomimetic Memory - FILTRADO INTELIGENTE
Solo guarda lo que importa, filtra ruido
"""
import json
import os
import sys
import re
from datetime import datetime

sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', os.path.dirname(os.path.abspath(__file__))))

# Cosas que NUNCA olvidamos
CRITICAL_PATTERNS = [
    r'\b(Alberto|Beto|Farah)\b',
    r'\bvegetariano\b',
    r'\b(pizza|pastel de papa)\b',
    r'\bBrandistry\b',
    r'\bNexus\b',
    r'\bSilhouette\b',
    r'\b( Roger | Cami | Rick | Rose | Jack | Larry | Flocky )\b',
    r'\b( no alucinar | no mentir | error | bug )\b',
    r'\b( decisión | acordado | importante | recordar )\b',
]

NOISE_PATTERNS = [
    r'^\{.*\}$',
    r'^===.*===$',
    r'\[.*EMBEDDINGS.*\]',
    r'^/root/',
    r'^python3',
    r'^Memory -',
    r'^\[NEO4J\]',
    r'^\[REDIS\]',
    r'^Command exited',
    r'toolCall',
    r'toolResult',
]

def is_noise(text):
    if len(text) < 30:
        return True
    if text.strip().startswith('{') and text.strip().endswith('}'):
        return True
    for p in NOISE_PATTERNS:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False

def calculate_importance(text):
    if is_noise(text):
        return 0.0
    score = 0.0
    for p in CRITICAL_PATTERNS:
        if re.search(p, text, re.IGNORECASE):
            score += 0.4
            break
    if 'alberto' in text.lower() or 'beto' in text.lower():
        score += 0.3
    for p in ['brandistry', 'nexus', 'silhouette']:
        if p in text.lower():
            score += 0.3
    if any(x in text.lower() for x in ['decisión', 'acordado', 'prioridad']):
        score += 0.3
    if any(x in text.lower() for x in ['roger', 'cami', 'rick', 'rose', 'jack', 'larry', 'flocky']):
        score += 0.2
    return min(1.0, score)

def extract_tags(text):
    tags = []
    tl = text.lower()
    if 'alberto' in tl or 'beto' in tl:
        tags.append('persona:alberto')
    for p in ['brandistry', 'nexus', 'silhouette']:
        if p in tl:
            tags.append(f'proyecto:{p}')
    for a in ['roger', 'cami', 'rick', 'rose', 'jack', 'larry', 'flocky']:
        if a in tl:
            tags.append(f'agent:{a}')
    for t in ['n8n', 'neo4j', 'redis', 'docker', 'github']:
        if t in tl:
            tags.append(f'tech:{t}')
    return list(set(tags))

class BiomimeticMemory:
    def __init__(self):
        self.load_memory()
    
    def load_memory(self):
        f = os.path.join(os.getenv('BRAIN_DATA_DIR', './data'), 'priority_memory.json')
        try:
            with open(f) as fp:
                d = json.load(fp)
                self.never_forget = d.get('never_forget', [])
                self.important = d.get('important', [])
        except:
            self.never_forget = []
            self.important = []
    
    def save_memory(self):
        f = os.path.join(os.getenv('BRAIN_DATA_DIR', './data'), 'priority_memory.json')
        with open(f, 'w') as fp:
            json.dump({
                'never_forget': self.never_forget[-20:],
                'important': self.important[-50:],
                'updated': datetime.now().isoformat()
            }, fp, indent=2)
    
    def process(self, role, content, source='unknown'):
        if is_noise(content):
            return None
        imp = calculate_importance(content)
        if imp < 0.2:
            return None
        # Check duplicate
        for item in self.never_forget + self.important:
            if item.get('content', '')[:100] == content[:100]:
                return None
        entry = {
            'content': content[:500],
            'importance': imp,
            'tags': extract_tags(content),
            'source': source,
            'timestamp': datetime.now().isoformat()
        }
        if imp >= 0.5:
            self.never_forget.append(entry)
            print(f"[MEMORY] ⭐ {content[:50]}...")
        else:
            self.important.append(entry)
        self.save_memory()
        return entry
    
    def get_context(self):
        ctx = []
        for item in self.never_forget[-10:]:
            ctx.append({'type': '⭐ NEVER FORGET', 'content': item['content'], 'tags': item.get('tags', [])})
        for item in self.important[-5:]:
            ctx.append({'type': '📌 Importante', 'content': item['content'], 'tags': item.get('tags', [])})
        return ctx

_bm = None
def get_biomimetic_memory():
    global _bm
    if _bm is None:
        _bm = BiomimeticMemory()
    return _bm

if __name__ == "__main__":
    bm = get_biomimetic_memory()
    print("=== FILTRADO ACTIVADO ===")
    print(f"NEVER FORGET: {len(bm.never_forget)}")
    print(f"Important: {len(bm.important)}")
