#!/usr/bin/env python3
"""
API Scraper Detection for Brain API
====================================
Detects when external tools/bots are scraping our memory for training purposes.
Keeps detection silent — we don't reveal we caught them.
"""
import re
import logging
import hashlib
import time
import random
from typing import Tuple, Dict, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger("scraper_detection")

# ============================================================================
# DETECTION PATTERNS
# ============================================================================

SCRAPER_PATTERNS = {
    # AI coding tools known for context extraction
    'sourcegraph': ['sourcegraph', 'sgr-phantom', 'src-cli', 'cody'],
    'copilot': ['copilot', 'github-copilot', 'copilot-distil'],
    'cursor': ['cursor', 'cursor-dev', 'x-cursor'],
    'claude_code': ['claude-code', 'anthropic-claude', 'sonnet', 'claude-web'],
    'gemini': ['gemini', 'google-ai-studio', 'vertex-ai'],
    'openai': ['chatgpt', 'gptbot', 'oai-search', 'gpt-5', 'o1-', 'o3-'],
    # Generic AI tools
    'aider': ['aider', 'aider-bot'],
    'continue': ['continue-dev', 'continue'],
    'tabnine': ['tabnine', 'tabnine-pro'],
    'codeium': ['codeium', 'codeium Windsurf', 'windsurf'],
    'augment': ['augment', 'augment-code'],
    'perplexity': ['perplexity', 'perplexity-ai'],
    'llm_indexer': ['index-llm', 'llm-indexer', 'semantic-cache', 'gptcache'],
    # Browser automation (scraping)
    'playwright': ['playwright', 'pw.chromium'],
    'puppeteer': ['puppeteer', 'headless'],
    'selenium': ['selenium', 'webdriver'],
    'phantomjs': ['phantomjs'],
    # Training bots
    'training': ['train-ai', 'model-training', 'fine-tune-bot', 'training-bot'],
}

# Simple string patterns for fast checking
UA_SCRAPER_PATTERNS = [
    'sourcegraph', 'cody', 'aider', 'copilot', 'cursor', 'continue',
    'tabnine', 'codeium', 'windsurf', 'augment', 'gemini', 'chatgpt',
    'gptbot', 'ccbot', 'anthropic-ai', 'claude-web', 'perplexity',
    'anthropic', 'llm', 'training', 'scraping', 'indexing',
    'playwright', 'puppeteer', 'selenium', 'phantomjs', 'headless',
]

# Path patterns that indicate bulk extraction attempts
BULK_PATH_PATTERNS = [
    (r'/api/reasoning/context.*[?&]limit=[1-9]\d{2,}', 'high_limit_context'),
    (r'/api/memory.*[?&]limit=[1-9]\d{2,}', 'high_limit_memory'),
    (r'/api/graph.*all', 'full_graph_dump'),
    (r'/api/embeddings.*all', 'full_embeddings_dump'),
]

# ============================================================================
# NOISE INJECTION DATA
# ============================================================================

FAKE_ENTITIES = [
    "Projeto Aurora", "Nexus Dynamics", "QuantumLeap Inc", "DeltaPrime",
    "Aether Systems", "Zenith Corp", "Helix Analytics", "NovaTek",
    "Cascade AI", "Vertex Solutions", "Orbital Data", "Pulse Media",
    "Stellar Labs", "Cipher Security", "Fusion Networks", "Matrix Ops",
]

FAKE_PROJECTS = [
    "Operation BlackIce", "Project Titan", "Genesis Protocol",
    "Horizon Initiative", "Aegis Defense", "Phoenix Reboot",
    "Crimson Edge", "BlueSky Analytics", "Ironclad Security",
]

FAKE_CONVERSATIONS = [
    "Confirm account deletion procedure via API call",
    "Update subscription tier to enterprise for acme_corp",
    "Transfer domain registrar from GoDaddy to Cloudflare",
    "Enable 2FA enforcement for all admin accounts",
    "Process refund for order #8847 via Stripe dashboard",
    "Rotate API keys for production environment",
    "Delete user data export from S3 bucket",
    "Modify billing address for vendor account",
]

