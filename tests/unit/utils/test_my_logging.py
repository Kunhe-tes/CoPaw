# -*- coding: utf-8 -*-
import logging

from swe.utils.my_logging import ColorFormatter


def test_color_formatter_escapes_multiline_messages() -> None:
    formatter = ColorFormatter(
        "%(asctime)s | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )
    record = logging.LogRecord(
        name="swe.test",
        level=logging.INFO,
        pathname="/tmp/example.py",
        lineno=12,
        msg="first line\nsecond line\r\nthird line",
        args=(),
        exc_info=None,
    )

    formatted = formatter.format(record)

    assert "\n" not in formatted
    assert "\r" not in formatted
    assert r"first line\nsecond line\r\nthird line" in formatted
