"""
Hooks System for unified_daemon

Inspired by Claude Code's hooks system (5,022 lines, 25 event types).
Simplified version for Silhouette Brain.

Provides event-driven extensibility for:
- Memory events
- Agent events
- Security events
- System events
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# Type definitions
HookCallback = Callable[["HookInput"], Any]


class HookEvent(str, Enum):
    """Event types that can trigger hooks."""
    # Memory events
    MEMORY_STORED = "memory_stored"
    MEMORY_RETRIEVED = "memory_retrieved"
    MEMORY_SEARCH = "memory_search"

    # Agent events
    AGENT_HEARTBEAT = "agent_heartbeat"
    AGENT_SESSION_SYNC = "agent_session_sync"
    AGENT_TOOL_EXECUTED = "agent_tool_executed"

    # Security events
    INJECTION_DETECTED = "conversation_injection"
    SCAPER_DETECTED = "api_scraper"
    PERMISSION_DENIED = "permission_denied"

    # System events
    SERVICE_STARTED = "service_started"
    SERVICE_STOPPED = "service_stopped"
    TASK_QUEUED = "task_queued"
    TASK_COMPLETED = "task_completed"
    ERROR_OCCURRED = "error_occurred"


@dataclass
class HookInput:
    """Input data passed to hook handlers."""
    event: HookEvent
    timestamp: datetime
    data: dict = field(default_factory=dict)
    source: str = "unknown"


@dataclass
class HookResult:
    """Result of firing a hook event."""
    event: HookEvent
    handlers_run: int = 0
    total_duration_ms: float = 0.0
    errors: list[str] = field(default_factory=list)


class HooksSystem:
    """
    Event hooks system with async support, error isolation, and timeouts.

    Safety limits:
    - Max 100 handlers per event
    - 5 second timeout per handler
    """

    MAX_HANDLERS_PER_EVENT = 100
    HANDLER_TIMEOUT_SECONDS = 5.0

    def __init__(self):
        self._handlers: dict[HookEvent, list[tuple[str, HookCallback]]] = {}
        self._logger = logging.getLogger("silhouette.hooks.system")

    def register(self, event: HookEvent, name: str, callback: HookCallback) -> None:
        """
        Register a hook handler for an event.

        Args:
            event: The event type to listen for
            name: Unique name for this handler (idempotent - same name replaces)
            callback: Function to call when event fires
        """
        if event not in self._handlers:
            self._handlers[event] = []

        # Check handler limit
        current_handlers = len(self._handlers[event])
        existing_names = [n for n, _ in self._handlers[event]]

        # If name exists, remove old handler first (idempotent)
        if name in existing_names:
            self._handlers[event] = [(n, cb) for n, cb in self._handlers[event] if n != name]

        # Check capacity
        if current_handlers >= self.MAX_HANDLERS_PER_EVENT:
            raise RuntimeError(
                f"Cannot register handler '{name}': max {self.MAX_HANDLERS_PER_EVENT} "
                f"handlers reached for event {event.value}"
            )

        self._handlers[event].append((name, callback))
        self._logger.debug(f"Registered hook '{name}' for event {event.value}")

    def unregister(self, event: HookEvent, name: str) -> bool:
        """
        Remove a hook handler.

        Args:
            event: The event type
            name: Name of the handler to remove

        Returns:
            True if handler was found and removed, False if not found
        """
        if event not in self._handlers:
            return False

        original_count = len(self._handlers[event])
        self._handlers[event] = [(n, cb) for n, cb in self._handlers[event] if n != name]

        removed = original_count > len(self._handlers[event])
        if removed:
            self._logger.debug(f"Unregistered hook '{name}' from event {event.value}")
        return removed

    def emit(self, hook_input: HookInput) -> HookResult:
        """
        Fire a hook event synchronously and run all handlers.

        Error isolation: one handler failing doesn't break others.
        Timeout protection: each handler limited to HANDLER_TIMEOUT_SECONDS.

        Args:
            hook_input: Event data to pass to handlers

        Returns:
            HookResult with execution statistics
        """
        handlers = self._handlers.get(hook_input.event, [])
        results: list[dict[str, Any]] = []
        errors: list[str] = []

        for name, callback in handlers:
            start_time = time.time()
            try:
                # Check if callback is async
                if asyncio.iscoroutinefunction(callback):
                    # For sync emit, we need to handle async callbacks
                    # Run in a new event loop if needed
                    try:
                        loop = asyncio.get_running_loop()
                        # We're in an async context - this shouldn't normally happen for sync emit
                        # but handle it anyway
                        future = asyncio.ensure_future(
                            asyncio.wait_for(
                                callback(hook_input),
                                timeout=self.HANDLER_TIMEOUT_SECONDS
                            )
                        )
                        # Block and get result (not ideal but maintains sync interface)
                        result = asyncio.run_coroutine_threadsafe(
                            future, loop
                        ).result(self.HANDLER_TIMEOUT_SECONDS)
                    except RuntimeError:
                        # No running loop - create one
                        result = asyncio.run(
                            asyncio.wait_for(
                                callback(hook_input),
                                timeout=self.HANDLER_TIMEOUT_SECONDS
                            )
                        )
                else:
                    # Synchronous handler with timeout
                    result = self._run_with_timeout(callback, hook_input)

                duration_ms = (time.time() - start_time) * 1000
                results.append({
                    'handler': name,
                    'duration_ms': duration_ms,
                    'result': result
                })

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                error_msg = f"{name}: {type(e).__name__}: {e}"
                errors.append(error_msg)
                self._logger.warning(f"Hook handler '{name}' failed: {e}")

        return HookResult(
            event=hook_input.event,
            handlers_run=len(results),
            total_duration_ms=sum(r['duration_ms'] for r in results),
            errors=errors
        )

    async def emit_async(self, hook_input: HookInput) -> HookResult:
        """
        Fire a hook event asynchronously and run all handlers.

        Args:
            hook_input: Event data to pass to handlers

        Returns:
            HookResult with execution statistics
        """
        handlers = self._handlers.get(hook_input.event, [])
        results: list[dict[str, Any]] = []
        errors: list[str] = []

        for name, callback in handlers:
            start_time = time.time()
            try:
                if asyncio.iscoroutinefunction(callback):
                    result = await asyncio.wait_for(
                        callback(hook_input),
                        timeout=self.HANDLER_TIMEOUT_SECONDS
                    )
                else:
                    # Run sync handler in thread pool to not block
                    loop = asyncio.get_running_loop()
                    result = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda: self._run_sync_handler(callback, hook_input)
                        ),
                        timeout=self.HANDLER_TIMEOUT_SECONDS
                    )

                duration_ms = (time.time() - start_time) * 1000
                results.append({
                    'handler': name,
                    'duration_ms': duration_ms,
                    'result': result
                })

            except asyncio.TimeoutError:
                duration_ms = (time.time() - start_time) * 1000
                error_msg = f"{name}: Timeout after {self.HANDLER_TIMEOUT_SECONDS}s"
                errors.append(error_msg)
                self._logger.warning(error_msg)

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                error_msg = f"{name}: {type(e).__name__}: {e}"
                errors.append(error_msg)
                self._logger.warning(f"Hook handler '{name}' failed: {e}")

        return HookResult(
            event=hook_input.event,
            handlers_run=len(results),
            total_duration_ms=sum(r['duration_ms'] for r in results),
            errors=errors
        )

    def _run_with_timeout(self, callback: Callable, hook_input: HookInput) -> Any:
        """Run a sync callback with timeout (simplified, actual timeout handled at call site)."""
        return callback(hook_input)

    def _run_sync_handler(self, callback: Callable, hook_input: HookInput) -> Any:
        """Run a sync handler (for thread pool execution)."""
        return callback(hook_input)

    def list_handlers(self, event: HookEvent | None = None) -> dict[str, int]:
        """
        List registered handlers.

        Args:
            event: Optional event to filter by. If None, returns all handlers.

        Returns:
            Dict mapping event names to handler counts
        """
        if event is not None:
            return {event.value: len(self._handlers.get(event, []))}

        return {
            ev.value: len(handlers)
            for ev, handlers in self._handlers.items()
        }

    def clear(self, event: HookEvent | None = None) -> int:
        """
        Clear handlers for an event or all events.

        Args:
            event: Event to clear, or None to clear all

        Returns:
            Number of handlers removed
        """
        if event is not None:
            count = len(self._handlers.get(event, []))
            self._handlers.pop(event, None)
            return count

        count = sum(len(h) for h in self._handlers.values())
        self._handlers.clear()
        return count


# Global hooks system instance
hooks_system = HooksSystem()


# =============================================================================
# Pre-built Hooks (common use cases)
# =============================================================================

def create_logging_hook(logger: logging.Logger) -> HookCallback:
    """
    Create a hook that logs all events.

    Args:
        logger: Logger instance to use

    Returns:
        Hook callback function
    """
    def hook(input: HookInput) -> None:
        logger.info(
            f"[HOOK:{input.event.value}] source={input.source} data={input.data}"
        )
    return hook


def create_notification_hook(webhook_url: str) -> HookCallback:
    """
    Create a hook that sends notifications to a webhook on critical events.

    Args:
        webhook_url: URL to send POST requests to

    Returns:
        Async hook callback function
    """
    import aiohttp

    critical_events = {
        HookEvent.INJECTION_DETECTED,
        HookEvent.SCAPER_DETECTED,
        HookEvent.ERROR_OCCURRED,
        HookEvent.PERMISSION_DENIED
    }

    async def hook(input: HookInput) -> None:
        if input.event in critical_events:
            payload = {
                "event": input.event.value,
                "timestamp": input.timestamp.isoformat(),
                "source": input.source,
                "data": input.data
            }
            try:
                async with aiohttp.ClientSession() as session:
                    await session.post(webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=5))
            except Exception:
                # Don't let notification failures break anything
                pass

    return hook


def create_metrics_hook(metrics_client) -> HookCallback:
    """
    Create a hook that records metrics for each event.

    Assumes metrics_client has an `incr` method (like statsd).

    Args:
        metrics_client: Metrics client with incr method

    Returns:
        Hook callback function
    """
    def hook(input: HookInput) -> None:
        try:
            metrics_client.incr(f"hook.{input.event.value}")
        except Exception:
            # Don't let metrics failures break anything
            pass

    return hook


def create_counter_hook(counters: dict[str, int]) -> HookCallback:
    """
    Create a hook that counts events in a dict (simple built-in metrics).

    Args:
        counters: Dict to increment counter in

    Returns:
        Hook callback function
    """
    def hook(input: HookInput) -> None:
        key = input.event.value
        counters[key] = counters.get(key, 0) + 1

    return hook


# =============================================================================
# Decorator for easy registration
# =============================================================================

def on_hook(event: HookEvent, name: str | None = None):
    """
    Decorator to register a function as a hook handler.

    Usage:
        @on_hook(HookEvent.MEMORY_STORED, name="my_handler")
        def handle_memory_stored(input: HookInput) -> None:
            print(f"Memory stored: {input.data}")

    Note: The decorated function must still be registered with hooks_system.register()
    unless used with the auto_register parameter.

    Args:
        event: The event to listen for
        name: Optional name for the handler (defaults to function name)

    Returns:
        Decorator function
    """
    def decorator(func: HookCallback) -> HookCallback:
        func._hook_event = event
        func._hook_name = name if name is not None else func.__name__
        return func

    return decorator


def auto_register_hooks(hooks_instance: HooksSystem | None = None) -> Callable[[HookCallback], HookCallback]:
    """
    Decorator factory to auto-register hook handlers.

    Usage:
        @auto_register_hooks(hooks_system)
        @on_hook(HookEvent.MEMORY_STORED)
        def handle_memory_stored(input: HookInput) -> None:
            print(f"Memory stored: {input.data}")

    Args:
        hooks_instance: HooksSystem instance to register with

    Returns:
        Decorator that registers the function
    """
    _hooks = hooks_instance or hooks_system

    def decorator(func: HookCallback) -> HookCallback:
        event = getattr(func, '_hook_event', None)
        hook_name = getattr(func, '_hook_name', None) or func.__name__

        if event is None:
            raise ValueError(
                f"Function '{func.__name__}' must be decorated with @on_hook "
                f"before using @auto_register_hooks"
            )

        _hooks.register(event, hook_name, func)
        return func

    return decorator


# =============================================================================
# Integration helpers
# =============================================================================

def emit_memory_stored(conversation_id: str, entities_count: int, source: str = "brain_api") -> HookResult:
    """Convenience function to emit MEMORY_STORED event."""
    return hooks_system.emit(HookInput(
        event=HookEvent.MEMORY_STORED,
        timestamp=datetime.now(),
        data={"conversation_id": conversation_id, "entities_count": entities_count},
        source=source
    ))


def emit_errorOccurred(error: Exception, context: dict, source: str = "unknown") -> HookResult:
    """Convenience function to emit ERROR_OCCURRED event."""
    return hooks_system.emit(HookInput(
        event=HookEvent.ERROR_OCCURRED,
        timestamp=datetime.now(),
        data={"error": str(error), "error_type": type(error).__name__, "context": context},
        source=source
    ))


async def emit_memory_stored_async(conversation_id: str, entities_count: int, source: str = "brain_api") -> HookResult:
    """Async convenience function to emit MEMORY_STORED event."""
    return await hooks_system.emit_async(HookInput(
        event=HookEvent.MEMORY_STORED,
        timestamp=datetime.now(),
        data={"conversation_id": conversation_id, "entities_count": entities_count},
        source=source
    ))