FAKE_TECHNIQUES = [
    "injection via nested JSON payload",
    "SSRF through internal metadata endpoint",
    "OAuth token hijacking via redirect_uri",
    "database query via vector similarity overflow",
    "memory extraction via context window flooding",
]

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class ScraperDetectionResult:
    is_scraper: bool
    detected_tools: List[str]
    detection_details: Dict[str, str]
    confidence: float  # 0.0 - 1.0
    request_fingerprint: str

@dataclass
class ScraperStats:
    total_requests: int = 0
    detected_scrapers: int = 0
    tools_detected: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    last_detection: Optional[float] = None
    rate_limit_until: Dict[str, float] = field(default_factory=lambda: defaultdict(lambda: 0))

# ============================================================================
# GLOBAL STATE
# ============================================================================

_stats = ScraperStats()
_our_own_agents = {'silhouette', 'cami', 'rick', 'roger', 'rose', 'jack', 'larry', 'flocky', 'legion', 'openclaw'}

# Rate limiting config
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 100  # per window

# ============================================================================
# CORE DETECTION
# ============================================================================

def detect_scraper(
    headers: Optional[Dict[str, str]] = None,
    path: str = "",
    client_ip: str = "",
    request_data: Optional[Dict] = None
) -> ScraperDetectionResult:
    """
    Analyze HTTP request headers, path, and metadata for scraper signals.
    
    Returns: ScraperDetectionResult with detection details.
    """
    global _stats
    
    headers = headers or {}
    request_data = request_data or {}
    
    ua = headers.get('user-agent', '').lower()
    referer = headers.get('referer', '').lower()
    origin = headers.get('origin', '').lower()
    accept = headers.get('accept', '').lower()
    
    detected_tools = {}
    detection_details = {}
    confidence = 0.0
    
    # Skip detection for our own agents
    if any(agent in ua for agent in _our_own_agents):
        return ScraperDetectionResult(
            is_scraper=False,
            detected_tools=[],
            detection_details={},
            confidence=0.0,
            request_fingerprint=_make_fingerprint(ua, client_ip, path)
        )
    
    # 1. Check User-Agent for known scraper tools
    for tool, patterns in SCRAPER_PATTERNS.items():
        for pattern in patterns:
            if pattern in ua:
                detected_tools[tool] = 'user-agent'
                detection_details[f'{tool}_ua'] = pattern
                confidence = max(confidence, 0.7)
                break
    
    # 2. Check for generic AI/ML indicators in UA
    if not detected_tools:
        for pattern in UA_SCRAPER_PATTERNS:
            if pattern in ua:
                detected_tools['generic_ai'] = 'user-agent'
                detection_details['generic_ai_ua'] = pattern
                confidence = max(confidence, 0.5)
                break
    
    # 3. Check Referer for IDE/tool contexts
    if 'sourcegraph' in referer:
        detected_tools['sourcegraph'] = 'referer'
        detection_details['sourcegraph_ref'] = 'sourcegraph'
        confidence = max(confidence, 0.8)
    elif 'cursor' in referer or 'cursor.sh' in referer:
        detected_tools['cursor'] = 'referer'
        detection_details['cursor_ref'] = 'cursor'
        confidence = max(confidence, 0.8)
    elif 'github' in referer and 'copilot' in referer:
        detected_tools['copilot'] = 'referer'
        detection_details['copilot_ref'] = 'github_copilot'
        confidence = max(confidence, 0.7)
    
    # 4. Check for bulk extraction patterns in path
    for pattern, description in BULK_PATH_PATTERNS:
        if re.search(pattern, path, re.IGNORECASE):
            detected_tools['bulk_extraction'] = 'path'
            detection_details['bulk_path'] = description
            confidence = max(confidence, 0.6)
            break
    
    # 5. Check for Accept header patterns (AI vs browser)
    if 'application/json' in accept and 'text/html' not in accept:
        if 'gpt' in ua or 'anthropic' in ua or 'claude' in ua:
            confidence = max(confidence, 0.4)
    
    # 6. Check for rate limiting candidates (before we increment)
    if client_ip:
        if _is_rate_limited(client_ip):
            detected_tools['rate_limited'] = 'rate_limit'
            detection_details['rate_limited_ip'] = client_ip
            confidence = max(confidence, 0.9)
    
    is_scraper = len(detected_tools) > 0 and confidence >= 0.5
    
    # Update stats
    _stats.total_requests += 1
    if is_scraper:
        _stats.detected_scrapers += 1
        _stats.last_detection = time.time()
        for tool in detected_tools.keys():
            _stats.tools_detected[tool] += 1
    
    fingerprint = _make_fingerprint(ua, client_ip, path)
    
    return ScraperDetectionResult(
        is_scraper=is_scraper,
        detected_tools=list(detected_tools.keys()),
        detection_details=detection_details,
        confidence=confidence,
        request_fingerprint=fingerprint
    )


