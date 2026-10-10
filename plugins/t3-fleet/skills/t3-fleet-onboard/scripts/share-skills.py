#!/usr/bin/env python3
"""Superseded by sync-plugins.py.

The previous claude-skills-sync calls this after updating the plugin. Hand
over so that box installs the new sync on its next run.
"""

from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).with_name("sync-plugins.py")), run_name="__main__")
