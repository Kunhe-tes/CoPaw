# -*- coding: utf-8 -*-
"""Backup configuration models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BackupEnvironmentConfig(BaseModel):
    """AWS S3 configuration for a single environment (dev/prd)."""

    aws_access_key_id: str
    aws_secret_access_key: str
    s3_bucket: str
    s3_prefix: str = "cmbswe"
    s3_region: str = "cn-north-1"


class BackupCompressionConfig(BaseModel):
    """Compression settings for backup archives."""

    level: int = Field(default=6, ge=0, le=9)


class BackupTimeoutConfig(BaseModel):
    """Timeout settings for backup operations (minutes)."""

    compress: int = 30
    upload: int = 30
    download: int = 30


class BackupConfig(BaseModel):
    """Root backup configuration."""

    environments: dict[str, BackupEnvironmentConfig] = Field(
        default_factory=dict
    )
    compression: BackupCompressionConfig = Field(
        default_factory=BackupCompressionConfig
    )
    timeout: BackupTimeoutConfig = Field(default_factory=BackupTimeoutConfig)

    def get_active_config(self) -> BackupEnvironmentConfig | None:
        """Get active environment config based on COPAW_BACKUP_ENV."""
        import os

        env = os.environ.get("COPAW_BACKUP_ENV", "dev")
        return self.environments.get(env)
