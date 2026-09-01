"""Footprint Library Browser modal dialog."""

import wx
from typing import List, Optional
from core.footprint_library import FootprintItem, FootprintLibraryManager


class FootprintBrowserDialog(wx.Dialog):
    """Interactive modal dialog to search and pick footprints from KiCad libraries."""

    def __init__(self, parent, library_manager: FootprintLibraryManager, initial_search: str = ""):
        super().__init__(
            parent,
            title="Explorador de Huellas (Footprints) de KiCad",
            size=(820, 560),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX,
        )
        self.SetMinSize((640, 420))
        self.library_manager = library_manager
        self.selected_footprint: Optional[str] = None
        self.current_results: List[FootprintItem] = []

        self._init_ui(initial_search)
        self._perform_search()

    def _init_ui(self, initial_search: str):
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Top Filter Bar
        top_pnl = wx.Panel(self)
        top_sizer = wx.BoxSizer(wx.HORIZONTAL)

        search_lbl = wx.StaticText(top_pnl, label="🔍 Buscar huella:")
        self.search_ctrl = wx.SearchCtrl(top_pnl, style=wx.TE_PROCESS_ENTER)
        self.search_ctrl.ShowCancelButton(True)
        self.search_ctrl.SetDescriptiveText("Ej: 0805, SOT-23, SOIC-8, LED, Terminal...")
        self.search_ctrl.SetValue(initial_search)

        lib_lbl = wx.StaticText(top_pnl, label="Librería:")
        libs = ["(Todas las librerías)"] + self.library_manager.get_library_names()
        self.lib_choice = wx.Choice(top_pnl, choices=libs)
        self.lib_choice.SetSelection(0)

        top_sizer.Add(search_lbl, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        top_sizer.Add(self.search_ctrl, 1, wx.RIGHT | wx.EXPAND, 12)
        top_sizer.Add(lib_lbl, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        top_sizer.Add(self.lib_choice, 0, wx.ALIGN_CENTER_VERTICAL)
        top_pnl.SetSizer(top_sizer)

        main_sizer.Add(top_pnl, 0, wx.EXPAND | wx.ALL, 10)

        # Results ListCtrl
        self.list_ctrl = wx.ListCtrl(
            self,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN | wx.LC_VRULES,
        )
        self.list_ctrl.InsertColumn(0, "#", wx.LIST_FORMAT_CENTER, 45)
        self.list_ctrl.InsertColumn(1, "Nombre de la Huella", wx.LIST_FORMAT_LEFT, 320)
        self.list_ctrl.InsertColumn(2, "Librería (.pretty)", wx.LIST_FORMAT_LEFT, 200)
        self.list_ctrl.InsertColumn(3, "Identificador Completo (KiCad)", wx.LIST_FORMAT_LEFT, 360)

        main_sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Status & Count bar
        self.status_lbl = wx.StaticText(self, label="Mostrando 0 huellas.")
        self.status_lbl.SetForegroundColour(wx.Colour(100, 100, 100))
        main_sizer.Add(self.status_lbl, 0, wx.ALL, 8)

        # Bottom Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_select = wx.Button(self, wx.ID_OK, label="✓ Seleccionar Huella")
        self.btn_select.SetDefault()
        btn_cancel = wx.Button(self, wx.ID_CANCEL, label="Cancelar")

        btn_sizer.Add(self.btn_select, 0, wx.RIGHT, 8)
        btn_sizer.Add(btn_cancel, 0)
        main_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.BOTTOM, 10)

        self.SetSizer(main_sizer)

        # Event bindings
        self.search_ctrl.Bind(wx.EVT_TEXT, self._on_search_changed)
        self.search_ctrl.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, self._on_search_clear)
        self.lib_choice.Bind(wx.EVT_CHOICE, self._on_library_changed)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_item_double_clicked)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_item_selected)
        self.btn_select.Bind(wx.EVT_BUTTON, self._on_select_clicked)

        self.btn_select.Enable(False)

    def _on_search_changed(self, _event):
        self._perform_search()

    def _on_search_clear(self, _event):
        self.search_ctrl.SetValue("")
        self._perform_search()

    def _on_library_changed(self, _event):
        self._perform_search()

    def _perform_search(self):
        query = self.search_ctrl.GetValue().strip()
        selected_lib_idx = self.lib_choice.GetSelection()
        lib_filter = ""
        if selected_lib_idx > 0:
            lib_filter = self.lib_choice.GetString(selected_lib_idx)

        self.current_results = self.library_manager.search(
            query=query, library_filter=lib_filter, limit=300
        )

        self.list_ctrl.DeleteAllItems()
        for idx, item in enumerate(self.current_results, 1):
            row = self.list_ctrl.InsertItem(idx - 1, str(idx))
            self.list_ctrl.SetItem(row, 1, item.fp_name)
            self.list_ctrl.SetItem(row, 2, item.lib_name)
            self.list_ctrl.SetItem(row, 3, item.full_id)

        count = len(self.current_results)
        if count == 0:
            self.status_lbl.SetLabel("No se encontraron huellas que coincidan con la búsqueda.")
        elif count >= 300:
            self.status_lbl.SetLabel(f"Mostrando las primeras {count} huellas coincidentes (refina la búsqueda si es necesario).")
        else:
            self.status_lbl.SetLabel(f"Se encontraron {count} huellas.")

        self.btn_select.Enable(False)

    def _on_item_selected(self, _event):
        sel_idx = self.list_ctrl.GetFirstSelected()
        if sel_idx != -1 and sel_idx < len(self.current_results):
            self.selected_footprint = self.current_results[sel_idx].full_id
            self.btn_select.Enable(True)
        else:
            self.btn_select.Enable(False)

    def _on_item_double_clicked(self, event):
        sel_idx = self.list_ctrl.GetFirstSelected()
        if sel_idx != -1 and sel_idx < len(self.current_results):
            self.selected_footprint = self.current_results[sel_idx].full_id
            self.EndModal(wx.ID_OK)

    def _on_select_clicked(self, event):
        sel_idx = self.list_ctrl.GetFirstSelected()
        if sel_idx != -1 and sel_idx < len(self.current_results):
            self.selected_footprint = self.current_results[sel_idx].full_id
            self.EndModal(wx.ID_OK)
        else:
            event.Skip()
