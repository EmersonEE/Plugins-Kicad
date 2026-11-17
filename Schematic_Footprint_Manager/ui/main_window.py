"""Main Window GUI for Schematic Footprint Manager."""

import os
import re
import wx
from typing import Dict, List, Optional, Set, Tuple

from core.parser import SchematicProject, SchematicSymbol
from core.footprint_library import FootprintLibraryManager
from ui.library_dialog import FootprintBrowserDialog


class ComponentTableItem:
    """Represents a row in the GUI table."""

    def __init__(self, symbol: SchematicSymbol):
        self.symbol = symbol
        self.checked: bool = False
        self.new_footprint: Optional[str] = None

    @property
    def is_modified(self) -> bool:
        return (
            self.new_footprint is not None
            and self.new_footprint != self.symbol.footprint
        )

    @property
    def effective_footprint(self) -> str:
        return (
            self.new_footprint
            if self.new_footprint is not None
            else self.symbol.footprint
        )


class MainWindow(wx.Frame):
    """Main application frame for Schematic Footprint Manager."""

    def __init__(self, initial_path: Optional[str] = None):
        super().__init__(
            parent=None,
            title="Schematic Footprint Manager - KiCad",
            size=(1180, 740),
            style=wx.DEFAULT_FRAME_STYLE,
        )
        self.SetMinSize((880, 560))

        self.project: Optional[SchematicProject] = None
        self.library_manager = FootprintLibraryManager()
        self.items: List[ComponentTableItem] = []
        self.displayed_indices: List[int] = []  # indices into self.items

        self._init_ui()

        # Start indexing footprint libraries in background thread
        wx.CallAfter(self._async_index_libraries)

        if initial_path and (
            initial_path.endswith(".kicad_sch")
            or initial_path.endswith(".kicad_pro")
        ):
            self.open_project(initial_path)

    def _init_ui(self):
        main_pnl = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ---------------------------------------------------------------------
        # 1. Barra Superior: Carga de Archivos / Proyecto
        # ---------------------------------------------------------------------
        file_box = wx.StaticBox(main_pnl, label=" 1. Proyecto o Esquemático de KiCad ")
        file_sizer = wx.StaticBoxSizer(file_box, wx.HORIZONTAL)

        self.btn_open = wx.Button(main_pnl, label="📂 Abrir Esquemático / Proyecto")
        self.txt_file_path = wx.TextCtrl(
            main_pnl, style=wx.TE_READONLY | wx.BORDER_SUNKEN
        )
        self.txt_file_path.SetHint("Selecciona un archivo .kicad_sch o .kicad_pro...")
        self.btn_reload = wx.Button(main_pnl, label="🔄 Recargar")

        self.btn_open.Bind(wx.EVT_BUTTON, self._on_open_clicked)
        self.btn_reload.Bind(wx.EVT_BUTTON, self._on_reload_clicked)

        file_sizer.Add(self.btn_open, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 8)
        file_sizer.Add(self.txt_file_path, 1, wx.RIGHT | wx.EXPAND, 8)
        file_sizer.Add(self.btn_reload, 0, wx.ALIGN_CENTER_VERTICAL)
        main_sizer.Add(file_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # ---------------------------------------------------------------------
        # 2. Barra de Filtros y Selección Rápida
        # ---------------------------------------------------------------------
        filter_pnl = wx.Panel(main_pnl)
        filter_sizer = wx.BoxSizer(wx.HORIZONTAL)

        search_lbl = wx.StaticText(filter_pnl, label="🔍 Filtrar:")
        self.search_filter = wx.SearchCtrl(filter_pnl, style=wx.TE_PROCESS_ENTER)
        self.search_filter.ShowCancelButton(True)
        self.search_filter.SetDescriptiveText("Buscar por referencia (R1), valor (10k), huella...")

        prefix_lbl = wx.StaticText(filter_pnl, label="Prefijo:")
        self.prefix_choice = wx.Choice(
            filter_pnl,
            choices=[
                "(Todos)",
                "R (Resistores)",
                "C (Capacitores)",
                "U / IC (Circuitos integrados)",
                "D (Diodos / LEDs)",
                "Q (Transistores / MOSFETs)",
                "J (Conectores / Pines)",
                "L (Inductores)",
                "SW / K (Switches / Relés)",
            ],
        )
        self.prefix_choice.SetSelection(0)

        self.chk_include_power = wx.CheckBox(
            filter_pnl, label="Incluir alimentación (#PWR, GND...)"
        )
        self.chk_include_power.SetValue(False)

        filter_sizer.Add(search_lbl, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        filter_sizer.Add(self.search_filter, 1, wx.RIGHT | wx.EXPAND, 10)
        filter_sizer.Add(prefix_lbl, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        filter_sizer.Add(self.prefix_choice, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 10)
        filter_sizer.Add(self.chk_include_power, 0, wx.ALIGN_CENTER_VERTICAL)
        filter_pnl.SetSizer(filter_sizer)
        main_sizer.Add(filter_pnl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # ---------------------------------------------------------------------
        # 3. Botones de Selección Rápida y Tabla Principal
        # ---------------------------------------------------------------------
        table_box = wx.StaticBox(main_pnl, label=" 2. Lista de Componentes del Esquemático ")
        table_sizer = wx.StaticBoxSizer(table_box, wx.VERTICAL)

        quick_sel_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_select_all = wx.Button(main_pnl, label="☑ Marcar todos")
        self.btn_select_none = wx.Button(main_pnl, label="☐ Desmarcar todos")
        self.btn_select_invert = wx.Button(main_pnl, label="⇄ Invertir")
        self.btn_select_same_val = wx.Button(main_pnl, label="🎯 Mismo Valor")
        self.btn_select_same_fp = wx.Button(main_pnl, label="🏷 Misma Huella")

        self.btn_select_all.Bind(wx.EVT_BUTTON, self._on_select_all)
        self.btn_select_none.Bind(wx.EVT_BUTTON, self._on_select_none)
        self.btn_select_invert.Bind(wx.EVT_BUTTON, self._on_select_invert)
        self.btn_select_same_val.Bind(wx.EVT_BUTTON, self._on_select_same_value)
        self.btn_select_same_fp.Bind(wx.EVT_BUTTON, self._on_select_same_footprint)

        quick_sel_row.Add(self.btn_select_all, 0, wx.RIGHT, 4)
        quick_sel_row.Add(self.btn_select_none, 0, wx.RIGHT, 4)
        quick_sel_row.Add(self.btn_select_invert, 0, wx.RIGHT, 10)
        quick_sel_row.Add(self.btn_select_same_val, 0, wx.RIGHT, 4)
        quick_sel_row.Add(self.btn_select_same_fp, 0, wx.RIGHT, 10)

        self.selection_count_lbl = wx.StaticText(
            main_pnl, label="Seleccionados: 0 de 0 componentes."
        )
        self.selection_count_lbl.SetFont(self.selection_count_lbl.GetFont().Bold())
        quick_sel_row.Add(
            self.selection_count_lbl, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10
        )

        table_sizer.Add(quick_sel_row, 0, wx.EXPAND | wx.ALL, 6)

        # ListCtrl con checkboxes
        self.list_ctrl = wx.ListCtrl(
            main_pnl,
            style=wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_VRULES | wx.LC_HRULES,
        )
        self.list_ctrl.EnableCheckBoxes(True)

        self.list_ctrl.InsertColumn(0, "Sel", wx.LIST_FORMAT_CENTER, 45)
        self.list_ctrl.InsertColumn(1, "Referencia", wx.LIST_FORMAT_CENTER, 85)
        self.list_ctrl.InsertColumn(2, "Valor", wx.LIST_FORMAT_LEFT, 120)
        self.list_ctrl.InsertColumn(3, "Huella Actual", wx.LIST_FORMAT_LEFT, 300)
        self.list_ctrl.InsertColumn(4, "Nueva Huella (Pendiente)", wx.LIST_FORMAT_LEFT, 320)
        self.list_ctrl.InsertColumn(5, "Hoja Esquemática", wx.LIST_FORMAT_LEFT, 150)
        self.list_ctrl.InsertColumn(6, "Símbolo (Lib ID)", wx.LIST_FORMAT_LEFT, 180)

        table_sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, 6)
        main_sizer.Add(table_sizer, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # ---------------------------------------------------------------------
        # 4. Panel de Asignación en Lote (Batch Assign Panel)
        # ---------------------------------------------------------------------
        assign_box = wx.StaticBox(main_pnl, label=" 3. Asignación de Nueva Huella a Componentes Seleccionados ")
        assign_sizer = wx.StaticBoxSizer(assign_box, wx.VERTICAL)

        assign_row = wx.BoxSizer(wx.HORIZONTAL)
        new_fp_lbl = wx.StaticText(main_pnl, label="Nueva Huella:")
        new_fp_lbl.SetFont(new_fp_lbl.GetFont().Bold())

        self.txt_target_fp = wx.TextCtrl(main_pnl)
        self.txt_target_fp.SetHint("Escribe o selecciona la huella (ej: Resistor_SMD:R_0805_2012Metric)...")

        self.btn_browse_lib = wx.Button(main_pnl, label="🔍 Explorar Librerías...")
        self.btn_browse_lib.Bind(wx.EVT_BUTTON, self._on_browse_libraries)

        self.used_fp_choice = wx.Choice(main_pnl, choices=["(Huellas en este esquemático)"])
        self.used_fp_choice.SetSelection(0)
        self.used_fp_choice.Bind(wx.EVT_CHOICE, self._on_used_fp_selected)

        self.btn_apply_fp = wx.Button(main_pnl, label="⚡ Asignar a Seleccionados")
        self.btn_apply_fp.SetFont(self.btn_apply_fp.GetFont().Bold())
        self.btn_apply_fp.SetBackgroundColour(wx.Colour(225, 245, 225))
        self.btn_apply_fp.Bind(wx.EVT_BUTTON, self._on_apply_footprint)

        self.btn_revert_selected = wx.Button(main_pnl, label="↺ Revertir Seleccionados")
        self.btn_revert_selected.Bind(wx.EVT_BUTTON, self._on_revert_selected)

        assign_row.Add(new_fp_lbl, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 8)
        assign_row.Add(self.txt_target_fp, 1, wx.RIGHT | wx.EXPAND, 8)
        assign_row.Add(self.btn_browse_lib, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 8)
        assign_row.Add(self.used_fp_choice, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 8)
        assign_row.Add(self.btn_apply_fp, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        assign_row.Add(self.btn_revert_selected, 0, wx.ALIGN_CENTER_VERTICAL)

        assign_sizer.Add(assign_row, 0, wx.EXPAND | wx.ALL, 6)
        main_sizer.Add(assign_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # ---------------------------------------------------------------------
        # 5. Barra Inferior de Acciones y Guardado
        # ---------------------------------------------------------------------
        bottom_row = wx.BoxSizer(wx.HORIZONTAL)
        self.chk_backup = wx.CheckBox(main_pnl, label="Crear copia de respaldo (.bak)")
        self.chk_backup.SetValue(True)

        self.status_msg = wx.StaticText(
            main_pnl, label="Listo. Abre un esquemático o proyecto para comenzar."
        )
        self.status_msg.SetForegroundColour(wx.Colour(100, 100, 100))

        self.btn_revert_all = wx.Button(main_pnl, label="Revertir Todo")
        self.btn_revert_all.Bind(wx.EVT_BUTTON, self._on_revert_all)

        self.btn_save = wx.Button(main_pnl, label="💾 Guardar Cambios en Esquemático")
        self.btn_save.SetFont(self.btn_save.GetFont().Bold())
        self.btn_save.SetBackgroundColour(wx.Colour(215, 235, 255))
        self.btn_save.Bind(wx.EVT_BUTTON, self._on_save_clicked)

        bottom_row.Add(self.chk_backup, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 16)
        bottom_row.Add(self.status_msg, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        bottom_row.Add(self.btn_revert_all, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 8)
        bottom_row.Add(self.btn_save, 0, wx.ALIGN_CENTER_VERTICAL)

        main_sizer.Add(bottom_row, 0, wx.EXPAND | wx.ALL, 10)

        main_pnl.SetSizer(main_sizer)

        # Event bindings
        self.search_filter.Bind(wx.EVT_TEXT, self._on_filter_changed)
        self.search_filter.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, self._on_filter_clear)
        self.prefix_choice.Bind(wx.EVT_CHOICE, self._on_filter_changed)
        self.chk_include_power.Bind(wx.EVT_CHECKBOX, self._on_filter_changed)

        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_CHECKED, self._on_item_checked)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_UNCHECKED, self._on_item_unchecked)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_item_activated)

        self._update_ui_state()

    def _async_index_libraries(self):
        """Index KiCad footprint libraries in background so GUI is instantly responsive."""
        def run():
            self.library_manager.discover_and_index()
            wx.CallAfter(self._on_libraries_indexed)

        import threading
        t = threading.Thread(target=run, daemon=True)
        t.start()

    def _on_libraries_indexed(self):
        total = len(self.library_manager.footprints)
        libs = len(self.library_manager.libraries)
        self.status_msg.SetLabel(
            f"Librerías indexadas: {total} huellas en {libs} librerías disponibles."
        )

    def open_project(self, file_path: str):
        """Load and display the specified schematic or project."""
        self.txt_file_path.SetValue(file_path)
        self.project = SchematicProject(file_path)
        if not self.project.load():
            wx.MessageBox(
                f"No se pudo cargar el archivo esquemático:\n{file_path}",
                "Error al abrir",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        include_power = self.chk_include_power.GetValue()
        symbols = self.project.get_all_symbols(include_power=include_power)
        self.items = [ComponentTableItem(s) for s in symbols]

        # Update used footprints dropdown
        used_fps = sorted({s.footprint for s in symbols if s.footprint})
        choices = ["(Huellas en este esquemático)"] + used_fps
        self.used_fp_choice.Clear()
        self.used_fp_choice.Append(choices)
        self.used_fp_choice.SetSelection(0)

        self._apply_filter_and_refresh()
        self.status_msg.SetLabel(
            f"Cargadas {len(self.project.sheets)} hoja(s) con {len(self.items)} componentes."
        )

    def _apply_filter_and_refresh(self):
        """Filter items based on search text, prefix, and power checkbox, and update ListCtrl."""
        query = self.search_filter.GetValue().strip().lower()
        prefix_idx = self.prefix_choice.GetSelection()
        prefix_filter = ""
        if prefix_idx > 0:
            prefix_str = self.prefix_choice.GetString(prefix_idx)
            m = re.match(r"^([A-Za-z_]+)", prefix_str)
            if m:
                prefix_filter = m.group(1).upper()

        include_power = self.chk_include_power.GetValue()

        self.displayed_indices = []
        for idx, itm in enumerate(self.items):
            if not include_power and itm.symbol.is_power:
                continue

            if prefix_filter:
                if prefix_filter == "SW":
                    if itm.symbol.prefix not in ("SW", "K"):
                        continue
                elif prefix_filter == "U":
                    if itm.symbol.prefix not in ("U", "IC"):
                        continue
                elif itm.symbol.prefix != prefix_filter:
                    continue

            if query:
                search_target = (
                    f"{itm.symbol.reference} {itm.symbol.value} "
                    f"{itm.effective_footprint} {itm.symbol.sheet_name} "
                    f"{itm.symbol.lib_id}"
                ).lower()
                if not all(tok in search_target for tok in query.split()):
                    continue

            self.displayed_indices.append(idx)

        self._refresh_table()

    def _refresh_table(self):
        """Update ListCtrl rows with current displayed items."""
        self.list_ctrl.DeleteAllItems()

        for row_idx, item_idx in enumerate(self.displayed_indices):
            itm = self.items[item_idx]
            self.list_ctrl.InsertItem(row_idx, "")
            self.list_ctrl.CheckItem(row_idx, itm.checked)
            self.list_ctrl.SetItem(row_idx, 1, itm.symbol.reference)
            self.list_ctrl.SetItem(row_idx, 2, itm.symbol.value)
            self.list_ctrl.SetItem(row_idx, 3, itm.symbol.footprint)

            if itm.is_modified:
                self.list_ctrl.SetItem(row_idx, 4, f"➜ {itm.new_footprint}")
                self.list_ctrl.SetItemTextColour(row_idx, wx.Colour(0, 130, 0))
                self.list_ctrl.SetItemBackgroundColour(row_idx, wx.Colour(235, 255, 235))
            else:
                self.list_ctrl.SetItem(row_idx, 4, "(Sin cambios)")
                self.list_ctrl.SetItemTextColour(row_idx, wx.Colour(0, 0, 0))
                self.list_ctrl.SetItemBackgroundColour(row_idx, wx.Colour(255, 255, 255))

            self.list_ctrl.SetItem(row_idx, 5, itm.symbol.sheet_name)
            self.list_ctrl.SetItem(row_idx, 6, itm.symbol.lib_id)

        self._update_selection_counter()
        self._update_ui_state()

    def _update_selection_counter(self):
        selected_count = sum(1 for itm in self.items if itm.checked)
        modified_count = sum(1 for itm in self.items if itm.is_modified)
        total = len(self.items)
        disp_total = len(self.displayed_indices)

        self.selection_count_lbl.SetLabel(
            f"Seleccionados: {selected_count} | Modificados: {modified_count} | Visibles: {disp_total} de {total}"
        )

    def _update_ui_state(self):
        has_items = bool(self.items)
        has_selection = any(itm.checked for itm in self.items)
        has_modifications = any(itm.is_modified for itm in self.items)

        self.btn_select_all.Enable(has_items)
        self.btn_select_none.Enable(has_items)
        self.btn_select_invert.Enable(has_items)
        self.btn_select_same_val.Enable(has_items)
        self.btn_select_same_fp.Enable(has_items)
        self.btn_apply_fp.Enable(has_selection)
        self.btn_revert_selected.Enable(has_selection)
        self.btn_revert_all.Enable(has_modifications)
        self.btn_save.Enable(has_modifications)

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
            self.open_project(path)

    def _on_reload_clicked(self, _event):
        path = self.txt_file_path.GetValue()
        if path and os.path.isfile(path):
            self.open_project(path)

    def _on_filter_changed(self, _event):
        self._apply_filter_and_refresh()

    def _on_filter_clear(self, _event):
        self.search_filter.SetValue("")
        self._apply_filter_and_refresh()

    def _on_item_checked(self, event):
        row_idx = event.GetIndex()
        if row_idx < len(self.displayed_indices):
            item_idx = self.displayed_indices[row_idx]
            self.items[item_idx].checked = True
            self._update_selection_counter()
            self._update_ui_state()

    def _on_item_unchecked(self, event):
        row_idx = event.GetIndex()
        if row_idx < len(self.displayed_indices):
            item_idx = self.displayed_indices[row_idx]
            self.items[item_idx].checked = False
            self._update_selection_counter()
            self._update_ui_state()

    def _on_item_activated(self, event):
        """Toggle checked state on double click."""
        row_idx = event.GetIndex()
        if row_idx < len(self.displayed_indices):
            curr = self.list_ctrl.IsItemChecked(row_idx)
            self.list_ctrl.CheckItem(row_idx, not curr)
            item_idx = self.displayed_indices[row_idx]
            self.items[item_idx].checked = not curr
            self._update_selection_counter()
            self._update_ui_state()

    def _on_select_all(self, _event):
        for idx in self.displayed_indices:
            self.items[idx].checked = True
        for row in range(self.list_ctrl.GetItemCount()):
            self.list_ctrl.CheckItem(row, True)
        self._update_selection_counter()
        self._update_ui_state()

    def _on_select_none(self, _event):
        for itm in self.items:
            itm.checked = False
        for row in range(self.list_ctrl.GetItemCount()):
            self.list_ctrl.CheckItem(row, False)
        self._update_selection_counter()
        self._update_ui_state()

    def _on_select_invert(self, _event):
        for idx in self.displayed_indices:
            self.items[idx].checked = not self.items[idx].checked
        for row in range(self.list_ctrl.GetItemCount()):
            item_idx = self.displayed_indices[row]
            self.list_ctrl.CheckItem(row, self.items[item_idx].checked)
        self._update_selection_counter()
        self._update_ui_state()

    def _on_select_same_value(self, _event):
        sel_row = self.list_ctrl.GetFirstSelected()
        if sel_row == -1 or sel_row >= len(self.displayed_indices):
            wx.MessageBox(
                "Selecciona primero una fila en la tabla como referencia de valor.",
                "Selección por Valor",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        ref_val = self.items[self.displayed_indices[sel_row]].symbol.value
        matched = 0
        for idx in self.displayed_indices:
            if self.items[idx].symbol.value == ref_val:
                self.items[idx].checked = True
                matched += 1

        for row in range(self.list_ctrl.GetItemCount()):
            item_idx = self.displayed_indices[row]
            self.list_ctrl.CheckItem(row, self.items[item_idx].checked)

        self._update_selection_counter()
        self._update_ui_state()
        self.status_msg.SetLabel(f"Seleccionados {matched} componentes con valor '{ref_val}'.")

    def _on_select_same_footprint(self, _event):
        sel_row = self.list_ctrl.GetFirstSelected()
        if sel_row == -1 or sel_row >= len(self.displayed_indices):
            wx.MessageBox(
                "Selecciona primero una fila en la tabla como referencia de huella.",
                "Selección por Huella",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        ref_fp = self.items[self.displayed_indices[sel_row]].symbol.footprint
        matched = 0
        for idx in self.displayed_indices:
            if self.items[idx].symbol.footprint == ref_fp:
                self.items[idx].checked = True
                matched += 1

        for row in range(self.list_ctrl.GetItemCount()):
            item_idx = self.displayed_indices[row]
            self.list_ctrl.CheckItem(row, self.items[item_idx].checked)

        self._update_selection_counter()
        self._update_ui_state()
        self.status_msg.SetLabel(f"Seleccionados {matched} componentes con huella '{ref_fp}'.")

    def _on_browse_libraries(self, _event):
        initial_search = self.txt_target_fp.GetValue().strip()
        dlg = FootprintBrowserDialog(
            self, self.library_manager, initial_search=initial_search
        )
        if dlg.ShowModal() == wx.ID_OK and dlg.selected_footprint:
            self.txt_target_fp.SetValue(dlg.selected_footprint)
        dlg.Destroy()

    def _on_used_fp_selected(self, _event):
        idx = self.used_fp_choice.GetSelection()
        if idx > 0:
            fp_str = self.used_fp_choice.GetString(idx)
            self.txt_target_fp.SetValue(fp_str)

    def _on_apply_footprint(self, _event):
        new_fp = self.txt_target_fp.GetValue().strip()
        if not new_fp:
            wx.MessageBox(
                "Ingresa o selecciona una huella antes de asignar.",
                "Asignar Huella",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        selected_items = [itm for itm in self.items if itm.checked]
        if not selected_items:
            wx.MessageBox(
                "No hay componentes marcados con casilla de verificación.",
                "Asignar Huella",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        count = 0
        for itm in selected_items:
            itm.new_footprint = new_fp
            count += 1

        self._refresh_table()
        self.status_msg.SetLabel(
            f"Asignada huella '{new_fp}' a {count} componentes seleccionados."
        )

    def _on_revert_selected(self, _event):
        for itm in self.items:
            if itm.checked:
                itm.new_footprint = None
        self._refresh_table()
        self.status_msg.SetLabel("Huellas revertidas en los componentes seleccionados.")

    def _on_revert_all(self, _event):
        for itm in self.items:
            itm.new_footprint = None
        self._refresh_table()
        self.status_msg.SetLabel("Todas las modificaciones han sido revertidas.")

    def _on_save_clicked(self, _event):
        if not self.project:
            return

        modified_items = [itm for itm in self.items if itm.is_modified]
        if not modified_items:
            wx.MessageBox(
                "No hay modificaciones pendientes de guardar.",
                "Guardar Esquemático",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        # Prepare confirmation breakdown
        summary_lines = []
        for itm in modified_items[:15]:
            summary_lines.append(
                f"  [{itm.symbol.reference}] ({itm.symbol.value}): '{itm.symbol.footprint}' ➜ '{itm.new_footprint}'"
            )
        if len(modified_items) > 15:
            summary_lines.append(f"  ... y {len(modified_items) - 15} componentes más.")

        msg = (
            f"Se aplicarán cambios en {len(modified_items)} componentes del esquemático:\n\n"
            + "\n".join(summary_lines)
            + "\n\n¿Deseas guardar los cambios en disco?"
        )

        dlg = wx.MessageDialog(
            self, msg, "Confirmar Guardado de Huellas", wx.YES_NO | wx.ICON_QUESTION
        )
        if dlg.ShowModal() != wx.ID_YES:
            dlg.Destroy()
            return
        dlg.Destroy()

        make_backup = self.chk_backup.GetValue()

        # Build update dictionary: (sheet_path, reference) -> new_footprint
        updates = {}
        for itm in modified_items:
            updates[(itm.symbol.sheet_file, itm.symbol.reference)] = itm.new_footprint

        ok, count, errors = self.project.apply_footprint_updates(
            updates, make_backup=make_backup
        )

        if ok:
            backup_msg = (
                " (Se crearon copias de seguridad .bak)" if make_backup else ""
            )
            wx.MessageBox(
                f"¡Guardado exitoso! Se actualizaron {count} instancias en los esquemáticos.{backup_msg}",
                "Guardado Completado",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            # Reload fresh project state
            self.open_project(self.project.root_file)
        else:
            wx.MessageBox(
                f"Ocurrieron errores al guardar:\n\n" + "\n".join(errors),
                "Error al Guardar",
                wx.OK | wx.ICON_ERROR,
                self,
            )
