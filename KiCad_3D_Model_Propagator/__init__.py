"""KiCad 3D Model Propagator Action Plugin."""

import sys
import os

_base_dir = os.path.dirname(os.path.abspath(__file__))
if _base_dir not in sys.path:
    sys.path.insert(0, _base_dir)

try:
    from .plugin import ModelPropagatorPlugin
except (ImportError, ValueError):
    from plugin import ModelPropagatorPlugin

ModelPropagatorPlugin().register()
