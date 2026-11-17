"""Main Application Window for KiCad BOM Estimator (La Electrónica GT)."""

import os
import threading
import webbrowser
import wx
from typing import List, Optional

from core.bom_extractor import BOMExtractor, BOMItem
from core.laelectronica_api import LaElectronicaClient
from core.exporter import BOMExporter
from ui.product_picker import ProductPickerDialog


class MainWindow(wx.Frame):
    """Main application frame with interactive live BOM pricing table."""

    def __init__(self, initial_file: Optional[str] = None):
        super().__init__(
            parent=None,
            title="KiCad BOM Estimator - Precios en Vivo (La Electrónica GT)",
            size=(1240, 780),
            style=wx.DEFAULT_FRAME_STYLE,
        )
        self.SetMinSize((940, 600))

        self.api_client = LaElectronicaClient()
        self.bom_items: List[BOMItem] = []
        self.displayed_items: List[BOMItem] = []
        self.current_file_path: str = ""
        self.is_fetching: bool = False

        self._init_ui()

        if initial_file and os.path.isfile(initial_file):
            self.load_and_price_schematic(initial_file)

    def _init_ui(self):
        main_pnl = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ---------------------------------------------------------------------
        # 1. Barra Superior: Carga de Esquemático y Botón de Cotizar
        # ---------------------------------------------------------------------
        top_box = wx.StaticBox(main_pnl, label=" 1. Esquemático / Proyecto de KiCad ")
        top_sizer = wx.StaticBoxSizer(top_box, wx.HORIZONTAL)

        self.btn_open = wx.Button(main_pnl, label="📂 Abrir Esquemático (.kicad_sch / .kicad_pro)")
        self.txt_file_path = wx.TextCtrl(main_pnl, style=wx.TE_READONLY | wx.BORDER_SUNKEN)
        self.txt_file_path.SetHint("Selecciona tu archivo esquemático...")

        self.btn_reprice = wx.Button(main_pnl, label="🔄 Re-cotizar en Vivo")
        self.btn_reprice.SetBackgroundColour(wx.Colour(230, 245, 255))

        self.btn_open.Bind(wx.EVT_BUTTON, self._on_open_clicked)
        self.btn_reprice.Bind(wx.EVT_BUTTON, self._on_reprice_clicked)

        top_sizer.Add(self.btn_open, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 8)
        top_sizer.Add(self.txt_file_path, 1, wx.RIGHT | wx.EXPAND, 8)
        top_sizer.Add(self.btn_reprice, 0, wx.ALIGN_CENTER_VERTICAL)
        main_sizer.Add(top_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # ---------------------------------------------------------------------
        # 2. Tarjeta de Resumen y Costo Total en Quetzales (Q)
        # ---------------------------------------------------------------------
        summary_pnl = wx.Panel(main_pnl)
        summary_pnl.SetBackgroundColour(wx.Colour(242, 248, 255))
        summary_sizer = wx.BoxSizer(wx.HORIZONTAL)

        stats_col = wx.BoxSizer(wx.VERTICAL)
        self.lbl_stats_components = wx.StaticText(
            summary_pnl, label="Componentes: 0 totales | 0 líneas de BOM"
        )
        self.lbl_stats_components.SetFont(self.lbl_stats_components.GetFont().Bold())

        self.lbl_stats_matched = wx.StaticText(
            summary_pnl, label="Cotizados con éxito: 0 de 0 productos"
        )
        self.lbl_stats_matched.SetForegroundColour(wx.Colour(80, 80, 80))

        stats_col.Add(self.lbl_stats_components, 0, wx.BOTTOM, 4)
        stats_col.Add(self.lbl_stats_matched, 0)
        summary_sizer.Add(stats_col, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 12)

        # Total Price Display Badge
        price_col = wx.BoxSizer(wx.VERTICAL)
        price_title = wx.StaticText(summary_pnl, label="COSTO TOTAL ESTIMADO:")
        price_title.SetFont(wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        price_title.SetForegroundColour(wx.Colour(0, 80, 160))

        self.lbl_total_price = wx.StaticText(summary_pnl, label="Q 0.00")
        total_font = wx.Font(24, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        self.lbl_total_price.SetFont(total_font)
        self.lbl_total_price.SetForegroundColour(wx.Colour(0, 102, 204))

        price_col.Add(price_title, 0, wx.ALIGN_RIGHT)
        price_col.Add(self.lbl_total_price, 0, wx.ALIGN_RIGHT)
        summary_sizer.Add(price_col, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT | wx.ALL, 12)

        summary_pnl.SetSizer(summary_sizer)
        main_sizer.Add(summary_pnl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # ---------------------------------------------------------------------
        # 3. Filtros Rápidos y Búsqueda
        # ---------------------------------------------------------------------
        filter_pnl = wx.Panel(main_pnl)
        filter_sizer = wx.BoxSizer(wx.HORIZONTAL)

        search_lbl = wx.StaticText(filter_pnl, label="🔍 Filtrar tabla:")
        self.search_ctrl = wx.SearchCtrl(filter_pnl, style=wx.TE_PROCESS_ENTER)
        self.search_ctrl.ShowCancelButton(True)
        self.search_ctrl.SetDescriptiveText("Buscar por referencia, valor, huella o producto...")

        status_lbl = wx.StaticText(filter_pnl, label="Estado:")
        self.status_choice = wx.Choice(
            filter_pnl,
            choices=[
                "(Todos los componentes)",
                "Solo con precio encontrado",
                "Solo sin precio / no encontrados",
                "Solo productos en Stock",
            ],
        )
        self.status_choice.SetSelection(0)

        filter_sizer.Add(search_lbl, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        filter_sizer.Add(self.search_ctrl, 1, wx.RIGHT | wx.EXPAND, 12)
        filter_sizer.Add(status_lbl, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        filter_sizer.Add(self.status_choice, 0, wx.ALIGN_CENTER_VERTICAL)
        filter_pnl.SetSizer(filter_sizer)
        main_sizer.Add(filter_pnl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # ---------------------------------------------------------------------
        # 4. Tabla de Lista de Materiales y Precios
        # ---------------------------------------------------------------------
        self.list_ctrl = wx.ListCtrl(
            main_pnl,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN | wx.LC_VRULES | wx.LC_HRULES,
        )
        self.list_ctrl.InsertColumn(0, "#", wx.LIST_FORMAT_CENTER, 40)
        self.list_ctrl.InsertColumn(1, "Cant.", wx.LIST_FORMAT_CENTER, 55)
        self.list_ctrl.InsertColumn(2, "Referencias", wx.LIST_FORMAT_LEFT, 160)
        self.list_ctrl.InsertColumn(3, "Valor", wx.LIST_FORMAT_LEFT, 110)
        self.list_ctrl.InsertColumn(4, "Huella (Footprint)", wx.LIST_FORMAT_LEFT, 210)
        self.list_ctrl.InsertColumn(5, "Producto en laelectronica.com.gt", wx.LIST_FORMAT_LEFT, 330)
        self.list_ctrl.InsertColumn(6, "Precio Unit.", wx.LIST_FORMAT_RIGHT, 100)
        self.list_ctrl.InsertColumn(7, "Subtotal (Q)", wx.LIST_FORMAT_RIGHT, 110)
        self.list_ctrl.InsertColumn(8, "Disponibilidad", wx.LIST_FORMAT_CENTER, 110)

        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_item_double_clicked)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self._on_item_right_clicked)

        main_sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Progress bar during live fetching
        self.progress_bar = wx.Gauge(main_pnl, range=100, style=wx.GA_HORIZONTAL)
        self.progress_bar.Hide()
        main_sizer.Add(self.progress_bar, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # ---------------------------------------------------------------------
        # 5. Barra Inferior de Exportación y Acciones
        # ---------------------------------------------------------------------
        bottom_pnl = wx.Panel(main_pnl)
        bottom_sizer = wx.BoxSizer(wx.HORIZONTAL)

        hint_lbl = wx.StaticText(
            bottom_pnl,
            label="💡 Haz doble clic en cualquier fila para cambiar o buscar un producto alternativo.",
        )
        hint_lbl.SetForegroundColour(wx.Colour(110, 110, 110))

        self.btn_export_csv = wx.Button(bottom_pnl, label="📊 Exportar a CSV (Excel)")
        self.btn_export_html = wx.Button(bottom_pnl, label="🌐 Exportar Reporte HTML")
        self.btn_open_shop = wx.Button(bottom_pnl, label="🛒 Abrir laelectronica.com.gt")

        self.btn_export_csv.Bind(wx.EVT_BUTTON, self._on_export_csv)
        self.btn_export_html.Bind(wx.EVT_BUTTON, self._on_export_html)
        self.btn_open_shop.Bind(wx.EVT_BUTTON, lambda _e: webbrowser.open("https://laelectronica.com.gt"))

        bottom_sizer.Add(hint_lbl, 1, wx.ALIGN_CENTER_VERTICAL)
        bottom_sizer.Add(self.btn_export_csv, 0, wx.RIGHT, 6)
        bottom_sizer.Add(self.btn_export_html, 0, wx.RIGHT, 6)
        bottom_sizer.Add(self.btn_open_shop, 0)
        bottom_pnl.SetSizer(bottom_sizer)
        main_sizer.Add(bottom_pnl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        main_pnl.SetSizer(main_sizer)

        # Event bindings
        self.search_ctrl.Bind(wx.EVT_TEXT, self._on_filter_changed)
        self.search_ctrl.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, lambda _e: self.search_ctrl.SetValue(""))
        self.status_choice.Bind(wx.EVT_CHOICE, self._on_filter_changed)

        self._update_ui_state()

    def _update_ui_state(self):
        has_items = bool(self.bom_items)
        self.btn_reprice.Enable(has_items and not self.is_fetching)
        self.btn_export_csv.Enable(has_items and not self.is_fetching)
        self.btn_export_html.Enable(has_items and not self.is_fetching)

    def load_and_price_schematic(self, file_path: str):
        """Extract BOM from schematic and trigger live online pricing."""
        self.current_file_path = file_path
        self.txt_file_path.SetValue(file_path)

        items = BOMExtractor.extract_from_schematic(file_path)
        if not items:
            wx.MessageBox(
                f"No se encontraron componentes en el esquemático:\n{file_path}",
                "Esquemático Vacío",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        self.bom_items = items
        self._apply_filter_and_refresh()
        self._start_live_pricing()

    def _start_live_pricing(self):
        """Run batch pricing in a background thread with progress feedback."""
        if self.is_fetching:
            return

        self.is_fetching = True
        self.progress_bar.SetRange(len(self.bom_items))
        self.progress_bar.SetValue(0)
        self.progress_bar.Show()
        self.Layout()
        self._update_ui_state()

        def worker():
            def on_prog(curr, total, itm):
                wx.CallAfter(self._on_item_priced, curr, total, itm)

            self.api_client.match_bom_items(self.bom_items, on_progress=on_prog)
            wx.CallAfter(self._on_pricing_complete)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _on_item_priced(self, curr: int, total: int, itm: BOMItem):
        self.progress_bar.SetValue(curr)
        self._apply_filter_and_refresh()

    def _on_pricing_complete(self):
        self.is_fetching = False
        self.progress_bar.Hide()
        self.Layout()
        self._apply_filter_and_refresh()
        self._update_ui_state()

    def _apply_filter_and_refresh(self):
        query = self.search_ctrl.GetValue().strip().lower()
        status_filter = self.status_choice.GetSelection()

        self.displayed_items = []
        for itm in self.bom_items:
            # Status filter
            if status_filter == 1 and not itm.is_matched:
                continue
            elif status_filter == 2 and itm.is_matched:
                continue
            elif status_filter == 3 and not (itm.is_matched and itm.is_available):
                continue

            # Query filter
            if query:
                prod_title = itm.matched_product.title if itm.matched_product else ""
                target_str = (
                    f"{itm.references_str} {itm.value} {itm.footprint} {prod_title}"
                ).lower()
                if not all(tok in target_str for tok in query.split()):
                    continue

            self.displayed_items.append(itm)

        self._refresh_table()
        self._update_summary_card()

    def _refresh_table(self):
        self.list_ctrl.DeleteAllItems()

        for idx, itm in enumerate(self.displayed_items, 1):
            row = self.list_ctrl.InsertItem(idx - 1, str(idx))
            self.list_ctrl.SetItem(row, 1, str(itm.quantity))
            self.list_ctrl.SetItem(row, 2, itm.references_str)
            self.list_ctrl.SetItem(row, 3, itm.value)
            self.list_ctrl.SetItem(row, 4, itm.footprint)

            if itm.ignored:
                self.list_ctrl.SetItem(row, 5, "(Ignorado de cotización)")
                self.list_ctrl.SetItem(row, 6, "-")
                self.list_ctrl.SetItem(row, 7, "-")
                self.list_ctrl.SetItem(row, 8, "Ignorado")
                self.list_ctrl.SetItemTextColour(row, wx.Colour(140, 140, 140))
                self.list_ctrl.SetItemBackgroundColour(row, wx.Colour(245, 245, 245))
            elif itm.is_matched:
                self.list_ctrl.SetItem(row, 5, itm.matched_product.title)
                self.list_ctrl.SetItem(row, 6, f"Q {itm.unit_price:.2f}")
                self.list_ctrl.SetItem(row, 7, f"Q {itm.subtotal:.2f}")

                if itm.is_available:
                    self.list_ctrl.SetItem(row, 8, "✓ En Stock")
                    self.list_ctrl.SetItemTextColour(row, wx.Colour(0, 120, 0))
                    self.list_ctrl.SetItemBackgroundColour(row, wx.Colour(240, 252, 240))
                else:
                    self.list_ctrl.SetItem(row, 8, "⚠ Agotado")
                    self.list_ctrl.SetItemTextColour(row, wx.Colour(180, 20, 20))
                    self.list_ctrl.SetItemBackgroundColour(row, wx.Colour(255, 242, 242))
            else:
                self.list_ctrl.SetItem(row, 5, "(Buscando o no encontrado...)")
                self.list_ctrl.SetItem(row, 6, "-")
                self.list_ctrl.SetItem(row, 7, "-")
                self.list_ctrl.SetItem(row, 8, "-")
                self.list_ctrl.SetItemTextColour(row, wx.Colour(100, 100, 100))
                self.list_ctrl.SetItemBackgroundColour(row, wx.Colour(255, 255, 255))

    def _update_summary_card(self):
        active_items = [itm for itm in self.bom_items if not itm.ignored]
        total_qty = sum(itm.quantity for itm in active_items)
        total_cost = sum(itm.subtotal for itm in active_items)
        matched_count = sum(1 for itm in active_items if itm.is_matched)

        self.lbl_stats_components.SetLabel(
            f"Componentes: {total_qty} totales | {len(active_items)} líneas de BOM"
        )
        self.lbl_stats_matched.SetLabel(
            f"Cotizados con éxito: {matched_count} de {len(active_items)} productos en tienda"
        )
        self.lbl_total_price.SetLabel(f"Q {total_cost:.2f}")

    # -------------------------------------------------------------------------
    # Event Handlers
    # -------------------------------------------------------------------------
    def _on_open_clicked(self, _event):
        with wx.FileDialog(
            self,
            "Seleccionar Esquemático o Proyecto KiCad",
            wildcard="Archivos KiCad (*.kicad_sch;*.kicad_pro)|*.kicad_sch;*.kicad_pro|Esquemáticos (*.kicad_sch)|*.kicad_sch|Proyectos (*.kicad_pro)|*.kicad_pro|Todos los archivos (*.*)|*.*",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            path = fileDialog.GetPath()
            self.load_and_price_schematic(path)

    def _on_reprice_clicked(self, _event):
        if self.bom_items:
            self._start_live_pricing()

    def _on_filter_changed(self, _event):
        self._apply_filter_and_refresh()

    def _on_item_double_clicked(self, event):
        sel_idx = event.GetIndex()
        if sel_idx < len(self.displayed_items):
            itm = self.displayed_items[sel_idx]
            dlg = ProductPickerDialog(self, itm, self.api_client)
            if dlg.ShowModal() == wx.ID_OK:
                itm.matched_product = dlg.selected_product
                itm.ignored = dlg.ignore_item
                self._apply_filter_and_refresh()
            dlg.Destroy()

    def _on_item_right_clicked(self, event):
        sel_idx = event.GetIndex()
        if sel_idx >= len(self.displayed_items):
            return
        itm = self.displayed_items[sel_idx]

        menu = wx.Menu()
        m_pick = menu.Append(wx.ID_ANY, "🔍 Cambiar / Buscar producto alternativo...")
        m_web = menu.Append(wx.ID_ANY, "🌐 Ver producto en tienda web")
        menu.AppendSeparator()
        ignore_label = "Restaurar a la cotización" if itm.ignored else "Ignorar este componente"
        m_ignore = menu.Append(wx.ID_ANY, ignore_label)

        if not itm.matched_product:
            m_web.Enable(False)

        def on_pick(_e):
            dlg = ProductPickerDialog(self, itm, self.api_client)
            if dlg.ShowModal() == wx.ID_OK:
                itm.matched_product = dlg.selected_product
                itm.ignored = dlg.ignore_item
                self._apply_filter_and_refresh()
            dlg.Destroy()

        def on_web(_e):
            if itm.matched_product:
                webbrowser.open(itm.matched_product.full_url)

        def on_ignore(_e):
            itm.ignored = not itm.ignored
            self._apply_filter_and_refresh()

        self.Bind(wx.EVT_MENU, on_pick, m_pick)
        self.Bind(wx.EVT_MENU, on_web, m_web)
        self.Bind(wx.EVT_MENU, on_ignore, m_ignore)

        self.PopupMenu(menu)
        menu.Destroy()

    def _on_export_csv(self, _event):
        if not self.bom_items:
            return
        with wx.FileDialog(
            self,
            "Guardar Cotización en CSV",
            wildcard="Archivos CSV (*.csv)|*.csv",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
            defaultFile="Cotizacion_LaElectronica_BOM.csv",
        ) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            path = fileDialog.GetPath()
            if BOMExporter.export_csv(path, self.bom_items):
                wx.MessageBox(
                    f"Cotización exportada con éxito en:\n{path}",
                    "Exportación Exitosa",
                    wx.OK | wx.ICON_INFORMATION,
                    self,
                )
            else:
                wx.MessageBox(
                    f"Error al escribir archivo CSV en:\n{path}",
                    "Error de Exportación",
                    wx.OK | wx.ICON_ERROR,
                    self,
                )

    def _on_export_html(self, _event):
        if not self.bom_items:
            return
        proj_name = os.path.basename(self.current_file_path) if self.current_file_path else "Proyecto KiCad"
        with wx.FileDialog(
            self,
            "Guardar Reporte de Cotización HTML",
            wildcard="Páginas HTML (*.html)|*.html",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
            defaultFile="Reporte_Cotizacion_LaElectronica.html",
        ) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            path = fileDialog.GetPath()
            if BOMExporter.export_html(path, proj_name, self.bom_items):
                resp = wx.MessageBox(
                    f"Reporte HTML generado con éxito en:\n{path}\n\n¿Deseas abrirlo ahora en tu navegador?",
                    "Exportación Exitosa",
                    wx.YES_NO | wx.ICON_QUESTION,
                    self,
                )
                if resp == wx.YES:
                    webbrowser.open(f"file://{os.path.abspath(path)}")
            else:
                wx.MessageBox(
                    f"Error al escribir archivo HTML en:\n{path}",
                    "Error de Exportación",
                    wx.OK | wx.ICON_ERROR,
                    self,
                )
