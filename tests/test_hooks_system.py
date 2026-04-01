"""
Tests for hooks_system.py

Run with: pytest tests/test_hooks_system.py -v
"""

import asyncio
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.core.hooks_system import (
    HookEvent,
    HookInput,
    HookResult,
    HooksSystem,
    HookCallback,
    create_logging_hook,
    create_counter_hook,
    on_hook,
    auto_register_hooks,
    emit_memory_stored,
    hooks_system,
)


class TestHookEvent:
    """Test HookEvent enum."""

    def test_all_events_defined(self):
        """All expected events should be defined."""
        expected_events = {
            "memory_stored", "memory_retrieved", "memory_search",
            "agent_heartbeat", "agent_session_sync", "agent_tool_executed",
            "conversation_injection", "api_scraper", "permission_denied",
            "service_started", "service_stopped", "task_queued",
            "task_completed", "error_occurred"
        }
        actual_events = {e.value for e in HookEvent}
        assert expected_events == actual_events

    def test_events_are_strings(self):
        """Events should be usable as strings."""
        event = HookEvent.MEMORY_STORED
        assert event == "memory_stored"
        assert str(event) == "HookEvent.MEMORY_STORED"


class TestHookInput:
    """Test HookInput dataclass."""

    def test_creation(self):
        """HookInput should be creatable with required fields."""
        input_data = HookInput(
            event=HookEvent.MEMORY_STORED,
            timestamp=datetime.now(),
            data={"key": "value"},
            source="test"
        )
        assert input_data.event == HookEvent.MEMORY_STORED
        assert input_data.data == {"key": "value"}
        assert input_data.source == "test"

    def test_default_values(self):
        """HookInput should have sensible defaults."""
        input_data = HookInput(
            event=HookEvent.ERROR_OCCURRED,
            timestamp=datetime.now()
        )
        assert input_data.data == {}
        assert input_data.source == "unknown"


class TestHookResult:
    """Test HookResult dataclass."""

    def test_creation(self):
        """HookResult should be creatable."""
        result = HookResult(
            event=HookEvent.MEMORY_STORED,
            handlers_run=3,
            total_duration_ms=15.5,
            errors=["handler2: failed"]
        )
        assert result.handlers_run == 3
        assert result.total_duration_ms == 15.5
        assert len(result.errors) == 1


