"""Tests for the ALS pool functionality."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ada_mcp.server import ALSInstance, ALSPool


class TestALSInstance:
    """Tests for ALSInstance dataclass."""

    def test_instance_creation(self):
        """Test creating an ALS instance."""
        mock_client = MagicMock()
        mock_monitor = MagicMock()
        project_root = Path("/test/project")

        instance = ALSInstance(
            client=mock_client,
            monitor=mock_monitor,
            project_root=project_root,
            last_used=12345.0,
            lock=asyncio.Lock(),
        )

        assert instance.client is mock_client
        assert instance.monitor is mock_monitor
        assert instance.project_root == project_root
        assert instance.last_used == 12345.0


class TestALSPool:
    """Tests for ALSPool class."""

    def test_pool_creation(self):
        """Test creating a pool with default settings."""
        pool = ALSPool()
        assert pool.max_instances == 3
        assert pool.idle_timeout == 300.0
        assert len(pool._instances) == 0

    def test_pool_custom_settings(self):
        """Test creating a pool with custom settings."""
        pool = ALSPool(max_instances=5, idle_timeout=600.0)
        assert pool.max_instances == 5
        assert pool.idle_timeout == 600.0

    def test_get_stats_empty(self):
        """Test stats on empty pool."""
        pool = ALSPool()
        stats = pool.get_stats()
        assert stats["active_instances"] == 0
        assert stats["max_instances"] == 3
        assert stats["projects"] == []

    @pytest.mark.asyncio
    async def test_get_client_creates_instance(self):
        """Test that get_client creates a new ALS instance."""
        pool = ALSPool()

        mock_client = MagicMock()
        mock_client.is_running = True
        mock_monitor = MagicMock()

        with (
            patch(
                "ada_mcp.server.start_als_with_monitoring",
                new_callable=AsyncMock,
                return_value=(mock_client, mock_monitor),
            ),
            patch(
                "ada_mcp.server.find_project_root",
                return_value=Path("/test/project"),
            ),
        ):
            client = await pool.get_client("/test/project/src/main.adb")

            assert client is mock_client
            assert len(pool._instances) == 1
            assert Path("/test/project") in pool._instances

    @pytest.mark.asyncio
    async def test_get_client_reuses_instance(self):
        """Test that get_client reuses existing instances."""
        pool = ALSPool()

        mock_client = MagicMock()
        mock_client.is_running = True
        mock_monitor = MagicMock()

        with (
            patch(
                "ada_mcp.server.start_als_with_monitoring",
                new_callable=AsyncMock,
                return_value=(mock_client, mock_monitor),
            ) as mock_start,
            patch(
                "ada_mcp.server.find_project_root",
                return_value=Path("/test/project"),
            ),
        ):
            # First call creates instance
            client1 = await pool.get_client("/test/project/src/main.adb")
            # Second call should reuse
            client2 = await pool.get_client("/test/project/src/utils.ads")

            assert client1 is client2
            # start_als_with_monitoring should only be called once
            assert mock_start.call_count == 1

    @pytest.mark.asyncio
    async def test_get_client_different_projects(self):
        """Test that different projects get different instances."""
        pool = ALSPool()

        mock_client1 = MagicMock()
        mock_client1.is_running = True
        mock_client2 = MagicMock()
        mock_client2.is_running = True
        mock_monitor = MagicMock()

        call_count = 0

        async def mock_start(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (mock_client1, mock_monitor)
            return (mock_client2, mock_monitor)

        with (
            patch(
                "ada_mcp.server.start_als_with_monitoring",
                side_effect=mock_start,
            ),
            patch(
                "ada_mcp.server.find_project_root",
                side_effect=lambda p: Path(str(p).rsplit("/src", 1)[0]),
            ),
        ):
            client1 = await pool.get_client("/project1/src/main.adb")
            client2 = await pool.get_client("/project2/src/main.adb")

            assert client1 is not client2
            assert len(pool._instances) == 2

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        """Test that LRU eviction works when pool is full."""
        pool = ALSPool(max_instances=2)

        clients = [MagicMock() for _ in range(3)]
        for c in clients:
            c.is_running = True
        mock_monitor = MagicMock()

        call_count = 0

        async def mock_start(*args, **kwargs):
            nonlocal call_count
            result = (clients[call_count], mock_monitor)
            call_count += 1
            return result

        with (
            patch(
                "ada_mcp.server.start_als_with_monitoring",
                side_effect=mock_start,
            ),
            patch(
                "ada_mcp.server.find_project_root",
                side_effect=lambda p: Path(str(p).rsplit("/src", 1)[0]),
            ),
            patch(
                "ada_mcp.server.shutdown_als",
                new_callable=AsyncMock,
            ) as mock_shutdown,
        ):
            # Fill the pool
            await pool.get_client("/project1/src/main.adb")
            await pool.get_client("/project2/src/main.adb")

            assert len(pool._instances) == 2

            # Add a third - should evict oldest
            await pool.get_client("/project3/src/main.adb")

            # Should still have only 2 instances
            assert len(pool._instances) == 2
            # Shutdown should have been called for eviction
            assert mock_shutdown.called

    @pytest.mark.asyncio
    async def test_shutdown_all(self):
        """Test shutting down all instances."""
        pool = ALSPool()

        mock_client = MagicMock()
        mock_client.is_running = True
        mock_monitor = MagicMock()

        with (
            patch(
                "ada_mcp.server.start_als_with_monitoring",
                new_callable=AsyncMock,
                return_value=(mock_client, mock_monitor),
            ),
            patch(
                "ada_mcp.server.find_project_root",
                return_value=Path("/test/project"),
            ),
            patch(
                "ada_mcp.server.shutdown_als",
                new_callable=AsyncMock,
            ) as mock_shutdown,
        ):
            await pool.get_client("/test/project/src/main.adb")
            assert len(pool._instances) == 1

            await pool.shutdown_all()

            assert len(pool._instances) == 0
            assert mock_shutdown.called

    @pytest.mark.asyncio
    async def test_dead_instance_removed(self):
        """Test that dead instances are removed and recreated."""
        pool = ALSPool()

        mock_client1 = MagicMock()
        mock_client1.is_running = True
        mock_client2 = MagicMock()
        mock_client2.is_running = True
        mock_monitor = MagicMock()

        call_count = 0

        async def mock_start(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (mock_client1, mock_monitor)
            return (mock_client2, mock_monitor)

        with (
            patch(
                "ada_mcp.server.start_als_with_monitoring",
                side_effect=mock_start,
            ),
            patch(
                "ada_mcp.server.find_project_root",
                return_value=Path("/test/project"),
            ),
        ):
            # First call creates instance
            client1 = await pool.get_client("/test/project/src/main.adb")
            assert client1 is mock_client1

            # Simulate client dying
            mock_client1.is_running = False

            # Next call should create new instance
            client2 = await pool.get_client("/test/project/src/main.adb")
            assert client2 is mock_client2
            assert call_count == 2