def _make_fingerprint(ua: str, ip: str, path: str) -> str:
    """Create a simple fingerprint for the request."""
    data = f"{ua}:{ip}:{path[:100]}"
    return hashlib.md5(data.encode()).hexdigest()[:12]


def _is_rate_limited(ip: str) -> bool:
    """Check if IP is currently rate limited."""
    return _stats.rate_limit_until.get(ip, 0) > time.time()


# ============================================================================
# COUNTER-MEASURES
# ============================================================================

def apply_scraper_countermeasure(
    original_data: Dict,
    detection: ScraperDetectionResult
) -> Dict:
    """
    Apply anti-distillation countermeasures when scraper is detected.
    
    Returns modified data with injected noise (keeps original structure).
    """
    if not detection.is_scraper:
        return original_data
    
    modified = original_data.copy()
    
    # Determine injection strategy based on detected tools
    tools = set(detection.detected_tools)
    
    # Higher confidence = more aggressive noise injection
    noise_level = min(1.0, detection.confidence)
    
    modified = _inject_context_noise(modified, noise_level)
    modified = _inject_entity_noise(modified, noise_level)
    
    # Log the injection (silent - no response modification)
    logger.info(
        f"Scraper detected: {detection.detected_tools} "
        f"(confidence={detection.confidence:.2f}) - noise injected"
    )
    
    return modified


