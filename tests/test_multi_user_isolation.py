# -*- coding: utf-8 -*-
"""Multi-user isolation tests for CoPaw.

This module tests the request-scoped user isolation feature that allows
CoPaw to serve multiple users concurrently with full data isolation.

Tests are organized into three categories:
1. Unit Tests: Test context variables and directory accessors
2. Integration Tests: Test config isolation, session isolation, file operations
3. End-to-End Tests: Test full request lifecycle and concurrent scenarios
"""
import asyncio
import contextvars
import pytest
from pathlib import Path

# Import the functions we're testing
from copaw.constant import (
    DEFAULT_WORKING_DIR,
    DEFAULT_SECRET_DIR,
    set_request_user_id,
    reset_request_user_id,
    get_request_user_id,
    get_request_working_dir,
    get_request_secret_dir,
    get_active_skills_dir,
    get_customized_skills_dir,
    get_memory_dir,
    get_models_dir,
    get_custom_channels_dir,
    get_working_dir,
    get_secret_dir,
    set_current_user,
    get_runtime_working_dir,
)


@pytest.fixture(autouse=True)
def reset_all_context():
    """Reset all context vars before and after each test."""
    from copaw.constant import _request_working_dir, _request_secret_dir, _request_user_id

    # Reset to None at start of each test
    token_user = _request_user_id.set(None)
    token_wd = _request_working_dir.set(None)
    token_sd = _request_secret_dir.set(None)

    try:
        yield
    finally:
        # Always restore to clean state
        _request_user_id.reset(token_user)
        _request_working_dir.reset(token_wd)
        _request_secret_dir.reset(token_sd)


@pytest.fixture
def tmp_copaw_dirs(tmp_path, monkeypatch):
    """Create temporary copaw directories for testing.

    This fixture patches the DEFAULT_WORKING_DIR and DEFAULT_SECRET_DIR
    as well as the runtime variables. Note that because these are module-level
    variables, the patch only affects code that reads them after the patch.
    """
    working_dir = tmp_path / "copaw"
    secret_dir = tmp_path / "copaw.secret"
    working_dir.mkdir(parents=True, exist_ok=True)
    secret_dir.mkdir(parents=True, exist_ok=True)

    # Patch the module-level variables
    monkeypatch.setattr("copaw.constant.DEFAULT_WORKING_DIR", working_dir)
    monkeypatch.setattr("copaw.constant.DEFAULT_SECRET_DIR", secret_dir)
    monkeypatch.setattr("copaw.constant._runtime_working_dir", working_dir)
    monkeypatch.setattr("copaw.constant._runtime_secret_dir", secret_dir)

    yield working_dir, secret_dir


class TestContextVariablesIsolation:
    """Test context variable isolation for multi-user support."""

    def test_set_request_user_id_returns_token(self):
        """Test that setting user_id returns a valid token."""
        token = set_request_user_id("test_user")
        assert token is not None
        assert isinstance(token, contextvars.Token)
        reset_request_user_id(token)

    def test_reset_request_user_id_restores_context(self):
        """Test that resetting context restores previous state."""
        # Set initial state
        token1 = set_request_user_id("user1")
        assert get_request_user_id() == "user1"

        # Change to different user
        token2 = set_request_user_id("user2")
        assert get_request_user_id() == "user2"

        # Restore to user1
        reset_request_user_id(token2)
        assert get_request_user_id() == "user1"

        # Restore to initial state
        reset_request_user_id(token1)
        assert get_request_user_id() is None

    def test_get_request_user_id_without_context(self):
        """Test that get_request_user_id returns None without context."""
        assert get_request_user_id() is None

    def test_get_request_working_dir_without_context(self, tmp_copaw_dirs):
        """Test that get_request_working_dir falls back to runtime dir."""
        working_dir, _ = tmp_copaw_dirs

        # Without request context, should use runtime working dir
        result = get_request_working_dir()
        assert result == working_dir