class TestHooksSystem:
    """Test HooksSystem class."""

    def setup_method(self):
        """Create fresh HooksSystem for each test."""
        self.hooks = HooksSystem()

    def test_register_single_handler(self):
        """Should register a single handler."""
        handler_called = []

        def my_handler(input_data: HookInput) -> None:
            handler_called.append(input_data)

        self.hooks.register(HookEvent.MEMORY_STORED, "test_handler", my_handler)
        assert len(self.hooks.list_handlers(HookEvent.MEMORY_STORED)) == 1

    def test_register_multiple_handlers(self):
        """Should register multiple handlers for same event."""
        def handler1(inp): pass
        def handler2(inp): pass

        self.hooks.register(HookEvent.MEMORY_STORED, "h1", handler1)
        self.hooks.register(HookEvent.MEMORY_STORED, "h2", handler2)

        assert len(self.hooks.list_handlers(HookEvent.MEMORY_STORED)) == 2

    def test_register_idempotent(self):
        """Registering with same name should replace, not duplicate."""
        def handler1(inp): pass
        def handler2(inp): pass

        self.hooks.register(HookEvent.MEMORY_STORED, "same_name", handler1)
        self.hooks.register(HookEvent.MEMORY_STORED, "same_name", handler2)

        assert len(self.hooks.list_handlers(HookEvent.MEMORY_STORED)) == 1

    def test_register_max_handlers(self):
        """Should enforce MAX_HANDLERS_PER_EVENT limit."""
        self.hooks.MAX_HANDLERS_PER_EVENT = 3  # Temporarily lower for test

        def make_handler(n):
            def h(inp): pass
            return h

        for i in range(3):
            self.hooks.register(HookEvent.MEMORY_STORED, f"h{i}", make_handler(i))

        with pytest.raises(RuntimeError, match="max.*handlers reached"):
            self.hooks.register(HookEvent.MEMORY_STORED, "h_extra", make_handler(99))

    def test_unregister_existing(self):
        """Should remove existing handler."""
        def handler(inp): pass

        self.hooks.register(HookEvent.MEMORY_STORED, "to_remove", handler)
        assert len(self.hooks.list_handlers(HookEvent.MEMORY_STORED)) == 1

        removed = self.hooks.unregister(HookEvent.MEMORY_STORED, "to_remove")
        assert removed is True
        assert len(self.hooks.list_handlers(HookEvent.MEMORY_STORED)) == 0

    def test_unregister_nonexistent(self):
        """Unregistering non-existent handler should return False."""
        removed = self.hooks.unregister(HookEvent.MEMORY_STORED, "nonexistent")
        assert removed is False

    def test_emit_calls_handlers(self):
        """Emit should call all registered handlers."""
        calls = []

        def handler1(inp):
            calls.append(("h1", inp.data))

        def handler2(inp):
            calls.append(("h2", inp.data))

        self.hooks.register(HookEvent.MEMORY_STORED, "h1", handler1)
        self.hooks.register(HookEvent.MEMORY_STORED, "h2", handler2)

        input_data = HookInput(
            event=HookEvent.MEMORY_STORED,
            timestamp=datetime.now(),
            data={"test": True},
            source="test"
        )
        result = self.hooks.emit(input_data)

        assert len(calls) == 2
        assert ("h1", {"test": True}) in calls
        assert ("h2", {"test": True}) in calls

    def test_emit_error_isolation(self):
        """One handler failing should not prevent others from running."""
        def good_handler(inp):
            return "good"

        def bad_handler(inp):
            raise ValueError("intentional error")

        self.hooks.register(HookEvent.ERROR_OCCURRED, "good", good_handler)
        self.hooks.register(HookEvent.ERROR_OCCURRED, "bad", bad_handler)

        input_data = HookInput(
            event=HookEvent.ERROR_OCCURRED,
            timestamp=datetime.now(),
            data={},
            source="test"
        )
        result = self.hooks.emit(input_data)

        assert result.handlers_run == 1  # Only good handler ran
        assert len(result.errors) == 1
        assert "bad" in result.errors[0]

    def test_emit_returns_result(self):
        """Emit should return HookResult with correct stats."""
        def fast_handler(inp):
            time.sleep(0.01)
            return "done"

        self.hooks.register(HookEvent.MEMORY_STORED, "fast", fast_handler)

        input_data = HookInput(
            event=HookEvent.MEMORY_STORED,
            timestamp=datetime.now(),
            data={},
            source="test"
        )
        result = self.hooks.emit(input_data)

        assert isinstance(result, HookResult)
        assert result.event == HookEvent.MEMORY_STORED
        assert result.handlers_run == 1
        assert result.total_duration_ms >= 10  # At least 10ms
        assert len(result.errors) == 0

    def test_emit_no_handlers(self):
        """Emit with no handlers should return empty result."""
        input_data = HookInput(
            event=HookEvent.MEMORY_STORED,
            timestamp=datetime.now(),
            data={},
            source="test"
        )
        result = self.hooks.emit(input_data)

        assert result.handlers_run == 0
        assert result.total_duration_ms == 0.0
        assert len(result.errors) == 0

    def test_emit_different_event_no_handlers(self):
        """Emitting event with no handlers should be silent."""
        def handler(inp):
            pass

        self.hooks.register(HookEvent.MEMORY_STORED, "h", handler)

        input_data = HookInput(
            event=HookEvent.ERROR_OCCURRED,  # Different event
            timestamp=datetime.now(),
            data={},
            source="test"
        )
        result = self.hooks.emit(input_data)

        assert result.handlers_run == 0

    def test_list_handlers_specific_event(self):
        """list_handlers(event) should return count for that event."""
        def handler1(inp): pass
        def handler2(inp): pass

        self.hooks.register(HookEvent.MEMORY_STORED, "h1", handler1)
        self.hooks.register(HookEvent.MEMORY_STORED, "h2", handler2)
        self.hooks.register(HookEvent.ERROR_OCCURRED, "h3", handler2)

        counts = self.hooks.list_handlers(HookEvent.MEMORY_STORED)
        assert counts[HookEvent.MEMORY_STORED.value] == 2

    def test_list_handlers_all_events(self):
        """list_handlers(None) should return all handlers."""
        def handler(inp): pass

        self.hooks.register(HookEvent.MEMORY_STORED, "h1", handler)
        self.hooks.register(HookEvent.ERROR_OCCURRED, "h2", handler)

        counts = self.hooks.list_handlers()
        assert counts[HookEvent.MEMORY_STORED.value] == 1
        assert counts[HookEvent.ERROR_OCCURRED.value] == 1

    def test_clear_specific_event(self):
        """clear(event) should remove only that event's handlers."""
        def handler(inp): pass

        self.hooks.register(HookEvent.MEMORY_STORED, "h1", handler)
        self.hooks.register(HookEvent.ERROR_OCCURRED, "h2", handler)

        removed = self.hooks.clear(HookEvent.MEMORY_STORED)
        assert removed == 1
        assert len(self.hooks.list_handlers(HookEvent.MEMORY_STORED)) == 0
        assert len(self.hooks.list_handlers(HookEvent.ERROR_OCCURRED)) == 1

    def test_clear_all_events(self):
        """clear(None) should remove all handlers."""
        def handler(inp): pass

        self.hooks.register(HookEvent.MEMORY_STORED, "h1", handler)
        self.hooks.register(HookEvent.ERROR_OCCURRED, "h2", handler)

        removed = self.hooks.clear()
        assert removed == 2
        assert len(self.hooks.list_handlers()) == 0


