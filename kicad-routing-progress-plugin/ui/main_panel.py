"""Interactive wxPython dialog for KiCad Net Routing Progress analysis."""

import fnmatch
import os
import sys
import wx
from typing import List, Optional

import pcbnew

_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _base_dir not in sys.path:
    sys.path.insert(0, _base_dir)

try:
    from ..core.routing_analyzer import (
        BoardRoutingSummary,
        NetRoutingInfo,
        analyze_board_routing,
        export_routing_report_to_csv,
    )
except (ImportError, ValueError):
    from core.routing_analyzer import (
        BoardRoutingSummary,
        NetRoutingInfo,
        analyze_board_routing,
        export_routing_report_to_csv,
    )


def get_theme_palette() -> dict:
    """Return theme-adaptive colors for Dark/Light mode compatibility in KiCad."""
    try:
        bg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)
        is_dark = (bg.Red() * 0.299 + bg.Green() * 0.587 + bg.Blue() * 0.114) < 128
    except Exception:
        is_dark = True

    if is_dark:
        return {
            "is_dark": True,
            "success": wx.Colour(100, 225, 130),
            "warning": wx.Colour(255, 185, 80),
            "danger": wx.Colour(255, 110, 110),
            "info": wx.Colour(120, 190, 255),
            "muted": wx.Colour(175, 175, 175),
        }
    else:
        return {
            "is_dark": False,
            "success": wx.Colour(0, 135, 30),
            "warning": wx.Colour(185, 95, 0),
            "danger": wx.Colour(200, 25, 25),
            "info": wx.Colour(0, 95, 210),
            "muted": wx.Colour(110, 110, 110),
        }