class TestDirectoryAccessors:
    """Test directory accessor functions with user context."""

    def test_get_request_working_dir_with_user_context(self, tmp_copaw_dirs):
        """Test that get_request_working_dir returns correct directory."""
        working_dir, _ = tmp_copaw_dirs

        token = set_request_user_id("alice")
        try:
            result = get_request_working_dir()
            assert result == working_dir / "alice"
        finally:
            reset_request_user_id(token)

    def test_get_request_secret_dir_with_user_context(self, tmp_copaw_dirs):
        """Test that get_request_secret_dir returns correct directory."""
        _, secret_dir = tmp_copaw_dirs

        token = set_request_user_id("bob")
        try:
            result = get_request_secret_dir()
            assert result == secret_dir / "bob"
        finally:
            reset_request_user_id(token)

    def test_get_active_skills_dir_with_user_context(self, tmp_copaw_dirs):
        """Test that active skills directory is user-isolated."""
        working_dir, _ = tmp_copaw_dirs

        token = set_request_user_id("charlie")
        try:
            result = get_active_skills_dir()
            expected = working_dir / "charlie" / "active_skills"
            assert result == expected
        finally:
            reset_request_user_id(token)

    def test_get_customized_skills_dir_with_user_context(self, tmp_copaw_dirs):
        """Test that customized skills directory is user-isolated."""
        working_dir, _ = tmp_copaw_dirs

        token = set_request_user_id("david")
        try:
            result = get_customized_skills_dir()
            expected = working_dir / "david" / "customized_skills"
            assert result == expected
        finally:
            reset_request_user_id(token)

    def test_get_memory_dir_with_user_context(self, tmp_copaw_dirs):
        """Test that memory directory is user-isolated."""
        working_dir, _ = tmp_copaw_dirs

        token = set_request_user_id("eve")
        try:
            result = get_memory_dir()
            expected = working_dir / "eve" / "memory"
            assert result == expected
        finally:
            reset_request_user_id(token)

    def test_get_models_dir_with_user_context(self, tmp_copaw_dirs):
        """Test that models directory is user-isolated."""
        working_dir, _ = tmp_copaw_dirs

        token = set_request_user_id("frank")
        try:
            result = get_models_dir()
            expected = working_dir / "frank" / "models"
            assert result == expected
        finally:
            reset_request_user_id(token)

    def test_get_custom_channels_dir_with_user_context(self, tmp_copaw_dirs):
        """Test that custom channels directory is user-isolated."""
        working_dir, _ = tmp_copaw_dirs

        token = set_request_user_id("grace")
        try:
            result = get_custom_channels_dir()
            expected = working_dir / "grace" / "custom_channels"
            assert result == expected
        finally:
            reset_request_user_id(token)