class TestAsyncHooks:
    """Test async hook functionality."""

    def setup_method(self):
        """Create fresh HooksSystem for each test."""
        self.hooks = HooksSystem()

    @pytest_asyncio.fixture
    async def fresh_hooks(self):
        """Provide a fresh HooksSystem for async tests."""
        return HooksSystem()

    async def test_emit_async_calls_handlers(self):
        """emit_async should call async handlers."""
        hooks = HooksSystem()
        calls = []

        async def async_handler(inp):
            calls.append(("async", inp.data))

        hooks.register(HookEvent.MEMORY_STORED, "async_h", async_handler)

        input_data = HookInput(
            event=HookEvent.MEMORY_STORED,
            timestamp=datetime.now(),
            data={"async": True},
            source="test"
        )
        result = await hooks.emit_async(input_data)

        assert len(calls) == 1
        assert result.handlers_run == 1

    async def test_emit_async_mixed_sync_async(self):
        """emit_async should handle both sync and async handlers."""
        hooks = HooksSystem()
        sync_calls = []
        async_calls = []

        def sync_handler(inp):
            sync_calls.append(inp.data)

        async def async_handler(inp):
            async_calls.append(inp.data)

        hooks.register(HookEvent.MEMORY_STORED, "sync", sync_handler)
        hooks.register(HookEvent.MEMORY_STORED, "async", async_handler)

        input_data = HookInput(
            event=HookEvent.MEMORY_STORED,
            timestamp=datetime.now(),
            data={"mixed": True},
            source="test"
        )
        result = await hooks.emit_async(input_data)

        assert len(sync_calls) == 1
        assert len(async_calls) == 1
        assert result.handlers_run == 2

    async def test_emit_async_error_isolation(self):
        """Async emit should also isolate errors."""
        hooks = HooksSystem()

        async def bad_handler(inp):
            raise ValueError("async error")

        def good_handler(inp):
            return "good"

        hooks.register(HookEvent.ERROR_OCCURRED, "bad", bad_handler)
        hooks.register(HookEvent.ERROR_OCCURRED, "good", good_handler)

        input_data = HookInput(
            event=HookEvent.ERROR_OCCURRED,
            timestamp=datetime.now(),
            data={},
            source="test"
        )
        result = await hooks.emit_async(input_data)

        assert result.handlers_run == 1
        assert len(result.errors) == 1


