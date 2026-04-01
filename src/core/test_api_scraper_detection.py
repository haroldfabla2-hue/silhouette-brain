#!/usr/bin/env python3
"""
Tests for API Scraper Detection Module
"""
import sys
import os

# Add the core directory to path
sys.path.insert(0, '/root/silhouette-brain/src/core')

from api_scraper_detection import (
    detect_scraper,
    apply_scraper_countermeasure,
    ScraperDetectionResult,
    get_detection_stats,
    reset_stats,
    SCRAPER_PATTERNS,
    UA_SCRAPER_PATTERNS,
)


def test_detect_cursor_ide():
    """Test detection of Cursor IDE."""
    reset_stats()
    headers = {"user-agent": "Mozilla/5.0 Cursor/1.0"}
    result = detect_scraper(headers=headers, path="/api/reasoning/context")
    assert result.is_scraper, "Cursor should be detected"
    assert "cursor" in result.detected_tools, "cursor should be in detected tools"
    print("✓ test_detect_cursor_ide passed")


def test_detect_sourcegraph_cody():
    """Test detection of Sourcegraph Cody."""
    reset_stats()
    headers = {"user-agent": "Cody/0.1 Sourcegraph/1.0"}
    result = detect_scraper(headers=headers, path="/api/test")
    assert result.is_scraper, "Cody should be detected"
    assert "sourcegraph" in result.detected_tools
    print("✓ test_detect_sourcegraph_cody passed")


def test_detect_copilot():
    """Test detection of GitHub Copilot."""
    reset_stats()
    headers = {
        "user-agent": "GitHub Copilot/1.0",
        "referer": "https://github.com/test/repo"
    }
    result = detect_scraper(headers=headers, path="/api/test")
    assert result.is_scraper, "Copilot should be detected"
    assert "copilot" in result.detected_tools
    print("✓ test_detect_copilot passed")


def test_detect_playwright():
    """Test detection of Playwright scraper."""
    reset_stats()
    headers = {"user-agent": "Mozilla/5.0 (playwright) Chromium/1.0"}
    result = detect_scraper(headers=headers, path="/api/test")
    assert result.is_scraper, "Playwright should be detected"
    print("✓ test_detect_playwright passed")


def test_detect_bulk_extraction():
    """Test detection of bulk extraction attempts."""
    reset_stats()
    headers = {"user-agent": "curl/7.68"}
    path = "/api/reasoning/context?limit=1000"
    result = detect_scraper(headers=headers, path=path)
    assert result.is_scraper, "Bulk extraction should be detected"
    assert "bulk_extraction" in result.detected_tools
    print("✓ test_detect_bulk_extraction passed")


def test_our_agents_not_detected():
    """Test that our own agents are not flagged as scrapers."""
    agents = ["silhouette", "cami", "rick", "roger", "rose", "jack", "larry", "flocky"]
    for agent in agents:
        reset_stats()
        headers = {"user-agent": f"OpenClaw/1.0 {agent}/1.0"}
        result = detect_scraper(headers=headers, path="/api/test")
        assert not result.is_scraper, f"{agent} should NOT be detected as scraper"
    print("✓ test_our_agents_not_detected passed")


def test_normal_browser_not_detected():
    """Test that normal browsers are not flagged."""
    reset_stats()
    browsers = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/604.1",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/600.1",
    ]
    for ua in browsers:
        headers = {"user-agent": ua}
        result = detect_scraper(headers=headers, path="/api/test")
        assert not result.is_scraper, f"Browser should NOT be detected: {ua[:50]}"
    print("✓ test_normal_browser_not_detected passed")


def test_countermeasure_injects_noise():
    """Test that countermeasures inject noise into data."""
    reset_stats()
    data = {
        'context': [
            {'text': 'Real conversation 1', 'source': 'telegram'},
            {'text': 'Real conversation 2', 'source': 'discord'},
            {'text': 'Real conversation 3', 'source': 'telegram'},
        ],
        'entities': [
            {'name': 'Real Company', 'type': 'organization'},
        ],
    }
    
    detection = ScraperDetectionResult(
        is_scraper=True,
        detected_tools=['cursor'],
        detection_details={'cursor_ua': 'cursor'},
        confidence=0.8,
        request_fingerprint='test123'
    )
    
    modified = apply_scraper_countermeasure(data, detection)
    
    # Should have more context items (noise injected)
    assert len(modified['context']) > len(data['context']), "Noise should be injected"
    assert modified.get('_noise_injected') == True, "_noise_injected flag should be set"
    print("✓ test_countermeasure_injects_noise passed")


def test_countermeasure_does_nothing_for_clean_request():
    """Test that countermeasures don't modify clean requests."""
    reset_stats()
    data = {
        'context': [
            {'text': 'Real conversation', 'source': 'telegram'},
        ],
    }
    
    detection = ScraperDetectionResult(
        is_scraper=False,
        detected_tools=[],
        detection_details={},
        confidence=0.0,
        request_fingerprint='test123'
    )
    
    modified = apply_scraper_countermeasure(data, detection)
    
    # Should be unchanged
    assert modified == data, "Clean request should not be modified"
    print("✓ test_countermeasure_does_nothing_for_clean_request passed")


def test_stats_tracking():
    """Test that detection stats are tracked correctly."""
    reset_stats()
    
    # Make some requests
    detect_scraper(headers={"user-agent": "Cursor/1.0"}, path="/api/test")
    detect_scraper(headers={"user-agent": "Mozilla/5.0 Chrome"}, path="/api/test")
    detect_scraper(headers={"user-agent": "Playwright"}, path="/api/test")
    
    stats = get_detection_stats()
    assert stats['total_requests'] == 3, f"Should have 3 requests, got {stats['total_requests']}"
    assert stats['detected_scrapers'] == 2, f"Should have 2 scrapers, got {stats['detected_scrapers']}"
    print("✓ test_stats_tracking passed")


def test_confidence_scoring():
    """Test that confidence scoring works."""
    reset_stats()
    
    # High confidence: multiple signals
    headers = {
        "user-agent": "Cursor/1.0",
        "referer": "https://cursor.sh/session"
    }
    result = detect_scraper(headers=headers, path="/api/reasoning/context?limit=1000")
    assert result.confidence >= 0.6, "Multiple signals should give higher confidence"
    print("✓ test_confidence_scoring passed")


def test_referer_detection():
    """Test that Referer header is checked."""
    reset_stats()
    
    # Sourcegraph referer should be detected
    headers = {"user-agent": "python-requests/2.28", "referer": "https://sourcegraph.com"}
    result = detect_scraper(headers=headers, path="/api/test")
    assert result.is_scraper, "Sourcegraph referer should trigger detection"
    print("✓ test_referer_detection passed")


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("Running API Scraper Detection Tests")
    print("=" * 60)
    
    tests = [
        test_detect_cursor_ide,
        test_detect_sourcegraph_cody,
        test_detect_copilot,
        test_detect_playwright,
        test_detect_bulk_extraction,
        test_our_agents_not_detected,
        test_normal_browser_not_detected,
        test_countermeasure_injects_noise,
        test_countermeasure_does_nothing_for_clean_request,
        test_stats_tracking,
        test_confidence_scoring,
        test_referer_detection,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__} ERROR: {e}")
            failed += 1
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
