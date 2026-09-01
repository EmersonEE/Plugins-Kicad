#!/usr/bin/env python3
"""Schematic Footprint Manager - KiCad Batch Footprint Assignment Tool.

Author: Emerson / DeepMind Assistant
"""

import os
import sys
import wx

# Add project root directory to python path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ui.main_window import MainWindow


def main():
    app = wx.App()
    initial_file = None
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if os.path.isfile(arg):
            initial_file = os.path.abspath(arg)

    frame = MainWindow(initial_path=initial_file)

    # Set icon if exists
    icon_path = os.path.join(ROOT_DIR, "icon.png")
    if os.path.isfile(icon_path):
        try:
            icon = wx.Icon(icon_path, wx.BITMAP_TYPE_PNG)
            frame.SetIcon(icon)
        except Exception:
            pass

    frame.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()
