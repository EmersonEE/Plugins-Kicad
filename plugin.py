"""Block Aligner entry point.

This module is now a thin facade: the logic has been split into

* ``config.py``    - tunable constants + JSON config file
* ``core.py``      - pure, deterministic geometry/matching (unit-testable)
* ``discovery.py`` - automatic block discovery
* ``tracks.py``    - KiCad ``pcbnew`` copper/position/orientation integrations
* ``ui.py``        - wxPython dialogs

``BlockAlignerPlugin`` is kept here so ``__init__.py`` and any existing import
of ``from .plugin import BlockAlignerPlugin`` keep working. The dialog classes
are re-exported for backward compatibility.
"""

import os

import pcbnew
import wx

from . import config  # noqa: F401  (re-export)
from . import core  # noqa: F401  (re-export)
from . import discovery  # noqa: F401  (re-export)
from . import schematic  # noqa: F401  (re-export)
from . import tracks  # noqa: F401  (re-export)
from .ui import (  # noqa: F401  (re-export)
    BlockAlignerDialog,
    DiagnosticLogDialog,
    ErrorDetailsDialog,
    generate_diagnostic_report,
)


class BlockAlignerPlugin(pcbnew.ActionPlugin):
    def __init__(self):
        super().__init__()
        self.dialog = None

    def defaults(self):
        self.name = "Block Aligner"
        self.category = "Layout Helper"
        self.description = "Alinea bloques repetidos copiando posiciones y orientaciones."
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(os.path.dirname(__file__), "icon.png")

    def Run(self):
        try:
            board = pcbnew.GetBoard()
        except Exception:
            board = None
        if board is None:
            try:
                wx.MessageBox(
                    "No hay ninguna placa (PCB) abierta en el editor.",
                    "Block Aligner",
                    wx.OK | wx.ICON_WARNING,
                )
            except Exception:
                pass
            return
        if self.dialog is not None and self.dialog.IsShown():
            self.dialog.Raise()
            return
        self.dialog = BlockAlignerDialog(None, board)
        self.dialog.Bind(wx.EVT_CLOSE, self._close_dialog)
        self.dialog.Show()

    def _close_dialog(self, event):
        if self.dialog is not None:
            if getattr(self.dialog, "preview_state", None) is not None:
                self.dialog.cancel_preview(None)
            self.dialog.Destroy()
            self.dialog = None
        event.Skip()
