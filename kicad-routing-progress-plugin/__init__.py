"""KiCad Net Routing Progress Action Plugin entry point."""

import os
import sys

_base_dir = os.path.dirname(os.path.abspath(__file__))
if _base_dir not in sys.path:
    sys.path.insert(0, _base_dir)

try:
    from .plugin_action import NetRoutingProgressPlugin
except (ImportError, ValueError):
    from plugin_action import NetRoutingProgressPlugin

NetRoutingProgressPlugin().register()