class RoutingProgressDialog(wx.Dialog):
    """Main dialog to display, filter, and inspect pending routing progress per net."""

    def __init__(self, parent, board):
        super().__init__(
            parent,
            title="KiCad Net Routing Progress - Progreso de Ruteo de Nets",
            size=(1060, 720),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX | wx.MINIMIZE_BOX,
        )
        self.SetMinSize((880, 560))
        self.board = board
        self.summary: Optional[BoardRoutingSummary] = None
        self.filtered_nets: List[NetRoutingInfo] = []
        self.sort_col = 1  # Default sort by % Pending descending
        self.sort_ascending = False

        self._init_ui()
        self._recalculate_and_refresh()

    def _init_ui(self):
        palette = get_theme_palette()
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ---------------------------------------------------------------------
        # 1. Panel de Resumen Global (Summary Card)
        # ---------------------------------------------------------------------
        summary_box = wx.StaticBox(self, label=" Resumen Global del PCB ")
        summary_sizer = wx.StaticBoxSizer(summary_box, wx.VERTICAL)

        self.lbl_global_progress = wx.StaticText(
            self, label="Progreso Global: Calculando..."
        )
        self.lbl_global_progress.SetFont(self.lbl_global_progress.GetFont().Bold().Larger())
        summary_sizer.Add(self.lbl_global_progress, 0, wx.ALL, 4)

        # Progress bar
        self.progress_bar = wx.Gauge(self, range=1000, style=wx.GA_HORIZONTAL)
        summary_sizer.Add(self.progress_bar, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # Multi-stat badges row
        stat_row = wx.BoxSizer(wx.HORIZONTAL)
        self.lbl_stat_nets = wx.StaticText(self, label="Total Nets: 0 | Activas: 0")
        self.lbl_stat_conns = wx.StaticText(self, label="Conexiones Pendientes: 0 / 0")
        self.lbl_stat_length = wx.StaticText(self, label="Pistas: 0 mm (0 vias)")

        stat_row.Add(self.lbl_stat_nets, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        stat_row.Add(self.lbl_stat_conns, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        stat_row.Add(self.lbl_stat_length, 1, wx.ALIGN_CENTER_VERTICAL)
        summary_sizer.Add(stat_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        main_sizer.Add(summary_sizer, 0, wx.EXPAND | wx.ALL, 8)

        # ---------------------------------------------------------------------
        # 2. Barra de Búsqueda y Filtros
        # ---------------------------------------------------------------------
        filter_bar = wx.BoxSizer(wx.HORIZONTAL)

        lbl_search = wx.StaticText(self, label="🔍 Filtrar Net:")
        lbl_search.SetFont(lbl_search.GetFont().Bold())

        self.txt_filter = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER, size=(240, -1))
        self.txt_filter.SetHint("Buscar net (GND, SPI*, *CLK*)...")
        self.txt_filter.Bind(wx.EVT_TEXT, self._on_filter_changed)

        self.choice_status = wx.Choice(
            self,
            choices=[
                "Todas las Nets",
                "Solo Pendientes (> 0% pendiente)",
                "Solo 100% Pendientes (Sin rutear)",
                "Solo En Progreso (Parciales)",
                "Solo 100% Ruteadas",
            ],
        )
        self.choice_status.SetSelection(0)
        self.choice_status.Bind(wx.EVT_CHOICE, self._on_filter_changed)

        self.chk_hide_single = wx.CheckBox(self, label="Ocultar nets de 0 o 1 pad")
        self.chk_hide_single.SetValue(True)
        self.chk_hide_single.Bind(wx.EVT_CHECKBOX, self._on_filter_changed)

        self.btn_clear_filter = wx.Button(self, label="↺ Limpiar", size=(-1, 26))
        self.btn_clear_filter.Bind(wx.EVT_BUTTON, self._on_clear_filter)

        filter_bar.Add(lbl_search, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        filter_bar.Add(self.txt_filter, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 8)
        filter_bar.Add(self.choice_status, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 8)
        filter_bar.Add(self.chk_hide_single, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 10)
        filter_bar.Add(self.btn_clear_filter, 0, wx.ALIGN_CENTER_VERTICAL)
        filter_bar.AddStretchSpacer(1)

        self.lbl_table_count = wx.StaticText(self, label="Mostrando 0 nets")
        self.lbl_table_count.SetForegroundColour(palette["muted"])
        filter_bar.Add(self.lbl_table_count, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)

        main_sizer.Add(filter_bar, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # ---------------------------------------------------------------------
        # 3. Tabla Principal de Nets
        # ---------------------------------------------------------------------
        self.list_ctrl = wx.ListCtrl(
            self,
            style=wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_SINGLE_SEL | wx.LC_VRULES | wx.LC_HRULES,
        )

        self.list_ctrl.InsertColumn(0, "Nombre de Net", wx.LIST_FORMAT_LEFT, 230)
        self.list_ctrl.InsertColumn(1, "% Pendiente", wx.LIST_FORMAT_RIGHT, 110)
        self.list_ctrl.InsertColumn(2, "% Ruteado", wx.LIST_FORMAT_RIGHT, 100)
        self.list_ctrl.InsertColumn(3, "Conexiones Pendientes", wx.LIST_FORMAT_CENTER, 160)
        self.list_ctrl.InsertColumn(4, "Total Pads", wx.LIST_FORMAT_CENTER, 90)
        self.list_ctrl.InsertColumn(5, "Pistas / Vías", wx.LIST_FORMAT_LEFT, 130)
        self.list_ctrl.InsertColumn(6, "Longitud Pistas", wx.LIST_FORMAT_RIGHT, 120)
        self.list_ctrl.InsertColumn(7, "Estado", wx.LIST_FORMAT_LEFT, 130)

        self.list_ctrl.Bind(wx.EVT_LIST_COL_CLICK, self._on_col_click)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_item_selected)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_item_double_clicked)

        main_sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # ---------------------------------------------------------------------
        # 4. Barra Inferior de Acciones
        # ---------------------------------------------------------------------
        bottom_bar = wx.BoxSizer(wx.HORIZONTAL)

        self.btn_refresh = wx.Button(self, label="🔄 Actualizar / Recalcular")
        self.btn_refresh.SetFont(self.btn_refresh.GetFont().Bold())
        self.btn_refresh.Bind(wx.EVT_BUTTON, lambda _e: self._recalculate_and_refresh())

        self.btn_highlight = wx.Button(self, label="💡 Resaltar Net en PCB")
        self.btn_highlight.Bind(wx.EVT_BUTTON, self._on_highlight_clicked)
        self.btn_highlight.Enable(False)

        self.btn_clear_highlight = wx.Button(self, label="🚫 Quitar Resaltado")
        self.btn_clear_highlight.Bind(wx.EVT_BUTTON, self._on_clear_highlight)

        self.btn_export_csv = wx.Button(self, label="📋 Exportar a CSV...")
        self.btn_export_csv.Bind(wx.EVT_BUTTON, self._on_export_csv)

        btn_close = wx.Button(self, wx.ID_CANCEL, label="Cerrar")
        btn_close.Bind(wx.EVT_BUTTON, lambda _e: self._on_close())

        bottom_bar.Add(self.btn_refresh, 0, wx.RIGHT, 8)
        bottom_bar.Add(self.btn_highlight, 0, wx.RIGHT, 6)
        bottom_bar.Add(self.btn_clear_highlight, 0, wx.RIGHT, 12)
        bottom_bar.Add(self.btn_export_csv, 0, wx.RIGHT, 8)
        bottom_bar.AddStretchSpacer(1)
        bottom_bar.Add(btn_close, 0)

        main_sizer.Add(bottom_bar, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        self.SetSizer(main_sizer)

    def _recalculate_and_refresh(self):
        try:
            self.board = pcbnew.GetBoard()
        except Exception:
            pass

        self.summary = analyze_board_routing(self.board)
        self._update_summary_card()
        self._apply_filters_and_populate()

    def _update_summary_card(self):
        if not self.summary:
            return

        palette = get_theme_palette()
        pct_routed = self.summary.global_pct_routed
        pct_pending = self.summary.global_pct_pending

        self.lbl_global_progress.SetLabel(
            f"Progreso Global: {pct_routed:.1f}% Ruteado  ({pct_pending:.1f}% Pendiente)"
        )

        if pct_pending == 0.0:
            self.lbl_global_progress.SetForegroundColour(palette["success"])
        elif pct_pending < 50.0:
            self.lbl_global_progress.SetForegroundColour(palette["info"])
        else:
            self.lbl_global_progress.SetForegroundColour(palette["warning"])

        # Progress bar (0 to 1000)
        self.progress_bar.SetValue(min(1000, max(0, int(pct_routed * 10))))

        self.lbl_stat_nets.SetLabel(
            f"Total Nets: {self.summary.total_nets} (Activas: {self.summary.active_nets} | Completas: {self.summary.completed_nets})"
        )
        self.lbl_stat_conns.SetLabel(
            f"Conexiones Pendientes: {self.summary.total_pending_connections} / {self.summary.total_expected_connections}"
        )
        self.lbl_stat_length.SetLabel(
            f"Pistas: {self.summary.total_track_length_mm:.1f} mm ({self.summary.total_tracks} segs, {self.summary.total_vias} vías)"
        )

    def _apply_filters_and_populate(self):
        if not self.summary:
            return

        q = self.txt_filter.GetValue().strip().lower()
        status_choice = self.choice_status.GetSelection()
        hide_single = self.chk_hide_single.GetValue()

        filtered: List[NetRoutingInfo] = []

        for net in self.summary.net_results:
            # 1. Hide single/empty nets filter
            if hide_single and net.total_pads <= 1:
                continue

            # 2. Status filter
            if status_choice == 1 and net.pct_pending <= 0.0:
                continue  # Solo pendientes (> 0%)
            elif status_choice == 2 and net.pct_pending < 100.0:
                continue  # Solo 100% pendientes
            elif status_choice == 3 and (net.pct_pending <= 0.0 or net.pct_pending >= 100.0):
                continue  # Solo en progreso (0% < x < 100%)
            elif status_choice == 4 and net.pct_pending > 0.0:
                continue  # Solo 100% ruteadas

            # 3. Query text filter
            if q:
                name_lower = net.netname.lower()
                match = (q in name_lower or fnmatch.fnmatch(name_lower, q))
                if not match:
                    continue

            filtered.append(net)

        self._sort_nets(filtered)
        self.filtered_nets = filtered
        self._populate_table()

    def _sort_nets(self, net_list: List[NetRoutingInfo]):
        # Columns: 0:Name, 1:%Pending, 2:%Routed, 3:PendingConns, 4:TotalPads, 5:Tracks, 6:Length, 7:Status
        key_map = {
            0: lambda n: n.netname.lower(),
            1: lambda n: n.pct_pending,
            2: lambda n: n.pct_routed,
            3: lambda n: n.pending_connections,
            4: lambda n: n.total_pads,
            5: lambda n: n.track_count + n.via_count,
            6: lambda n: n.routed_length_mm,
            7: lambda n: n.status_label,
        }
        key_func = key_map.get(self.sort_col, lambda n: n.pct_pending)
        net_list.sort(key=key_func, reverse=not self.sort_ascending)

    def _populate_table(self):
        palette = get_theme_palette()
        self.list_ctrl.DeleteAllItems()

        for row_idx, net in enumerate(self.filtered_nets):
            self.list_ctrl.InsertItem(row_idx, net.netname)
            self.list_ctrl.SetItem(row_idx, 1, f"{net.pct_pending:.1f}%")
            self.list_ctrl.SetItem(row_idx, 2, f"{net.pct_routed:.1f}%")
            self.list_ctrl.SetItem(row_idx, 3, f"{net.pending_connections} / {net.total_connections}")
            self.list_ctrl.SetItem(row_idx, 4, str(net.total_pads))
            self.list_ctrl.SetItem(row_idx, 5, f"{net.track_count} trk / {net.via_count} via")
            self.list_ctrl.SetItem(row_idx, 6, f"{net.routed_length_mm:.1f} mm")
            self.list_ctrl.SetItem(row_idx, 7, net.status_label)

            # Color coding for readability
            if net.total_pads <= 1:
                self.list_ctrl.SetItemTextColour(row_idx, palette["muted"])
            elif net.pct_pending == 0.0:
                self.list_ctrl.SetItemTextColour(row_idx, palette["success"])
            elif net.pct_pending == 100.0:
                self.list_ctrl.SetItemTextColour(row_idx, palette["danger"])
            else:
                self.list_ctrl.SetItemTextColour(row_idx, palette["warning"])

        total_available = len(self.summary.net_results) if self.summary else 0
        vis_count = len(self.filtered_nets)
        self.lbl_table_count.SetLabel(f"Mostrando {vis_count} de {total_available} nets")
        self.btn_highlight.Enable(False)

    # -------------------------------------------------------------------------
    # Event Handlers
    # -------------------------------------------------------------------------
    def _on_filter_changed(self, _event):
        self._apply_filters_and_populate()

    def _on_clear_filter(self, _event):
        self.txt_filter.SetValue("")
        self.choice_status.SetSelection(0)
        self.chk_hide_single.SetValue(True)
        self._apply_filters_and_populate()

    def _on_col_click(self, event):
        col = event.GetColumn()
        if col == self.sort_col:
            self.sort_ascending = not self.sort_ascending
        else:
            self.sort_col = col
            self.sort_ascending = (col == 0)  # Default ascending for name, descending for others

        self._sort_nets(self.filtered_nets)
        self._populate_table()

    def _get_selected_net(self) -> Optional[NetRoutingInfo]:
        idx = self.list_ctrl.GetFirstSelected()
        if 0 <= idx < len(self.filtered_nets):
            return self.filtered_nets[idx]
        return None

    def _on_item_selected(self, _event):
        net = self._get_selected_net()
        self.btn_highlight.Enable(net is not None)
        if net:
            self._highlight_net_in_pcb(net.netcode)

    def _on_item_double_clicked(self, _event):
        net = self._get_selected_net()
        if net:
            self._highlight_net_in_pcb(net.netcode)
            pads_str = ", ".join(net.pads_info[:15])
            if len(net.pads_info) > 15:
                pads_str += f" ... (+{len(net.pads_info)-15} más)"

            wx.MessageBox(
                f"Detalle de Net: {net.netname} (NetCode: {net.netcode})\n\n"
                f"• Estado: {net.status_label}\n"
                f"• Conexiones pendientes: {net.pending_connections} de {net.total_connections}\n"
                f"• Total Pads ({net.total_pads}): {pads_str}\n"
                f"• Pistas: {net.track_count} segmentos ({net.routed_length_mm} mm)\n"
                f"• Vías: {net.via_count}\n\n"
                "💡 La net ha sido resaltada en la ventana del PCB Editor.",
                f"Detalle de Net: {net.netname}",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )

    def _highlight_net_in_pcb(self, netcode: int):
        if not self.board or netcode <= 0:
            return
        try:
            self.board.SetHighLightNet(netcode)
            self.board.HighLightON()
            pcbnew.Refresh()
        except Exception:
            pass

    def _on_highlight_clicked(self, _event):
        net = self._get_selected_net()
        if net:
            self._highlight_net_in_pcb(net.netcode)

    def _on_clear_highlight(self, _event):
        if not self.board:
            return
        try:
            self.board.ResetNetHighLight()
            self.board.HighLightOFF()
            pcbnew.Refresh()
        except Exception:
            pass

    def _on_export_csv(self, _event):
        if not self.summary or not self.summary.net_results:
            wx.MessageBox("No hay datos de ruteo para exportar.", "Exportar CSV", wx.OK | wx.ICON_WARNING, self)
            return

        with wx.FileDialog(
            self,
            "Guardar Informe de Ruteo en CSV",
            wildcard="Archivos CSV (*.csv)|*.csv",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            path = fileDialog.GetPath()
            if not path.endswith(".csv"):
                path += ".csv"

            ok = export_routing_report_to_csv(self.summary, path)
            if ok:
                wx.MessageBox(
                    f"¡Informe exportado con éxito!\n\nArchivo: {path}",
                    "Exportar CSV",
                    wx.OK | wx.ICON_INFORMATION,
                    self,
                )
            else:
                wx.MessageBox("Error al guardar el archivo CSV.", "Error", wx.OK | wx.ICON_ERROR, self)

    def _on_close(self):
        self._on_clear_highlight(None)
        self.Close()