class TestConcurrentIsolation:
    """Test concurrent request isolation."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_isolation(self, tmp_copaw_dirs):
        """Test that concurrent requests use different directories."""
        working_dir, _ = tmp_copaw_dirs

        results = {}

        async def handle_request(user_id: str):
            token = set_request_user_id(user_id)
            try:
                await asyncio.sleep(0.01)  # Simulate some async work
                results[user_id] = str(get_request_working_dir())
            finally:
                reset_request_user_id(token)

        # Run concurrent requests
        await asyncio.gather(
            handle_request("alice"),
            handle_request("bob"),
            handle_request("charlie"),
        )

        # Verify each request used correct directory
        assert results["alice"] == str(working_dir / "alice")
        assert results["bob"] == str(working_dir / "bob")
        assert results["charlie"] == str(working_dir / "charlie")

    @pytest.mark.asyncio
    async def test_many_concurrent_users_isolation(self, tmp_copaw_dirs):
        """Test isolation with 10+ concurrent users."""
        working_dir, _ = tmp_copaw_dirs

        user_ids = [f"user_{i}" for i in range(15)]
        results = {}

        async def handle_request(user_id: str):
            token = set_request_user_id(user_id)
            try:
                await asyncio.sleep(0.001)
                results[user_id] = get_request_working_dir()
            finally:
                reset_request_user_id(token)

        await asyncio.gather(*[handle_request(uid) for uid in user_ids])

        for user_id in user_ids:
            assert results[user_id] == working_dir / user_id

    @pytest.mark.asyncio
    async def test_context_not_leaked_between_requests(self, tmp_copaw_dirs):
        """Test that context is properly cleaned up between requests."""
        working_dir, _ = tmp_copaw_dirs

        async def handle_request_with_cleanup(user_id: str):
            token = set_request_user_id(user_id)
            try:
                return get_request_working_dir()
            finally:
                reset_request_user_id(token)

        # First request
        result1 = await handle_request_with_cleanup("user1")
        assert result1 == working_dir / "user1"

        # After cleanup, should return to default
        assert get_request_user_id() is None

        # Second request should not see first request's context
        result2 = await handle_request_with_cleanup("user2")
        assert result2 == working_dir / "user2"
        assert get_request_user_id() is None


class TestConfigIsolation:
    """Test configuration file isolation."""

    def test_get_config_path_with_user_id(self, tmp_copaw_dirs):
        """Test that config path is user-isolated."""
        from copaw.config.utils import get_config_path

        working_dir, _ = tmp_copaw_dirs

        # With explicit user_id
        result = get_config_path("alice")
        assert result == working_dir / "alice" / "config.json"

    def test_get_config_path_with_request_context(self, tmp_copaw_dirs):
        """Test that config path uses request context when user_id=None."""
        from copaw.config.utils import get_config_path

        working_dir, _ = tmp_copaw_dirs

        # With request context
        token = set_request_user_id("bob")
        try:
            result = get_config_path()
            assert result == working_dir / "bob" / "config.json"
        finally:
            reset_request_user_id(token)

    def test_get_providers_json_path_with_user_id(self, tmp_copaw_dirs):
        """Test that providers.json path is user-isolated."""
        from copaw.providers.store import get_providers_json_path

        _, secret_dir = tmp_copaw_dirs

        result = get_providers_json_path("alice")
        assert result == secret_dir / "alice" / "providers.json"

    def test_get_providers_json_path_with_request_context(self, tmp_copaw_dirs):
        """Test that providers.json path uses request context."""
        from copaw.providers.store import get_providers_json_path

        _, secret_dir = tmp_copaw_dirs

        token = set_request_user_id("bob")
        try:
            result = get_providers_json_path()
            assert result == secret_dir / "bob" / "providers.json"
        finally:
            reset_request_user_id(token)


class TestFileOperations:
    """Test file operation tools use correct user directories."""

    @pytest.mark.asyncio
    async def test_file_io_uses_user_directory(self, tmp_copaw_dirs):
        """Test that file read/write operations use user directory."""
        from copaw.agents.tools.file_io import _resolve_file_path

        working_dir, _ = tmp_copaw_dirs

        # Set up user context BEFORE importing file_io
        token = set_request_user_id("testuser")
        try:
            # Verify get_request_working_dir returns correct path
            current_wd = get_request_working_dir()
            assert current_wd == working_dir / "testuser", \
                f"Expected {working_dir / 'testuser'}, got {current_wd}"

            # Import file_io after setting context
            # Note: In real usage, the module is already loaded and uses
            # get_request_working_dir() at call time, not import time
            from copaw.agents.tools.file_io import _resolve_file_path

            # Test path resolution directly
            resolved = _resolve_file_path("test.txt")
            expected = str(working_dir / "testuser" / "test.txt")
            assert resolved == expected, f"Expected {expected}, got {resolved}"

        finally:
            reset_request_user_id(token)

    @pytest.mark.asyncio
    async def test_file_search_uses_user_directory(self, tmp_copaw_dirs):
        """Test that file search operations use user directory."""
        from copaw.agents.tools.file_search import grep_search

        working_dir, _ = tmp_copaw_dirs

        # Set up user context and create test files
        token = set_request_user_id("searchuser")
        try:
            # Create test files in user's directory
            user_dir = working_dir / "searchuser"
            user_dir.mkdir(parents=True, exist_ok=True)

            test_file = user_dir / "test.txt"
            test_file.write_text("This is searchuser's content")

            # Search should find the file in user's directory
            result = await grep_search(
                pattern="searchuser",
                path=None,  # Use default (user's directory)
            )

            # result.content[0] is a dict, not an object with .text
            result_text = result.content[0].get("text", "") \
                if isinstance(result.content[0], dict) \
                else result.content[0].text
            assert "test.txt" in result_text

        finally:
            reset_request_user_id(token)


class TestAgentInitialization:
    """Test agent initialization with user context."""

    def test_bootstrap_hook_uses_user_directory(self, tmp_copaw_dirs):
        """Test that BootstrapHook uses user directory."""
        from copaw.agents.hooks import BootstrapHook

        working_dir, _ = tmp_copaw_dirs

        token = set_request_user_id("hookuser")
        try:
            hook = BootstrapHook(
                working_dir=get_request_working_dir(),
                language="en",
            )

            # Hook's working_dir should be user's directory
            assert hook.working_dir == working_dir / "hookuser"
        finally:
            reset_request_user_id(token)

    def test_prompt_builder_uses_user_directory(self, tmp_copaw_dirs):
        """Test that PromptBuilder uses user directory."""
        from copaw.agents.prompt import PromptBuilder

        working_dir, _ = tmp_copaw_dirs

        token = set_request_user_id("promptuser")
        try:
            builder = PromptBuilder(
                working_dir=get_request_working_dir()
            )

            assert builder.working_dir == working_dir / "promptuser"
        finally:
            reset_request_user_id(token)


class TestBackwardCompatibility:
    """Test backward compatibility with runtime (single-user) mode."""

    def test_runtime_working_dir_still_works(self, tmp_copaw_dirs):
        """Test that get_runtime_working_dir() still works."""
        working_dir, _ = tmp_copaw_dirs

        # get_runtime_working_dir should return the patched runtime dir
        result = get_runtime_working_dir()
        assert result == working_dir, f"Expected {working_dir}, got {result}"

    def test_set_current_user_for_single_user_mode(self, tmp_copaw_dirs):
        """Test set_current_user() for CLI single-user mode."""
        working_dir, _ = tmp_copaw_dirs

        # Set current user (single-user mode)
        set_current_user("cliuser")

        # Runtime working dir should be updated
        result = get_runtime_working_dir()
        assert result == working_dir / "cliuser"

        # Reset
        set_current_user(None)

    def test_get_working_dir_explicit_user(self, tmp_copaw_dirs):
        """Test get_working_dir with explicit user_id."""
        working_dir, _ = tmp_copaw_dirs

        result = get_working_dir("explicituser")
        assert result == working_dir / "explicituser"


class TestAutoInitialization:
    """Test automatic user directory initialization."""

    def test_initialize_new_user_directory(self, tmp_copaw_dirs):
        """Test that new user directory is properly initialized."""
        from copaw.agents.utils.setup_utils import initialize_user_directory

        working_dir, secret_dir = tmp_copaw_dirs
        user_id = "newuser"

        # Should return True for new user
        result = initialize_user_directory(user_id, language="en")
        assert result is True

        # Verify directories and files created
        user_wd = working_dir / user_id
        user_secret = secret_dir / user_id

        assert (user_wd / "config.json").exists()
        assert (user_secret / "providers.json").exists()
        # Note: active_skills directory is created by sync_skills_to_working_dir
        # but may be empty if no builtin skills exist in test environment

    def test_initialize_existing_user_returns_false(self, tmp_copaw_dirs):
        """Test that initialization returns False for existing user."""
        from copaw.agents.utils.setup_utils import initialize_user_directory
        from copaw.config import Config, save_config

        working_dir, _ = tmp_copaw_dirs
        user_id = "existinguser"

        # Create config.json first
        user_wd = working_dir / user_id
        user_wd.mkdir(parents=True, exist_ok=True)
        save_config(Config(), user_wd / "config.json")

        # Should return False for existing user
        result = initialize_user_directory(user_id)
        assert result is False

    def test_ensure_providers_json_creates_default(self, tmp_copaw_dirs):
        """Test that ensure_providers_json creates default config."""
        from copaw.providers.store import ensure_providers_json

        _, secret_dir = tmp_copaw_dirs
        user_id = "testuser"

        # Create new providers.json
        result_path = ensure_providers_json(user_id)

        expected_path = secret_dir / user_id / "providers.json"
        assert result_path == expected_path
        assert result_path.exists()

        # Verify content is valid JSON
        import json
        with open(result_path) as f:
            data = json.load(f)
        assert "providers" in data or "active_llm" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
