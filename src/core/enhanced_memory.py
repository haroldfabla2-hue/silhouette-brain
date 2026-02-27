#!/usr/bin/env python3
"""
Enhanced Biomimetic Memory - v3
Based on research from Mem0, Google Titans, human neuroscience
Features:
- Pattern detection (recurring topics)
- Surprise metric (important = unexpected/repeated)
- Entity extraction
- Memory consolidation
"""
import json
import os
import re
from datetime import datetime
from collections import Counter
from memory_noise_filter import is_operational_runtime_noise, should_skip_ingestion

# Research-based patterns
CRITICAL_ENTITY_PATTERNS = [
    (r'\b(Alberto|Beto|Farah)\b', 'person:alberto'),
    (r'\b(Brandistry|Nexus|Silhouette)\b', 'proyecto'),
    (r'\b(vegetariano|no come carne)\b', 'preferencia'),
    (r'\b(pizza|pastel de papa)\b', 'preferencia'),
    (r'\b(no alucinar|no mentir)\b', 'regla'),
    (r'\b(n8n|Neo4j|Redis|Docker)\b', 'tech'),
]

RECURRING_PATTERNS = [
    r'no alucinar',
    r'no mentir',
    r'importante',
    r'recordar',
    r'memoria',
    r'Brandistry',
    r'vegetariano',
]

class EnhancedMemory:
    def __init__(self):
        self.load()
    
    def load(self):
        f = os.getenv('BRAIN_DATA_DIR', './data'/priority_memory.json'
        try:
            with open(f) as fp:
                data = json.load(fp)
                self.never_forget = data.get('never_forget', [])
                self.important = data.get('important', [])
                self.recurring = data.get('recurring', {})  # NEW: track repeats
                self.entities = data.get('entities', {})     # NEW: extracted entities
                self.last_consolidation = data.get('last_consolidation')
        except:
            self.never_forget = []
            self.important = []
            self.recurring = {}
            self.entities = {}
            self.last_consolidation = None
        self._prune_runtime_noise_entries()
    
    def save(self):
        f = os.getenv('BRAIN_DATA_DIR', './data'/priority_memory.json'
        data = {
            'never_forget': self.never_forget[-20:],
            'important': self.important[-50:],
            'recurring': self.recurring,
            'entities': self.entities,
            'last_consolidation': datetime.now().isoformat()
        }
        with open(f, 'w') as fp:
            json.dump(data, fp, indent=2)

    def _prune_runtime_noise_entries(self):
        """Self-heal: remove operational runtime noise from persisted priority memory."""
        original_nf = len(self.never_forget)
        original_imp = len(self.important)

        self.never_forget = [
            item for item in self.never_forget
            if not is_operational_runtime_noise(item.get('content', ''))
        ]
        self.important = [
            item for item in self.important
            if not is_operational_runtime_noise(item.get('content', ''))
        ]

        noisy_recurring = [
            key for key in list(self.recurring.keys())
            if is_operational_runtime_noise(key)
        ]
        for key in noisy_recurring:
            self.recurring.pop(key, None)

        if len(self.never_forget) != original_nf or len(self.important) != original_imp or noisy_recurring:
            self.save()
    
    def extract_entities(self, text):
        """Extract entities like Mem0 does"""
        entities = []
        for pattern, label in CRITICAL_ENTITY_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                entities.append((label, match.lower() if isinstance(match, str) else match.group(0).lower()))
        return entities
    
    def calculate_surprise(self, text, entities):
        """
        Surprise metric - based on Google Titans research:
        - Repeated topics = higher surprise (important)
        - Unexpected = higher surprise
        - Emotional = higher surprise
        """
        score = 0.0
        text_lower = text.lower()
        
        # Check for recurring patterns
        for pattern in RECURRING_PATTERNS:
            if re.search(pattern, text_lower):
                count = self.recurring.get(pattern, 0) + 1
                self.recurring[pattern] = count
                # More repeated = more important
                score += min(0.3, count * 0.05)
        
        # Entities contribute
        score += len(entities) * 0.15
        
        # Emotional markers
        if any(x in text_lower for x in ['odio', 'amor', 'gracias', 'nunca', 'siempre']):
            score += 0.2
        
        # Repetition detection - if Alberto says same thing multiple times
        text_short = text[:100].lower()
        for item in self.never_forget + self.important:
            if text_short in item.get('content', '').lower():
                score += 0.3  # Repeated message
        
        return min(1.0, score)
    
    def process(self, role, content, source='unknown'):
        """Process with enhanced intelligence"""
        if len(content) < 20:
            return None
        if should_skip_ingestion(content):
            return None
        
        # Extract entities
        entities = self.extract_entities(content)
        
        # Update entity tracking
        for label, name in entities:
            if label not in self.entities:
                self.entities[label] = {}
            if name not in self.entities[label]:
                self.entities[label][name] = 0
            self.entities[label][name] += 1
        
        # Calculate surprise
        surprise = self.calculate_surprise(content, entities)
        
        # Determine importance
        importance = surprise
        
        # Boost for critical entities
        for label, name in entities:
            if label in ['person:alberto', 'proyecto', 'regla']:
                importance += 0.3
        
        importance = min(1.0, importance)
        
        if importance < 0.15:
            return None
        
        # Check for duplicate
        for item in self.never_forget + self.important:
            if item.get('content', '')[:80] == content[:80]:
                return None  # Already exists
        
        entry = {
            'content': content[:500],
            'importance': importance,
            'surprise': surprise,
            'entities': entities,
            'source': source,
            'timestamp': datetime.now().isoformat()
        }
        
        if importance >= 0.5:
            self.never_forget.append(entry)
            print(f"[MEMORY] ⭐ IMPORTANTE (surprise:{surprise:.2f}): {content[:50]}...")
        else:
            self.important.append(entry)
        
        self.save()
        return entry
    
    def get_context(self):
        """Get context with recurring patterns highlighted"""
        ctx = []
        
        # NEVER FORGET
        for item in self.never_forget[-10:]:
            ctx.append({
                'type': '⭐ NEVER FORGET',
                'content': item['content'],
                'surprise': item.get('surprise', 0),
                'entities': item.get('entities', [])
            })
        
        # Important
        for item in self.important[-5:]:
            ctx.append({
                'type': '📌 Importante',
                'content': item['content'],
                'surprise': item.get('surprise', 0)
            })
        
        # Recurring patterns
        if self.recurring:
            top_patterns = sorted(self.recurring.items(), key=lambda x: x[1], reverse=True)[:3]
            ctx.append({
                'type': '🔄 RECURRENT',
                'patterns': top_patterns
            })
        
        return ctx


# Singleton
_em = None
def get_enhanced_memory():
    global _em
    if _em is None:
        _em = EnhancedMemory()
    return _em


if __name__ == "__main__":
    em = get_enhanced_memory()
    
    print("=== ENHANCED MEMORY v3 ===\n")
    
    # Test with recurring pattern detection
    tests = [
        ("user", "Alberto es vegetariano y no come carne", "test"),
        ("user", "No me gusta que alucines, es importante que no mientas", "test"),
        ("user", "Recordar: no alucines nunca", "test"),
        ("user", "También recuerda que no debes mentir nunca", "test"),
        ("user", "Brandistry es nuestro proyecto principal", "test"),
    ]
    
    for role, content, source in tests:
        result = em.process(role, content, source)
        if result:
            print(f"  ✓ Saved: {content[:40]}... (surprise:{result.get('surprise',0):.2f})")
    
    print(f"\nRecurring patterns: {em.recurring}")
    print(f"Entities: {em.entities}")
