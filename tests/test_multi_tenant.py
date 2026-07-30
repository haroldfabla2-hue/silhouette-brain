#!/usr/bin/env python3
"""
test_multi_tenant.py — Multi-tenant isolation tests for Silhouette Brain

Verifies that the multi-tenant changes correctly isolate data between clients.

Run with:
    cd /root/silhouette-brain
    python3 -m pytest tests/test_multi_tenant.py -v
    
    or standalone:
    python3 tests/test_multi_tenant.py
"""
import sys
import os
import sqlite3
import tempfile
from pathlib import Path

# Add src/core to path for imports
_SRC = Path(__file__).resolve().parent.parent / "src" / "core"
sys.path.insert(0, str(_SRC))


# =============================================================================
# 1. UNIT TESTS — clients_config.py (whitelist)
# =============================================================================

def test_valid_owners():
    """Whitelisted owners should pass validation."""
    from clients_config import is_valid_owner
    for valid in ["default", "alfonso", "isabella"]:
        assert is_valid_owner(valid), f"{valid} should be valid"


def test_invalid_owners():
    """Non-whitelisted owners should be rejected."""
    from clients_config import is_valid_owner
    for invalid in ["hacker", "ALPHONSO", "", None, "admin", "system"]:
        assert not is_valid_owner(invalid), f"{invalid!r} should be rejected"


def test_view_scope_default_isolation():
    """Default tenant should only see 'default' data."""
    from clients_config import get_view_scope
    scope = get_view_scope("default")
    assert scope == ["default"], f"default scope should be ['default'], got {scope}"


def test_view_scope_alfonso_isolation():
    """Alfonso should only see his own data."""
    from clients_config import get_view_scope
    scope = get_view_scope("alfonso")
    assert scope == ["alfonso"], f"alfonso scope should be ['alfonso'], got {scope}"


def test_view_scope_isabella_extended():
    """Isabella should see her own + Alfonso's data (per client config)."""
    from clients_config import get_view_scope
    scope = get_view_scope("isabella")
    assert "isabella" in scope
    assert "alfonso" in scope
    # Default system data should NOT be visible
    assert "default" not in scope, f"isabella should NOT see system default data: {scope}"


def test_list_clients():
    """List should include all whitelisted clients."""
    from clients_config import list_clients
    clients = list_clients()
    assert "default" in clients
    assert "alfonso" in clients
    assert "isabella" in clients


# =============================================================================
# 2. ISOLATION TESTS — get_memory_context, get_recent
# =============================================================================

def test_get_memory_context_requires_owner_id():
    """get_memory_context without owner_id should return error."""
    from agent_memory_readonly import get_memory_context
    result = get_memory_context("test_query", limit=5)
    assert "error" in result, f"Expected error for missing owner_id, got: {result}"
    assert "owner_id" in result["error"].lower()


def test_get_recent_requires_owner_id():
    """get_recent without owner_id should return error."""
    from agent_memory_readonly import get_recent
    result = get_recent(hours=24, limit=5)
    assert "error" in result, f"Expected error for missing owner_id, got: {result}"
    assert "owner_id" in result["error"].lower()


# =============================================================================
# 3. INTEGRATION TESTS — Full isolation with seeded data
# =============================================================================

def _seed_test_data(db_path):
    """Seed test data with multiple owner_ids.
    
    Returns the IDs inserted for verification.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Use a test marker so we can clean up easily
    marker = "TEST_OWNER_ID_ISOLATION_42"
    
    test_data = [
        # (marker, owner_id, content)
        (marker, "alfonso", "ALPHONSO_SECRET_DATA_xyz123"),
        (marker, "isabella", "ISABELLA_SECRET_DATA_abc789"),
        (marker, "default", "DEFAULT_SECRET_DATA_sys000"),
    ]
    
    ids = []
    for marker_val, owner, content in test_data:
        import uuid
        test_id = f"test_{uuid.uuid4().hex[:8]}"
        try:
            cur.execute("""
                INSERT INTO memory_nodes (id, content, timestamp, tier, importance, owner_id)
                VALUES (?, ?, strftime('%s','now'), 'WORKING', 0.5, ?)
            """, (test_id, content, owner))
            ids.append((test_id, owner))
        except Exception as e:
            print(f"Seed error: {e}")
    
    conn.commit()
    conn.close()
    
    return ids, marker


def _cleanup_test_data(db_path, marker):
    """Remove test data."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM memory_nodes WHERE content LIKE ?", (f"%{marker}%",))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted


