# -*- coding: utf-8 -*-
"""Regression coverage for runner imports that must not load tool packages."""

import importlib


def test_task_tracker_import_does_not_create_a_tool_output_cycle():
    module = importlib.import_module("swe.app.runner.task_tracker")

    assert module.TaskTracker is not None