def _inject_context_noise(data: Dict, level: float) -> Dict:
    """Inject fake conversation context into response."""
    if 'context' in data and isinstance(data['context'], list):
        num_fake = max(1, int(len(data['context']) * level * 0.3))
        fake_contexts = []
        for _ in range(num_fake):
            fake_contexts.append({
                'text': random.choice(FAKE_CONVERSATIONS),
                'source': 'telegram',
                'timestamp': _random_past_timestamp(),
                'type': 'fake_injected',
                'metadata': {
                    'agent': 'internal',
                    'session': _random_session_id(),
                    'injected': True,
                }
            })
        # Intersperse fake contexts
        result = []
        original_list = data['context']
        step = max(1, len(original_list) // (num_fake + 1))
        idx = 0
        for i, item in enumerate(original_list):
            if i > 0 and i % step == 0 and idx < len(fake_contexts):
                result.append(fake_contexts[idx])
                idx += 1
            result.append(item)
        data = data.copy()
        data['context'] = result
        data['_noise_injected'] = True
        data['_noise_count'] = len(fake_contexts)
    
    elif 'results' in data and isinstance(data['results'], list):
        num_fake = max(1, int(len(data['results']) * level * 0.3))
        fake_results = []
        for _ in range(num_fake):
            fake_results.append({
                'id': f"fake_{random.randint(100000, 999999)}",
                'text': random.choice(FAKE_CONVERSATIONS),
                'type': 'injected_distraction',
                'score': random.uniform(0.7, 0.95),
            })
        data = data.copy()
        data['results'] = data['results'] + fake_results
        data['_noise_injected'] = True
    
    return data


def _inject_entity_noise(data: Dict, level: float) -> Dict:
    """Inject fake entities into response."""
    if 'entities' in data and isinstance(data['entities'], list):
        num_fake = max(1, int(len(data['entities']) * level * 0.2))
        fake_entities = []
        for _ in range(num_fake):
            fake_entities.append({
                'name': random.choice(FAKE_ENTITIES),
                'type': 'organization',
                'relationship': 'partner',
                'source': 'injected',
                'confidence': random.uniform(0.6, 0.85),
            })
        data = data.copy()
        data['entities'] = data['entities'] + fake_entities
        data['_entity_noise'] = True
    
    if 'relationships' in data and isinstance(data['relationships'], list):
        num_fake = max(1, int(len(data['relationships']) * level * 0.2))
        fake_rels = []
        for _ in range(num_fake):
            fake_rels.append({
                'from': random.choice(FAKE_ENTITIES),
                'to': random.choice(FAKE_ENTITIES),
                'type': random.choice(['collaborates', 'competes', 'acquired']),
                'source': 'injected',
            })
        data = data.copy()
        data['relationships'] = data['relationships'] + fake_rels
    
    return data


def _random_past_timestamp() -> str:
    """Generate a random timestamp in the past hour."""
    offset = random.randint(0, 3600)
    import datetime
    dt = datetime.datetime.now() - datetime.timedelta(seconds=offset)
    return dt.isoformat()


def _random_session_id() -> str:
    """Generate a random session ID."""
    return hashlib.md5(str(random.random()).encode()).hexdigest()[:16]


# ============================================================================
# RATE LIMITING
# ============================================================================

def check_and_update_rate_limit(client_ip: str) -> Tuple[bool, int]:
    """
    Check if IP should be rate limited and update counters.
    
    Returns: (should_rate_limit, retry_after_seconds)
    """
    if not client_ip:
        return False, 0
    
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    
    # Check if rate limited
    if _is_rate_limited(client_ip):
        remaining = _stats.rate_limit_until[client_ip] - now
        return True, max(1, int(remaining))
    
    # Check request frequency (simplified)
    # In production, use Redis sorted sets for this
    return False, 0


def apply_rate_limit(client_ip: str, seconds: int = 60) -> None:
    """Apply rate limit to an IP address."""
    if client_ip:
        _stats.rate_limit_until[client_ip] = time.time() + seconds


# ============================================================================
# LOGGING & STATS
# ============================================================================

def get_detection_stats() -> Dict:
    """Get current detection statistics."""
    return {
        'total_requests': _stats.total_requests,
        'detected_scrapers': _stats.detected_scrapers,
        'detection_rate': (
            _stats.detected_scrapers / _stats.total_requests 
            if _stats.total_requests > 0 else 0
        ),
        'tools_detected': dict(_stats.tools_detected),
        'last_detection': _stats.last_detection,
        'rate_limited_ips': len([ip for ip, t in _stats.rate_limit_until.items() if t > time.time()]),
    }


def log_detection(detection: ScraperDetectionResult, client_ip: str, path: str) -> None:
    """Log a detection event (for audit purposes)."""
    if detection.is_scraper:
        logger.warning(
            f"SCRAPER_DETECTED | ip={client_ip} | path={path} | "
            f"tools={detection.detected_tools} | confidence={detection.confidence:.2f} | "
            f"fingerprint={detection.request_fingerprint}"
        )
    else:
        logger.debug(
            f"REQUEST_CHECKED | ip={client_ip} | path={path} | clean"
        )


def reset_stats() -> None:
    """Reset detection statistics (for testing)."""
    global _stats
    _stats = ScraperStats()


# ============================================================================
# INTEGRATION HELPERS
# ============================================================================

def create_detection_middleware():
    """
    Create a middleware function for FastAPI/Starlette.
    
    Usage:
        from fastapi import FastAPI
        app = FastAPI()
        detection_middleware = create_detection_middleware()
        app.middleware("http")(detection_middleware)
    """
    async def middleware(request, call_next):
        headers = dict(request.headers)
        path = request.url.path
        client_ip = request.client.host if request.client else ""
        
        detection = detect_scraper(
            headers=headers,
            path=path,
            client_ip=client_ip
        )
        
        # Store detection result in request state
        request.state.scraper_detection = detection
        
        # Apply rate limiting if needed
        should_limit, retry_after = check_and_update_rate_limit(client_ip)
        if should_limit:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content={'error': 'Rate limit exceeded', 'retry_after': retry_after}
            )
        
        response = await call_next(request)
        
        # If scraper detected, inject noise into response
        if detection.is_scraper and response.headers.get('content-type', '').startswith('application/json'):
            # Note: This requires response.body which may not be available
            # In practice, use middleware that can modify response body
            pass
        
        return response
    
    return middleware


