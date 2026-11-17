"""Dialog for searching and picking matching products from laelectronica.com.gt."""

import webbrowser
import wx
from typing import List, Optional

from core.bom_extractor import BOMItem, ProductMatch
from core.laelectronica_api import LaElectronicaClient


class ProductPickerDialog(wx.Dialog):
    """Modal dialog allowing users to pick an alternative product or search manually."""

    def __init__(
        self, parent, bom_item: BOMItem, api_client: LaElectronicaClient
    ):
        super().__init__(
            parent,
            title=f"Seleccionar Producto para {bom_item.value} ({bom_item.references_str})",
            size=(860, 560),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX,
        )
        self.SetMinSize((680, 440))
        self.bom_item = bom_item
        self.api_client = api_client
        self.selected_product: Optional[ProductMatch] = bom_item.matched_product
        self.current_results: List[ProductMatch] = []
        self.ignore_item: bool = bom_item.ignored

        self._init_ui()
        self._initial_search()

    def _init_ui(self):
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Header with BOM component information
        header_pnl = wx.Panel(self)
        header_sizer = wx.BoxSizer(wx.VERTICAL)

        comp_info = (
            f"Componente: {self.bom_item.value} | Cantidad: {self.bom_item.quantity} | "
            f"Referencias: {self.bom_item.references_str} | Huella: {self.bom_item.footprint}"
        )
        info_txt = wx.StaticText(header_pnl, label=comp_info)
        info_txt.SetFont(info_txt.GetFont().Bold())
        header_sizer.Add(info_txt, 0, wx.ALL, 6)
        header_pnl.SetSizer(header_sizer)
        main_sizer.Add(header_pnl, 0, wx.EXPAND | wx.ALL, 8)

        # Search Bar
        search_pnl = wx.Panel(self)
        search_sizer = wx.BoxSizer(wx.HORIZONTAL)

        search_lbl = wx.StaticText(search_pnl, label="🔍 Buscar en laelectronica.com.gt:")
        self.search_ctrl = wx.SearchCtrl(search_pnl, style=wx.TE_PROCESS_ENTER)
        self.search_ctrl.ShowCancelButton(True)
        default_query = self.bom_item.generate_search_queries()[0] if self.bom_item.generate_search_queries() else self.bom_item.value
        self.search_ctrl.SetValue(default_query)

        self.btn_search = wx.Button(search_pnl, label="Buscar")
        self.btn_search.Bind(wx.EVT_BUTTON, self._on_search_clicked)
        self.search_ctrl.Bind(wx.EVT_TEXT_ENTER, self._on_search_clicked)
        self.search_ctrl.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, lambda _e: self.search_ctrl.SetValue(""))

        search_sizer.Add(search_lbl, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        search_sizer.Add(self.search_ctrl, 1, wx.RIGHT | wx.EXPAND, 6)
        search_sizer.Add(self.btn_search, 0, wx.ALIGN_CENTER_VERTICAL)
        search_pnl.SetSizer(search_sizer)
        main_sizer.Add(search_pnl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Results Table
        self.list_ctrl = wx.ListCtrl(
            self,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN | wx.LC_VRULES,
        )
        self.list_ctrl.InsertColumn(0, "#", wx.LIST_FORMAT_CENTER, 40)
        self.list_ctrl.InsertColumn(1, "Título del Producto en Tienda", wx.LIST_FORMAT_LEFT, 420)
        self.list_ctrl.InsertColumn(2, "Precio Unit. (GTQ)", wx.LIST_FORMAT_RIGHT, 130)
        self.list_ctrl.InsertColumn(3, "Subtotal (Q)", wx.LIST_FORMAT_RIGHT, 110)
        self.list_ctrl.InsertColumn(4, "Disponibilidad", wx.LIST_FORMAT_CENTER, 100)

        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_item_selected)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_item_double_clicked)

        main_sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Action links & Status
        mid_row = wx.BoxSizer(wx.HORIZONTAL)
        self.status_lbl = wx.StaticText(self, label="Buscando...")
        self.status_lbl.SetForegroundColour(wx.Colour(100, 100, 100))

        self.btn_open_web = wx.Button(self, label="🌐 Ver en Tienda Web")
        self.btn_open_web.Bind(wx.EVT_BUTTON, self._on_open_web_clicked)
        self.btn_open_web.Enable(False)

        mid_row.Add(self.status_lbl, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)
        mid_row.Add(self.btn_open_web, 0, wx.ALL, 6)
        main_sizer.Add(mid_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        # Bottom Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.chk_ignore = wx.CheckBox(self, label="Ignorar este componente de la cotización")
        self.chk_ignore.SetValue(self.bom_item.ignored)

        self.btn_select = wx.Button(self, wx.ID_OK, label="✓ Asignar Producto")
        self.btn_select.SetDefault()
        self.btn_select.Bind(wx.EVT_BUTTON, self._on_select_clicked)

        btn_cancel = wx.Button(self, wx.ID_CANCEL, label="Cancelar")

        btn_sizer.Add(self.chk_ignore, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)
        btn_sizer.AddStretchSpacer(1)
        btn_sizer.Add(self.btn_select, 0, wx.RIGHT, 6)
        btn_sizer.Add(btn_cancel, 0, wx.RIGHT, 10)

        main_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(main_sizer)

    def _initial_search(self):
        queries = self.bom_item.generate_search_queries()
        _, candidates = self.api_client.find_best_match(queries)
        self._populate_results(candidates)

    def _on_search_clicked(self, _event):
        q = self.search_ctrl.GetValue().strip()
        if not q:
            return
        self.status_lbl.SetLabel("Consultando tienda...")
        wx.Yield()
        results = self.api_client.search_products(q)
        self._populate_results(results)

    def _populate_results(self, products: List[ProductMatch]):
        self.current_results = products
        self.list_ctrl.DeleteAllItems()

        qty = self.bom_item.quantity
        for idx, p in enumerate(products, 1):
            row = self.list_ctrl.InsertItem(idx - 1, str(idx))
            self.list_ctrl.SetItem(row, 1, p.title)
            self.list_ctrl.SetItem(row, 2, f"Q {p.price:.2f}")
            self.list_ctrl.SetItem(row, 3, f"Q {p.price * qty:.2f}")
            stock_txt = "En Stock" if p.available else "Agotado"
            self.list_ctrl.SetItem(row, 4, stock_txt)

            if p.available:
                self.list_ctrl.SetItemTextColour(row, wx.Colour(0, 120, 0))
            else:
                self.list_ctrl.SetItemTextColour(row, wx.Colour(180, 0, 0))

        if products:
            self.status_lbl.SetLabel(f"Se encontraron {len(products)} productos en laelectronica.com.gt.")
            self.list_ctrl.Select(0)
            self.selected_product = products[0]
            self.btn_open_web.Enable(True)
        else:
            self.status_lbl.SetLabel("No se encontraron productos con ese término de búsqueda.")
            self.btn_open_web.Enable(False)

    def _on_item_selected(self, _event):
        sel_idx = self.list_ctrl.GetFirstSelected()
        if sel_idx != -1 and sel_idx < len(self.current_results):
            self.selected_product = self.current_results[sel_idx]
            self.btn_open_web.Enable(True)
        else:
            self.btn_open_web.Enable(False)

    def _on_item_double_clicked(self, _event):
        self._on_select_clicked(None)

    def _on_open_web_clicked(self, _event):
        if self.selected_product:
            webbrowser.open(self.selected_product.full_url)

    def _on_select_clicked(self, _event):
        self.ignore_item = self.chk_ignore.GetValue()
        sel_idx = self.list_ctrl.GetFirstSelected()
        if sel_idx != -1 and sel_idx < len(self.current_results):
            self.selected_product = self.current_results[sel_idx]
        self.EndModal(wx.ID_OK)
