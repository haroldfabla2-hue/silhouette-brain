"""
Session Storage V2 - Improved session storage for Silhouette Brain.

Features:
1. Tombstone pattern for deletions (mark instead of rewrite)
2. Head/Tail reading for large JSONL files
3. Ephemeral progress filtering (skip transient entries on persist)
4. Parent-UUID chain for message threading

Based on patterns from Claude Code's sessionStorage.ts
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Ephemeral types that should not be persisted (progress ticks, etc.)
EPHEMERAL_TYPES: set[str] = {
    'bash_progress',
    'sleep_progress',
    'mcp_progress',
    'powershell_progress',
}

# Tombstone threshold: compact when >20% of entries are tombstones
TOMBSTONE_COMPACT_THRESHOLD: float = 0.20

# Default buffer size for head/tail reads (64KB)
LITE_READ_BUF_SIZE: int = 65536

# Max bytes to read for transcript (prevents OOM on large files)
MAX_TRANSCRIPT_READ_BYTES: int = 50 * 1024 * 1024


# ---------------------------------------------------------------------------
# Type definitions
# ---------------------------------------------------------------------------

Entry = dict


# ---------------------------------------------------------------------------
# 1. Tombstone Pattern
# ---------------------------------------------------------------------------

def create_tombstone(uuid: str) -> Entry:
    """
    Create a tombstone entry for soft-delete.
    
    Instead of rewriting the entire JSONL file when deleting a message,
    we mark the entry as deleted with a tombstone marker.
    """
    return {
        'type': 'tombstone',
        'uuid': uuid,
        'deleted_at': datetime.now(timezone.utc).isoformat(),
    }


def is_tombstone(entry: Entry) -> bool:
    """Check if an entry is a tombstone (soft-deleted)."""
    return entry.get('type') == 'tombstone'


def get_entry_uuid(entry: Entry) -> Optional[str]:
    """Get the UUID of an entry, handling both 'uuid' and 'sessionId' fields."""
    return entry.get('uuid') or entry.get('sessionId')


def is_entry_deleted(entries: list[Entry], uuid: str) -> bool:
    """Check if a specific UUID has been soft-deleted (has a tombstone)."""
    for entry in entries:
        if entry.get('type') == 'tombstone' and entry.get('uuid') == uuid:
            return True
    return False


def filter_tombstones(entries: list[Entry]) -> list[Entry]:
    """Filter out tombstone entries when reading (returns active entries only)."""
    return [e for e in entries if not is_tombstone(e)]


def get_tombstone_ratio(entries: list[Entry]) -> float:
    """
    Calculate the ratio of tombstones to total entries.
    Used to determine when to compact the file.
    """
    if not entries:
        return 0.0
    
    tombstone_count = sum(1 for e in entries if is_tombstone(e))
    return tombstone_count / len(entries)


def should_compact(entries: list[Entry]) -> bool:
    """Check if file should be compacted based on tombstone ratio."""
    return get_tombstone_ratio(entries) > TOMBSTONE_COMPACT_THRESHOLD


def soft_delete_entry(filepath: str, uuid: str) -> bool:
    """
    Soft-delete an entry by appending a tombstone marker.
    Does NOT rewrite the file - just appends a single line.
    
    Returns True if successful, False if file doesn't exist or error.
    """
    try:
        tombstone = create_tombstone(uuid)
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(json.dumps(tombstone, ensure_ascii=False) + '\n')
        return True
    except (IOError, OSError):
        return False


def compact_file(filepath: str) -> int:
    """
    Rewrite the file, removing all tombstone entries.
    
    Returns the number of entries removed.
    """
    # Read all entries
    entries = read_entries(filepath)
    
    # Count tombstones
    original_count = len(entries)
    active_entries = filter_tombstones(entries)
    removed_count = original_count - len(active_entries)
    
    if removed_count == 0:
        return 0
    
    # Rewrite the file with active entries only
    temp_path = filepath + '.tmp'
    try:
        with open(temp_path, 'w', encoding='utf-8') as f:
            for entry in active_entries:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        
        # Atomic replace
        os.replace(temp_path, filepath)
        return removed_count
    except (IOError, OSError):
        # Clean up temp file on error
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


# ---------------------------------------------------------------------------
# 2. Head/Tail Reading for Large Files
# ---------------------------------------------------------------------------

def read_tail(filepath: str, lines: int = 50) -> list[Entry]:
    """
    Read the last N lines from a JSONL file without loading the entire file.
    
    Uses the same algorithm as Claude Code's sessionStoragePortable.ts:
    - Seek to near end of file
    - Read backwards to find N complete lines
    
    This is efficient for large files (multiple GB).
    """
    try:
        file_size = os.path.getsize(filepath)
        if file_size == 0:
            return []
        
        entries: list[Entry] = []
        line_count = 0
        position = file_size
        
        # Read in chunks from the end
        chunk_size = min(LITE_READ_BUF_SIZE, file_size)
        
        with open(filepath, 'rb') as f:
            while position > 0 and line_count < lines:
                # Read a chunk
                read_size = min(chunk_size, position)
                position -= read_size
                f.seek(position)
                chunk = f.read(read_size)
                
                # Process chunk in reverse
                chunk_str = chunk.decode('utf-8', errors='replace')
                
                # Find complete lines (in reverse)
                # Split by newline and process
                parts = chunk_str.split('\n')
                
                # If chunk doesn't end with newline, first part is partial line
                # that should be prepended to the last line from previous chunk
                if not chunk_str.endswith('\n'):
                    # First part is a partial line, will be completed by next chunk
                    # Save it for later
                    pass
                
                # Process complete lines in reverse
                for i in range(len(parts) - 1, -1, -1):
                    part = parts[i].strip()
                    if not part:
                        continue
                    
                    # If this is the first chunk and first part is partial, skip it
                    if i == 0 and not chunk_str.endswith('\n'):
                        # This is the start of a partial line, don't count it yet
                        continue
                    
                    line_count += 1
                    if line_count <= lines:
                        try:
                            entries.insert(0, json.loads(part))
                        except json.JSONDecodeError:
                            line_count -= 1  # Don't count bad lines
                
                if line_count >= lines:
                    break
        
        return entries[:lines]
        
    except (IOError, OSError, json.JSONDecodeError):
        return []


def read_head(filepath: str, lines: int = 50) -> list[Entry]:
    """
    Read the first N lines from a JSONL file.
    
    Simple line-by-line reading, stops after N lines.
    """
    entries: list[Entry] = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i >= lines:
                    break
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except (IOError, OSError):
        pass
    
    return entries


def read_entries(filepath: str, max_bytes: int = MAX_TRANSCRIPT_READ_BYTES) -> list[Entry]:
    """
    Read all entries from a JSONL file with optional size limit.
    
    For files larger than max_bytes, reading is aborted to prevent OOM.
    """
    entries: list[Entry] = []
    
    try:
        file_size = os.path.getsize(filepath)
        
        # If file is too large, return empty and let caller handle
        if file_size > max_bytes:
            return entries
        
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except (IOError, OSError):
        pass
    
    return entries


def read_entries_filtered(
    filepath: str,
    skip_tombstones: bool = True,
    skip_ephemeral: bool = True,
) -> list[Entry]:
    """
    Read entries with filtering options.
    
    Args:
        filepath: Path to JSONL file
        skip_tombstones: If True, filter out tombstone entries
        skip_ephemeral: If True, filter out ephemeral progress entries
    """
    entries = read_entries(filepath)
    
    result = []
    for entry in entries:
        # Skip tombstones
        if skip_tombstones and is_tombstone(entry):
            continue
        
        # Skip ephemeral entries
        if skip_ephemeral and is_ephemeral(entry):
            continue
        
        result.append(entry)
    
    return result


# ---------------------------------------------------------------------------
# 3. Ephemeral Progress Filtering
# ---------------------------------------------------------------------------

def is_ephemeral(entry: Entry) -> bool:
    """
    Check if an entry is ephemeral (should not be persisted).
    
    Ephemeral entries are high-frequency progress updates that are
    UI-only and not meaningful for conversation history.
    """
    data_type = entry.get('type') or entry.get('dataType')
    if isinstance(data_type, str):
        return data_type in EPHEMERAL_TYPES
    return False


def filter_ephemeral(entries: list[Entry]) -> list[Entry]:
    """Filter out ephemeral entries."""
    return [e for e in entries if not is_ephemeral(e)]


def persist_entries(
    filepath: str,
    entries: list[Entry],
    skip_ephemeral: bool = True,
) -> None:
    """
    Persist entries to a JSONL file, optionally skipping ephemeral entries.
    
    Args:
        filepath: Path to write
        entries: List of entry dicts to write
        skip_ephemeral: If True, filter out ephemeral entries before writing
    """
    if skip_ephemeral:
        entries = filter_ephemeral(entries)
    
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def append_entry(filepath: str, entry: Entry, skip_ephemeral: bool = True) -> None:
    """
    Append a single entry to a JSONL file.
    
    Args:
        filepath: Path to append to
        entry: Entry dict to append
        skip_ephemeral: If True and entry is ephemeral, do not append
    """
    if skip_ephemeral and is_ephemeral(entry):
        return
    
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    
    with open(filepath, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


# ---------------------------------------------------------------------------
# 4. Parent-UUID Chain for Message Threading
# ---------------------------------------------------------------------------

def get_parent_uuid(message: Entry) -> Optional[str]:
    """
    Get the parent UUID of a message for threading.
    
    Supports both 'parentUuid' and 'parent_id' field names.
    """
    return message.get('parentUuid') or message.get('parent_id')


def set_parent_uuid(message: Entry, parent_uuid: str) -> Entry:
    """Set the parent UUID on a message, returning a new dict."""
    return {**message, 'parentUuid': parent_uuid}


def build_chain(entries: list[Entry]) -> dict[str, Entry]:
    """
    Build a dictionary mapping UUID -> Entry for fast parent lookup.
    
    Only includes entries that have a UUID.
    """
    chain: dict[str, Entry] = {}
    
    for entry in entries:
        uuid = get_entry_uuid(entry)
        if uuid:
            chain[uuid] = entry
    
    return chain


def get_thread(entries: list[Entry], root_uuid: str) -> list[Entry]:
    """
    Get all messages in a thread starting from root_uuid.
    
    Returns messages in chronological order (following parent chain).
    """
    chain = build_chain(entries)
    thread: list[Entry] = []
    
    current_uuid = root_uuid
    while current_uuid and current_uuid in chain:
        entry = chain[current_uuid]
        thread.append(entry)
        current_uuid = get_parent_uuid(entry)
    
    return thread


def get_root_message(entries: list[Entry]) -> Optional[Entry]:
    """
    Find the root message of a conversation (message with no parent).
    """
    chain = build_chain(entries)
    uuids_with_parents: set[str] = set()
    
    # Collect all UUIDs that are referenced as parents
    for entry in entries:
        parent = get_parent_uuid(entry)
        if parent:
            uuids_with_parents.add(parent)
    
    # Find the entry that's not referenced as a parent (root)
    for uuid, entry in chain.items():
        if uuid not in uuids_with_parents:
            return entry
    
    return None


def attach_to_parent(entry: Entry, parent_entry: Entry) -> Entry:
    """
    Attach an entry to a parent, copying the parent's UUID as the parentUuid.
    
    Returns a new entry dict with the parent reference.
    """
    parent_uuid = get_entry_uuid(parent_entry)
    if parent_uuid:
        return set_parent_uuid(entry, parent_uuid)
    return entry


# ---------------------------------------------------------------------------
# Combined Operations
# ---------------------------------------------------------------------------

class SessionStorageV2:
    """
    Session storage with all V2 improvements.
    
    Usage:
        storage = SessionStorageV2('/path/to/session.jsonl')
        
        # Read with filtering
        entries = storage.read()
        
        # Write with ephemeral filtering
        storage.append(entry)
        
        # Soft delete (tombstone)
        storage.soft_delete(uuid)
        
        # Compact when needed
        if storage.should_compact():
            storage.compact()
    """
    
    def __init__(self, filepath: str):
        self.filepath = filepath
    
    def read(
        self,
        skip_tombstones: bool = True,
        skip_ephemeral: bool = True,
    ) -> list[Entry]:
        """Read all entries with filtering."""
        return read_entries_filtered(
            self.filepath,
            skip_tombstones=skip_tombstones,
            skip_ephemeral=skip_ephemeral,
        )
    
    def read_head(self, lines: int = 50) -> list[Entry]:
        """Read first N lines."""
        return read_head(self.filepath, lines)
    
    def read_tail(self, lines: int = 50) -> list[Entry]:
        """Read last N lines."""
        return read_tail(self.filepath, lines)
    
    def append(self, entry: Entry, skip_ephemeral: bool = True) -> None:
        """Append a single entry."""
        append_entry(self.filepath, entry, skip_ephemeral=skip_ephemeral)
    
    def write_all(
        self,
        entries: list[Entry],
        skip_ephemeral: bool = True,
    ) -> None:
        """Write all entries (overwrites file)."""
        persist_entries(self.filepath, entries, skip_ephemeral=skip_ephemeral)
    
    def soft_delete(self, uuid: str) -> bool:
        """Soft delete by appending a tombstone."""
        return soft_delete_entry(self.filepath, uuid)
    
    def get_tombstone_ratio(self) -> float:
        """Calculate tombstone ratio."""
        entries = read_entries(self.filepath)
        return get_tombstone_ratio(entries)
    
    def should_compact(self) -> bool:
        """Check if compaction is needed."""
        return self.get_tombstone_ratio() > TOMBSTONE_COMPACT_THRESHOLD
    
    def compact(self) -> int:
        """Compact the file, removing tombstone entries."""
        return compact_file(self.filepath)
    
    def exists(self) -> bool:
        """Check if the session file exists."""
        return os.path.exists(self.filepath)
    
    def get_thread(self, root_uuid: str) -> list[Entry]:
        """Get a thread starting from root_uuid."""
        entries = self.read()
        return get_thread(entries, root_uuid)
    
    def get_parent_chain(self, uuid: str) -> list[Entry]:
        """
        Get the parent chain leading to this UUID.
        Returns list from root to the entry with the given UUID.
        """
        entries = self.read()
        chain = build_chain(entries)
        
        result: list[Entry] = []
        current_uuid = uuid
        
        while current_uuid and current_uuid in chain:
            entry = chain[current_uuid]
            result.insert(0, entry)  # Insert at beginning to get root-first order
            current_uuid = get_parent_uuid(entry)
        
        return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _run_tests():
    """Run basic tests for the module."""
    import tempfile
    
    print("Running session_storage_v2 tests...")
    
    # Test 1: Tombstone creation
    tomb = create_tombstone("test-uuid-123")
    assert tomb['type'] == 'tombstone'
    assert tomb['uuid'] == 'test-uuid-123'
    assert 'deleted_at' in tomb
    print("  ✓ Tombstone creation")
    
    # Test 2: is_tombstone
    assert is_tombstone(tomb) == True
    assert is_tombstone({'type': 'user'}) == False
    print("  ✓ Tombstone detection")
    
    # Test 3: Ephemeral detection
    assert is_ephemeral({'type': 'bash_progress'}) == True
    assert is_ephemeral({'type': 'sleep_progress'}) == True
    assert is_ephemeral({'type': 'mcp_progress'}) == True
    assert is_ephemeral({'type': 'user'}) == False
    print("  ✓ Ephemeral detection")
    
    # Test 4: Parent UUID
    assert get_parent_uuid({'parentUuid': 'parent-123'}) == 'parent-123'
    assert get_parent_uuid({'parent_id': 'parent-456'}) == 'parent-456'
    assert get_parent_uuid({'type': 'user'}) is None
    print("  ✓ Parent UUID extraction")
    
    # Test 5: Filter tombstones
    entries = [
        {'type': 'user', 'uuid': '1'},
        {'type': 'tombstone', 'uuid': '2', 'deleted_at': '2024-01-01'},
        {'type': 'assistant', 'uuid': '3'},
    ]
    filtered = filter_tombstones(entries)
    assert len(filtered) == 2
    assert filtered[0]['uuid'] == '1'
    assert filtered[1]['uuid'] == '3'
    print("  ✓ Tombstone filtering")
    
    # Test 6: Filter ephemeral
    entries = [
        {'type': 'user'},
        {'type': 'bash_progress'},
        {'type': 'assistant'},
        {'type': 'sleep_progress'},
    ]
    filtered = filter_ephemeral(entries)
    assert len(filtered) == 2
    assert all(e['type'] in ('user', 'assistant') for e in filtered)
    print("  ✓ Ephemeral filtering")
    
    # Test 7: Read/Write with tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        temp_path = f.name
    
    try:
        storage = SessionStorageV2(temp_path)
        
        # Write entries
        storage.write_all([
            {'type': 'user', 'uuid': 'u1', 'message': 'Hello'},
            {'type': 'assistant', 'uuid': 'a1', 'message': 'Hi there'},
            {'type': 'bash_progress', 'uuid': 'p1'},  # Should be filtered
        ])
        
        # Read back
        entries = storage.read()
        assert len(entries) == 2  # ephemeral filtered
        assert entries[0]['message'] == 'Hello'
        print("  ✓ Write/read with ephemeral filtering")
        
        # Soft delete
        storage.soft_delete('a1')
        
        # Read with tombstone filter (should still see 2)
        entries = storage.read(skip_tombstones=False)
        assert len(entries) == 3
        print("  ✓ Soft delete (tombstone)")
        
        # Check tombstone ratio
        ratio = storage.get_tombstone_ratio()
        assert 0.3 < ratio < 0.4  # 1 tombstone out of 3
        print(f"  ✓ Tombstone ratio: {ratio:.2f}")
        
        # Compact
        removed = storage.compact()
        assert removed == 1
        
        # Verify compaction
        entries = storage.read()
        assert len(entries) == 2  # Still 2 (1 was already filtered)
        
        # Re-read without filter to verify tombstones are gone
        entries_all = read_entries(temp_path)
        tombstone_count = sum(1 for e in entries_all if is_tombstone(e))
        assert tombstone_count == 0
        print("  ✓ File compaction")
        
    finally:
        os.unlink(temp_path)
    
    # Test 8: Head/Tail reading
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        temp_path = f.name
        for i in range(100):
            f.write(json.dumps({'type': 'user', 'uuid': f'u{i}', 'n': i}) + '\n')
    
    try:
        head = read_head(temp_path, lines=10)
        assert len(head) == 10
        assert head[0]['n'] == 0
        assert head[9]['n'] == 9
        print("  ✓ Head reading")
        
        tail = read_tail(temp_path, lines=10)
        assert len(tail) == 10
        assert tail[0]['n'] == 90
        assert tail[9]['n'] == 99
        print("  ✓ Tail reading")
    finally:
        os.unlink(temp_path)
    
    # Test 9: Chain building
    entries = [
        {'type': 'user', 'uuid': 'u1', 'parentUuid': None},
        {'type': 'assistant', 'uuid': 'a1', 'parentUuid': 'u1'},
        {'type': 'user', 'uuid': 'u2', 'parentUuid': 'a1'},
    ]
    chain = build_chain(entries)
    assert len(chain) == 3
    assert get_parent_uuid(chain['a1']) == 'u1'
    print("  ✓ Chain building")
    
    # Test 10: Thread retrieval (start from leaf to get full chain)
    thread = get_thread(entries, 'u2')
    assert len(thread) == 3
    assert thread[0]['uuid'] == 'u2'
    assert thread[1]['uuid'] == 'a1'
    assert thread[2]['uuid'] == 'u1'
    print("  ✓ Thread retrieval")
    
    print("\n✅ All tests passed!")


if __name__ == '__main__':
    _run_tests()