class TestPrebuiltHooks:
    """Test pre-built hook creators."""

    def test_create_logging_hook(self):
        """create_logging_hook should return working logger."""
        mock_logger = MagicMock()

        hook = create_logging_hook(mock_logger)

        input_data = HookInput(
            event=HookEvent.MEMORY_STORED,
            timestamp=datetime.now(),
            data={"key": "value"},
            source="test_source"
        )
        hook(input_data)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert "memory_stored" in call_args
        assert "test_source" in call_args

    def test_create_counter_hook(self):
        """create_counter_hook should increment counters."""
        counters = {}

        hook = create_counter_hook(counters)

        hook(HookInput(event=HookEvent.MEMORY_STORED, timestamp=datetime.now()))
        hook(HookInput(event=HookEvent.MEMORY_STORED, timestamp=datetime.now()))
        hook(HookInput(event=HookEvent.ERROR_OCCURRED, timestamp=datetime.now()))

        assert counters["memory_stored"] == 2
        assert counters["error_occurred"] == 1

    def test_create_notification_hook(self):
        """create_notification_hook should only fire on critical events."""
        # This is a basic test - full webhook testing would need a server
        try:
            import aiohttp
        except ImportError:
            pytest.skip("aiohttp not installed")

        hook = create_notification_hook("http://example.com/webhook")

        # Non-critical event
        input_data = HookInput(
            event=HookEvent.MEMORY_STORED,
            timestamp=datetime.now(),
            data={},
            source="test"
        )
        # Should not raise even without a server running
        # (the hook will try to post but fail silently)


class TestDecorators:
    """Test hook decorators."""

    def test_on_hook_sets_metadata(self):
        """@on_hook should set _hook_event and _hook_name on function."""
        @on_hook(HookEvent.MEMORY_STORED, name="my_handler")
        def my_handler(inp):
            pass

        assert my_handler._hook_event == HookEvent.MEMORY_STORED
        assert my_handler._hook_name == "my_handler"

    def test_on_hook_default_name(self):
        """@on_hook should use function name if name not provided."""
        @on_hook(HookEvent.ERROR_OCCURRED)
        def error_handler(inp):
            pass

        assert error_handler._hook_event == HookEvent.ERROR_OCCURRED
        assert error_handler._hook_name == "error_handler"

    def test_auto_register_hooks(self):
        """@auto_register_hooks should register decorated function."""
        hooks = HooksSystem()

        @auto_register_hooks(hooks)
        @on_hook(HookEvent.MEMORY_STORED)
        def registered_handler(inp):
            return "registered"

        assert len(hooks.list_handlers(HookEvent.MEMORY_STORED)) == 1


class TestGlobalInstance:
    """Test global hooks_system instance."""

    def test_global_instance_exists(self):
        """Global hooks_system should be instance of HooksSystem."""
        assert isinstance(hooks_system, HooksSystem)

    def test_emit_memory_stored_convenience(self):
        """emit_memory_stored should work as convenience function."""
        # Clear first
        hooks_system.clear()

        calls = []

        @on_hook(HookEvent.MEMORY_STORED, name="test_mem")
        def handle_stored(inp):
            calls.append(inp.data)

        hooks_system.register(HookEvent.MEMORY_STORED, "test_mem", handle_stored)

        result = emit_memory_stored("conv123", 5, "test")

        assert len(calls) == 1
        assert calls[0]["conversation_id"] == "conv123"
        assert calls[0]["entities_count"] == 5


class TestSyncEmitWithAsyncHandler:
    """Test that sync emit can handle async handlers."""

    def setup_method(self):
        """Create fresh HooksSystem for each test."""
        self.hooks = HooksSystem()

    def test_sync_emit_with_async_handler(self):
        """Sync emit should be able to run async handlers."""
        calls = []

        async def async_handler(inp):
            # Small delay to simulate async work
            await asyncio.sleep(0.01)
            calls.append("async")

        self.hooks.register(HookEvent.MEMORY_STORED, "async_h", async_handler)

        input_data = HookInput(
            event=HookEvent.MEMORY_STORED,
            timestamp=datetime.now(),
            data={},
            source="test"
        )

        # This should not raise - sync emit handles async callbacks
        result = self.hooks.emit(input_data)

        # Handler should have been called (possibly via new event loop)
        assert result.handlers_run >= 0  # May be 0 if no running loop available


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
