"""Action Plugin definition for KiCad 3D Model Propagator."""

import os
import sys
import pcbnew
import wx

_base_dir = os.path.dirname(os.path.abspath(__file__))
if _base_dir not in sys.path:
    sys.path.insert(0, _base_dir)

try:
    from .ui.main_dialog import ModelPropagatorDialog
except (ImportError, ValueError):
    from ui.main_dialog import ModelPropagatorDialog


class ModelPropagatorPlugin(pcbnew.ActionPlugin):
    """Action Plugin to copy and propagate 3D models across identical footprints."""

    def __init__(self):
        super().__init__()
        self.dialog = None

    def defaults(self):
        self.name = "3D Model Propagator"
        self.category = "3D Model Helper"
        self.description = "Propaga modelos 3D desde una referencia a footprints idénticos."
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(os.path.dirname(__file__), "icon.png")

    def Run(self):
        board = pcbnew.GetBoard()
        if not board:
            wx.MessageBox(
                "No hay ninguna placa abierta en el PCB Editor.",
                "3D Model Propagator",
                wx.OK | wx.ICON_WARNING,
            )
            return

        if self.dialog is not None and self.dialog.IsShown():
            self.dialog.Raise()
            return

        self.dialog = ModelPropagatorDialog(None, board)
        self.dialog.Bind(wx.EVT_CLOSE, self._close_dialog)
        self.dialog.Show()

    def _close_dialog(self, event):
        if self.dialog is not None:
            self.dialog.Destroy()
            self.dialog = None
        event.Skip()
