# -*- coding: utf-8 -*-
"""Two-stage entry points for explicitly isolated tenant migrations."""

import json
import os

import click


def _write_discovery(path, report):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True)


def prepare_workflow(
    services,
    boundary,
    manifest,
    *,
    shares_file=None,
    overrides=None,
    tenant_isolation=False,
    in_place=False,
    application_schema=None,
    **resources,
):
    from swe.database.config import get_database_config
    from swe.app.conversation_storage.migration.manifest import SourceBoundary
    from .conversation_storage_discovery_cmd import (
        _list,
        _read,
        _semantic_validator,
        discover_services,
        freeze_discovery,
    )
    from .conversation_storage_v3_cmd import run_v3_command, validate_output

    if not tenant_isolation:
        raise ValueError("prepare requires explicit --tenant-isolation")
    declared = _list(_read(services), "services")
    path = validate_output(manifest, {"services": declared})
    discovery_path = path.with_name(path.name + ".discovery.json")
    if path.exists() or discovery_path.exists():
        raise FileExistsError("prepare output already exists")
    source_boundary = SourceBoundary(**_read(boundary))
    configured_schema = get_database_config().database
    schema = application_schema or configured_schema
    if schema != configured_schema:
        raise ValueError("configured application schema differs from prepare")
    report = discover_services(
        declared,
        shares=(),
        overrides=_list(_read(overrides), "overrides") if overrides else [],
        tenant_isolation=True,
        source_isolation=True,
        in_place=in_place,
        source_binding_storage="manifest-v1",
        semantic_inventory=False,
    )
    if not report.get("tenants"):
        raise ValueError("prepare requires at least one discovered tenant")
    frozen = freeze_discovery(
        report,
        path,
        source_boundary,
        schema,
        semantic_validator=_semantic_validator(**resources),
        revalidate=False,
    )
    _write_discovery(
        discovery_path,
        {key: frozen.data[key] for key in report},
    )
    result = run_v3_command(
        "preflight",
        frozen.path,
        apply=False,
        **resources,
    )
    return {
        **result,
        "operation": "prepare",
        "manifest": str(frozen.path),
        "discovery": str(discovery_path),
        "migration_id": frozen.migration_id,
    }


def register_workflow_commands(group):
    from .conversation_storage_discovery_cmd import _resource_options
    from .conversation_storage_v3_cmd import (
        echo_migration_report,
        run_v3_and_echo,
    )

    @group.command("prepare")
    @_resource_options
    @click.option(
        "--services",
        required=True,
        type=click.Path(exists=True, dir_okay=False),
    )
    @click.option(
        "--boundary",
        required=True,
        type=click.Path(exists=True, dir_okay=False),
    )
    @click.option("--manifest", required=True, type=click.Path(dir_okay=False))
    @click.option(
        "--shares-file",
        type=click.Path(exists=True, dir_okay=False),
        help="Deprecated; historical share records are skipped.",
    )
    @click.option("--overrides", type=click.Path(exists=True, dir_okay=False))
    @click.option("--tenant-isolation", is_flag=True)
    @click.option("--in-place", is_flag=True)
    @click.option("--application-schema")
    def prepare_command(**options):
        try:
            result = prepare_workflow(**options)
            echo_migration_report(result)
            if result.get("status") == "partial_success":
                raise click.exceptions.Exit(2)
            if result.get("passed") is False:
                raise click.ClickException("prepare preflight failed")
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise click.ClickException(str(error)) from error

    @group.command("migrate")
    @_resource_options
    @click.option(
        "--manifest",
        required=True,
        type=click.Path(exists=True, dir_okay=False),
    )
    @click.option("--apply", is_flag=True)
    @click.option("--full-audit", is_flag=True)
    def migrate_command(manifest, **options):
        try:
            run_v3_and_echo("migrate", manifest, **options)
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise click.ClickException(str(error)) from error
