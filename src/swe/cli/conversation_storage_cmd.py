# -*- coding: utf-8 -*-
"""Offline maintenance of MySQL Chat metadata."""

import click

from .conversation_storage_workflow_cmd import register_workflow_commands


@click.group("conversation-storage")
def conversation_storage_group():
    """Migrate Chat metadata after stopping all writers."""


register_workflow_commands(conversation_storage_group)