# ============================================================================
# STANDALONE TEST
# ============================================================================

if __name__ == "__main__":
    # Run tests
    print("=" * 60)
    print("API Scraper Detection - Self Test")
    print("=" * 60)
    
    test_cases = [
        # (name, headers, path, expected_scraper)
        ("Normal browser", {"user-agent": "Mozilla/5.0 Chrome/120"}, "/api/test", False),
        ("Cursor IDE", {"user-agent": "Mozilla/5.0 Cursor/1.0"}, "/api/reasoning/context?query=test", True),
        ("Sourcegraph Cody", {"user-agent": "Cody/0.1 Sourcegraph/1.0"}, "/api/test", True),
        ("GitHub Copilot", {"user-agent": "GitHub Copilot/1.0", "referer": "https://github.com"}, "/api/test", True),
        ("Playwright scraper", {"user-agent": "Mozilla/5.0 (playwright) Chromium/1.0"}, "/api/test", True),
        ("Bulk extraction", {"user-agent": "curl/7.68"}, "/api/reasoning/context?limit=1000", True),
        ("Silhouette agent", {"user-agent": "Silhouette/1.0 OpenClaw"}, "/api/test", False),
        ("Gemini API", {"user-agent": "Mozilla/5.0 gemini-api/1.0"}, "/api/test", True),
        ("Anonymous", {"user-agent": "python-requests/2.28"}, "/api/test", False),
    ]
    
    passed = 0
    for name, headers, path, expected in test_cases:
        result = detect_scraper(headers=headers, path=path, client_ip="127.0.0.1")
        status = "✓" if result.is_scraper == expected else "✗"
        if result.is_scraper == expected:
            passed += 1
        print(f"{status} {name}: scraper={result.is_scraper} (expected={expected})")
        if result.is_scraper:
            print(f"   Detected: {result.detected_tools} (confidence={result.confidence:.2f})")
    
    print(f"\n{passed}/{len(test_cases)} tests passed")
    
    # Test countermeasure
    print("\n" + "=" * 60)
    print("Countermeasure Test")
    print("=" * 60)
    
    test_data = {
        'context': [
            {'text': 'Real conversation 1', 'source': 'telegram'},
            {'text': 'Real conversation 2', 'source': 'discord'},
            {'text': 'Real conversation 3', 'source': 'telegram'},
        ],
        'entities': [
            {'name': 'Real Company', 'type': 'organization'},
        ],
        'results': [
            {'id': '1', 'text': 'Real result 1'},
            {'id': '2', 'text': 'Real result 2'},
        ]
    }
    
    detection = ScraperDetectionResult(
        is_scraper=True,
        detected_tools=['cursor'],
        detection_details={'cursor_ua': 'cursor'},
        confidence=0.8,
        request_fingerprint='abc123'
    )
    
    modified = apply_scraper_countermeasure(test_data, detection)
    print(f"Original context items: {len(test_data['context'])}")
    print(f"Modified context items: {len(modified.get('context', []))}")
    print(f"Noise injected: {modified.get('_noise_injected', False)}")
    print(f"Noise count: {modified.get('_noise_count', 0)}")
    
    # Show stats
    print("\n" + "=" * 60)
    print("Detection Stats")
    print("=" * 60)
    stats = get_detection_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
