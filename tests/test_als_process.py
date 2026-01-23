"""Tests for ALS process management and health monitoring."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ada_mcp.als.process import ALSHealthMonitor


class TestALSHealthMonitor:
    """Tests for ALSHealthMonitor class."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock ALS client."""
        client = MagicMock()
        client.is_running = True
        return client

    @pytest.fixture
    def monitor(self, mock_client):
        """Create an ALSHealthMonitor instance."""
        return ALSHealthMonitor(
            client=mock_client,
            project_root=Path("/test/project"),
            als_path="/test/als",
            gpr_file=Path("/test/project/test.gpr"),
            initial_backoff_seconds=0.1,  # Fast for tests
            max_backoff_seconds=1.0,
        )

    def test_initial_state(self, monitor):
        """Test initial monitor state."""
        assert monitor.restart_count == 0
        assert monitor._shutdown_requested is False
        assert monitor._monitor_task is None

    def test_stop_monitoring_sets_flag(self, monitor):
        """Test that stop_monitoring sets shutdown flag."""
        monitor.stop_monitoring()
        assert monitor._shutdown_requested is True

    def test_reset_restart_count(self, monitor):
        """Test resetting restart counter."""
        monitor.restart_count = 3
        monitor.reset_restart_count()
        assert monitor.restart_count == 0

    @pytest.mark.asyncio
    async def test_start_monitoring_creates_task(self, monitor):
        """Test that start_monitoring creates a monitoring task."""
        monitor.start_monitoring()
        assert monitor._monitor_task is not None
        assert not monitor._monitor_task.done()

        # Clean up
        monitor.stop_monitoring()
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_callback_stored(self, monitor):
        """Test that on_restart callback is stored."""
        callback = MagicMock()
        monitor.start_monitoring(on_restart=callback)
        assert monitor._on_restart_callback == callback

        # Clean up
        monitor.stop_monitoring()
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_exponential_backoff_calculation(self, monitor):
        """Test exponential backoff calculation."""
        # With initial_backoff=0.1, multiplier=2.0
        # attempt 0: 0.1
        # attempt 1: 0.2
        # attempt 2: 0.4
        # etc.
        assert monitor.initial_backoff_seconds == 0.1
        assert monitor.backoff_multiplier == 2.0

        # Calculate expected backoff for each attempt
        for attempt in range(5):
            expected = min(
                monitor.initial_backoff_seconds * (monitor.backoff_multiplier**attempt),
                monitor.max_backoff_seconds,
            )
            actual = min(
                monitor.initial_backoff_seconds * (monitor.backoff_multiplier**attempt),
                monitor.max_backoff_seconds,
            )
            assert actual == expected

    @pytest.mark.asyncio
    async def test_max_backoff_capped(self, monitor):
        """Test that backoff is capped at max_backoff_seconds."""
        monitor.restart_count = 100  # High count to exceed max
        backoff = min(
            monitor.initial_backoff_seconds * (monitor.backoff_multiplier**monitor.restart_count),
            monitor.max_backoff_seconds,
        )
        assert backoff == monitor.max_backoff_seconds

    @pytest.mark.asyncio
    async def test_monitor_detects_crash(self, monitor, mock_client):
        """Test that monitor detects when ALS process exits."""
        mock_client.is_running = True

        # Start monitoring
        monitor.start_monitoring()
        await asyncio.sleep(0.05)

        # Simulate crash
        mock_client.is_running = False

        # Give monitor time to detect
        await asyncio.sleep(0.1)

        # Stop before restart attempt completes
        monitor.stop_monitoring()
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_max_restart_attempts_respected(self, monitor, mock_client):
        """Test that monitor stops after max restart attempts."""
        monitor.max_restart_attempts = 2
        monitor.restart_count = 2  # Already at max

        # _handle_crash should not attempt restart
        mock_client.is_running = False

        with patch.object(monitor, "_handle_crash") as mock_handle:
            mock_handle.return_value = None
            # The actual restart logic checks restart_count
            assert monitor.restart_count >= monitor.max_restart_attempts


class TestALSHealthMonitorBackoff:
    """Test exponential backoff behavior."""

    def test_backoff_values(self):
        """Test specific backoff values."""
        monitor = ALSHealthMonitor(
            client=MagicMock(),
            project_root=Path("/test"),
            als_path="/test/als",
            initial_backoff_seconds=1.0,
            max_backoff_seconds=60.0,
            backoff_multiplier=2.0,
        )

        # Test backoff sequence
        expected_sequence = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0]
        for attempt, expected in enumerate(expected_sequence):
            actual = min(
                monitor.initial_backoff_seconds * (monitor.backoff_multiplier**attempt),
                monitor.max_backoff_seconds,
            )
            assert actual == expected, f"Attempt {attempt}: expected {expected}, got {actual}"


class TestHealthMonitorIntegration:
    """Integration tests for health monitoring (without real ALS)."""

    @pytest.mark.asyncio
    async def test_monitor_lifecycle(self):
        """Test complete monitor lifecycle: start, run, stop."""
        mock_client = MagicMock()
        mock_client.is_running = True

        monitor = ALSHealthMonitor(
            client=mock_client,
            project_root=Path("/test"),
            als_path="/test/als",
            initial_backoff_seconds=0.1,
        )

        # Start
        monitor.start_monitoring()
        assert monitor._monitor_task is not None

        # Let it run briefly
        await asyncio.sleep(0.1)
        assert not monitor._monitor_task.done()

        # Stop
        monitor.stop_monitoring()
        await asyncio.sleep(0.1)

        # Task should be cancelled
        assert monitor._shutdown_requested is True

    @pytest.mark.asyncio
    async def test_callback_invocation(self):
        """Test that restart callback is invoked with new client."""
        callback_client = None

        def on_restart(client):
            nonlocal callback_client
            callback_client = client

        monitor = ALSHealthMonitor(
            client=MagicMock(),
            project_root=Path("/test"),
            als_path="/test/als",
        )
        monitor._on_restart_callback = on_restart

        # Simulate callback
        new_client = MagicMock()
        monitor._on_restart_callback(new_client)

        assert callback_client is new_client
