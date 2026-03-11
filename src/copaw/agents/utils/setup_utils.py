# -*- coding: utf-8 -*-
"""Setup and initialization utilities for agent configuration.

This module handles copying markdown configuration files to
the working directory.
"""
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def initialize_user_directory(
    user_id: str,
    language: str = "en",
) -> bool:
    """Initialize user directory with minimal required files.

    This function is called automatically when a request is received
    from a new user. It creates the minimum set of files and directories
    required for the agent to function.

    Args:
        user_id: User identifier
        language: Language code for default config (default: "en")

    Returns:
        True if initialization was performed, False if directory already existed
    """
    from ...constant import get_working_dir, get_secret_dir
    from ...config import Config, save_config
    from ...providers.store import ensure_providers_json
    from ...agents.skills_manager import sync_skills_to_working_dir

    working_dir = get_working_dir(user_id)
    secret_dir = get_secret_dir(user_id)

    # Check if already initialized (config.json exists)
    config_path = working_dir / "config.json"
    if config_path.exists():
        logger.debug("User %s directory already initialized", user_id)
        return False

    # Create base directories
    working_dir.mkdir(parents=True, exist_ok=True)
    secret_dir.mkdir(parents=True, exist_ok=True)

    # Create default config.json
    config = Config()
    config.agents.language = language
    save_config(config, config_path)
    logger.info("Created default config.json for user %s", user_id)

    # Create default providers.json (without API keys)
    ensure_providers_json(user_id)
    logger.info("Created default providers.json for user %s", user_id)

    # Sync built-in skills to active_skills (required for agent to work)
    sync_skills_to_working_dir(force=False)
    logger.info("Synced built-in skills for user %s", user_id)

    logger.info(
        "User %s directory initialized at %s",
        user_id,
        working_dir,
    )
    return True


def copy_md_files(
    language: str,
    skip_existing: bool = False,
) -> list[str]:
    """Copy md files from agents/md_files to working directory.

    Args:
        language: Language code (e.g. 'en', 'zh')
        skip_existing: If True, skip files that already exist in working dir.

    Returns:
        List of copied file names.
    """
    from ...constant import get_request_working_dir

    # Get md_files directory path with language subdirectory
    md_files_dir = Path(__file__).parent.parent / "md_files" / language

    if not md_files_dir.exists():
        logger.warning(
            "MD files directory not found: %s, falling back to 'en'",
            md_files_dir,
        )
        # Fallback to English if specified language not found
        md_files_dir = Path(__file__).parent.parent / "md_files" / "en"
        if not md_files_dir.exists():
            logger.error("Default 'en' md files not found either")
            return []

    # Ensure working directory exists
    working_dir = get_request_working_dir()  # Use request-scoped
    working_dir.mkdir(parents=True, exist_ok=True)

    # Copy all .md files to working directory
    copied_files: list[str] = []
    for md_file in md_files_dir.glob("*.md"):
        target_file = working_dir / md_file.name
        if skip_existing and target_file.exists():
            logger.debug("Skipped existing md file: %s", md_file.name)
            continue
        try:
            shutil.copy2(md_file, target_file)
            logger.debug("Copied md file: %s", md_file.name)
            copied_files.append(md_file.name)
        except Exception as e:
            logger.error(
                "Failed to copy md file '%s': %s",
                md_file.name,
                e,
            )

    if copied_files:
        logger.debug(
            "Copied %d md file(s) [%s] to %s",
            len(copied_files),
            language,
            working_dir,
        )

    return copied_files
