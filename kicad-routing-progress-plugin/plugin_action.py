"""Action Plugin definition for KiCad Net Routing Progress Plugin."""

import os
import sys
import pcbnew
import wx

_base_dir = os.path.dirname(os.path.abspath(__file__))
if _base_dir not in sys.path:
    sys.path.insert(0, _base_dir)

try:
    from .ui.main_panel import RoutingProgressDialog
except (ImportError, ValueError):
    from ui.main_panel import RoutingProgressDialog


class NetRoutingProgressPlugin(pcbnew.ActionPlugin):
    """Action Plugin to analyze and display net-by-net pending routing progress."""

    def __init__(self):
        super().__init__()
        self.dialog = None

    def defaults(self):
        self.name = "Net Routing Progress"
        self.category = "Routing Analysis"
        self.description = "Muestra el porcentaje de ruteo pendiente por net y conexiones ratsnest (Estilo Altium)."
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(os.path.dirname(__file__), "icon.png")

    def Run(self):
        board = pcbnew.GetBoard()
        if not board:
            wx.MessageBox(
                "No hay ninguna placa abierta en el PCB Editor de KiCad.",
                "Net Routing Progress",
                wx.OK | wx.ICON_WARNING,
            )
            return

        if self.dialog is not None and self.dialog.IsShown():
            self.dialog.Raise()
            return

        self.dialog = RoutingProgressDialog(None, board)
        self.dialog.Bind(wx.EVT_CLOSE, self._close_dialog)
        self.dialog.Show()

    def _close_dialog(self, event):
        if self.dialog is not None:
            self.dialog.Destroy()
            self.dialog = None
        event.Skip()
