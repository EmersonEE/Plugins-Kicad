#!/usr/bin/env python3
"""KiCad BOM Estimator (La Electrónica GT) - Live Price & Stock Quoter.

Author: Emerson / DeepMind Assistant
"""

import os
import sys
import wx

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ui.main_window import MainWindow


def main():
    app = wx.App()
    initial_file = None
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        initial_file = os.path.abspath(sys.argv[1])

    frame = MainWindow(initial_file=initial_file)

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