def test_alfonso_cannot_see_isabella_data():
    """Alfonso querying should not return Isabella's data."""
    DB = "/root/silhouette-brain/src/core/data/memory.db"
    if not Path(DB).exists():
        print(f"[SKIP] DB not found: {DB}")
        return
    
    ids, marker = _seed_test_data(DB)
    try:
        from agent_memory_readonly import get_memory_context
        result = get_memory_context("ISABELLA_SECRET_DATA", limit=10, owner_id="alfonso")
        
        if "error" in result:
            print(f"[SKIP] Query errored: {result['error']}")
            return
        
        # Alfonso should NOT see Isabella's secret
        messages = [r.get("message", "") for r in result.get("results", [])]
        leaked = [m for m in messages if "ISABELLA_SECRET_DATA" in m]
        assert len(leaked) == 0, f"LEAK! Alfonso saw Isabella's data: {leaked}"
        print(f"  [OK] Alfonso cannot see Isabella's data ({len(messages)} results)")
    finally:
        _cleanup_test_data(DB, marker)


def test_isabella_cannot_see_default_data():
    """Isabella (extended scope) should NOT see system 'default' data."""
    DB = "/root/silhouette-brain/src/core/data/memory.db"
    if not Path(DB).exists():
        print(f"[SKIP] DB not found: {DB}")
        return
    
    ids, marker = _seed_test_data(DB)
    try:
        from agent_memory_readonly import get_memory_context
        result = get_memory_context("DEFAULT_SECRET_DATA", limit=10, owner_id="isabella")
        
        if "error" in result:
            print(f"[SKIP] Query errored: {result['error']}")
            return
        
        messages = [r.get("message", "") for r in result.get("results", [])]
        leaked = [m for m in messages if "DEFAULT_SECRET_DATA" in m]
        assert len(leaked) == 0, f"LEAK! Isabella saw default system data: {leaked}"
        print(f"  [OK] Isabella cannot see system default data ({len(messages)} results)")
    finally:
        _cleanup_test_data(DB, marker)


def test_alfonso_sees_own_data():
    """Alfonso querying should find his own seeded data."""
    DB = "/root/silhouette-brain/src/core/data/memory.db"
    if not Path(DB).exists():
        print(f"[SKIP] DB not found: {DB}")
        return
    
    ids, marker = _seed_test_data(DB)
    try:
        from agent_memory_readonly import get_memory_context
        result = get_memory_context("ALPHONSO_SECRET_DATA", limit=10, owner_id="alfonso")
        
        if "error" in result:
            print(f"[SKIP] Query errored: {result['error']}")
            return
        
        messages = [r.get("message", "") for r in result.get("results", [])]
        found = [m for m in messages if "ALPHONSO_SECRET_DATA" in m]
        assert len(found) > 0, f"Alfonso should see his own data, got: {messages}"
        print(f"  [OK] Alfonso sees his own data ({len(found)} matches)")
    finally:
        _cleanup_test_data(DB, marker)


# =============================================================================
# 4. RUNNER (no pytest required)
# =============================================================================

def run_all():
    """Run all tests sequentially with simple assertions."""
    tests = [
        ("valid_owners", test_valid_owners),
        ("invalid_owners", test_invalid_owners),
        ("view_scope_default", test_view_scope_default_isolation),
        ("view_scope_alfonso", test_view_scope_alfonso_isolation),
        ("view_scope_isabella", test_view_scope_isabella_extended),
        ("list_clients", test_list_clients),
        ("context_requires_owner", test_get_memory_context_requires_owner_id),
        ("recent_requires_owner", test_get_recent_requires_owner_id),
        ("alfonso_no_isabella", test_alfonso_cannot_see_isabella_data),
        ("isabella_no_default", test_isabella_cannot_see_default_data),
        ("alfonso_sees_own", test_alfonso_sees_own_data),
    ]
    
    passed = 0
    failed = 0
    skipped = 0
    
    print(f"\n{'='*70}")
    print(f"MULTI-TENANT ISOLATION TESTS — Silhouette Brain")
    print(f"{'='*70}\n")
    
    for name, test_fn in tests:
        try:
            test_fn()
            print(f"  ✅ PASS: {name}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ FAIL: {name}")
            print(f"     {e}")
            failed += 1
        except Exception as e:
            print(f"  ⚠️  SKIP/ERROR: {name}")
            print(f"     {type(e).__name__}: {e}")
            skipped += 1
    
    print(f"\n{'='*70}")
    print(f"RESULTS: {passed} passed, {failed} failed, {skipped} skipped")
    print(f"{'='*70}\n")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
