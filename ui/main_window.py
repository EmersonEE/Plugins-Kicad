"""Ventana Principal para la herramienta de Duplicación e Incremento de Etiquetas en KiCad."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import wx
from typing import Dict, List, Optional, Set, Tuple

from core.block_detector import BlockDetector, SchematicBlock
from core.block_duplicator import (
    BlockDuplicator,
    DuplicationConfig,
    DuplicationReport,
    KICAD_GRID_MM,
    snap_to_grid,
)
from core.hierarchical import HierarchicalManager
from core.label_renamer import LabelRenamer, RenamingRule
from core.project_backup import SafetyManager
from core.reference_annotator import ReferenceAnnotationMode
from core.sexpr import SExprParser, SExprSerializer, SNode
from ui.config_dialog import CONFIG_PATH, ConfigDialog


class MainWindow(wx.Frame):
    """Ventana principal de la aplicación con modos duales: Portapapeles y Archivo."""

    def __init__(self, initial_path: Optional[str] = None):
        super().__init__(
            parent=None,
            title="KiCad Block Duplicator & Label Incrementor",
            size=(1120, 760),
            style=wx.DEFAULT_FRAME_STYLE,
        )
        self.SetMinSize((850, 600))

        # Cargar configuración inicial
        self.config_data = self._load_config()

        # Estado del modo portapapeles
        self.clipboard_block: Optional[SchematicBlock] = None
        self.clipboard_raw_text: str = ""

        # Estado del modo archivo
        self.current_sch_path: Optional[str] = None
        self.sch_root: Optional[SNode] = None
        self.file_symbols: List[SNode] = []

        self._init_ui()

        # Intentar leer el portapapeles al iniciar automáticamente
        wx.CallAfter(self._auto_read_clipboard)

        if initial_path and initial_path.endswith(".kicad_sch"):
            wx.CallAfter(lambda: self._open_file(initial_path))

    def _load_config(self) -> dict:
        if os.path.isfile(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "num_copies": 4,
            "direction": "vertical",
            "pitch_y_mm": 50.8,
            "pitch_x_mm": 0.0,
            "annotation_mode": "question_mark",
            "auto_sync_parent_sheet": True,
            "grid_snap_mm": 1.27,
            "exceptions": [
                "+5V", "+3V3", "+3.3V", "+1.8V", "+12V", "+24V", "-12V", "-5V",
                "VCC", "VDD", "VSS", "VEE", "VBAT",
                "GND", "GNDA", "GNDD", "AGND", "DGND", "PGND", "EARTH", "0V"
            ]
        }

    def _init_ui(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # Barra de menú
        self._create_menu_bar()

        # Cuaderno de pestañas (Notebook)
        self.notebook = wx.Notebook(panel)

        self.tab_clipboard = wx.Panel(self.notebook)
        self._build_clipboard_tab(self.tab_clipboard)
        self.notebook.AddPage(self.tab_clipboard, "📋 Modo Portapapeles (Atajo Rápido / Wayland)")

        self.tab_file = wx.Panel(self.notebook)
        self._build_file_tab(self.tab_file)
        self.notebook.AddPage(self.tab_file, "📁 Modo Archivo (.kicad_sch)")

        vbox.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 8)

        # Barra de estado inferior
        self.status_bar = self.CreateStatusBar(2)
        self.status_bar.SetStatusWidths([-2, -1])
        self.status_bar.SetStatusText("Listo", 0)
        self.status_bar.SetStatusText("Grilla: 1.27 mm (50 mil)", 1)

        panel.SetSizer(vbox)

    def _create_menu_bar(self):
        menubar = wx.MenuBar()

        # Menú Archivo
        menu_file = wx.Menu()
        item_open = menu_file.Append(wx.ID_OPEN, "&Abrir Esquemático...\tCtrl+O")
        menu_file.AppendSeparator()
        item_exit = menu_file.Append(wx.ID_EXIT, "&Salir\tCtrl+Q")
        menubar.Append(menu_file, "&Archivo")

        # Menú Herramientas / Configuración
        menu_tools = wx.Menu()
        item_config = menu_tools.Append(wx.ID_PREFERENCES, "&Configuración y Excepciones...\tCtrl+,")
        menubar.Append(menu_tools, "&Herramientas")

        # Menú Ayuda
        menu_help = wx.Menu()
        item_shortcuts = menu_help.Append(wx.ID_ANY, "Atajos en Hyprland / Omarchy...")
        item_about = menu_help.Append(wx.ID_ABOUT, "Acerca de...")
        menubar.Append(menu_help, "A&yuda")

        self.SetMenuBar(menubar)

        self.Bind(wx.EVT_MENU, lambda e: self._on_menu_open(), item_open)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(), item_exit)
        self.Bind(wx.EVT_MENU, lambda e: self._on_menu_config(), item_config)
        self.Bind(wx.EVT_MENU, lambda e: self._show_hyprland_guide(), item_shortcuts)
        self.Bind(wx.EVT_MENU, lambda e: self._show_about(), item_about)

    # -------------------------------------------------------------------------
    # PESTAÑA 1: MODO PORTAPAPELES
    # -------------------------------------------------------------------------
    def _build_clipboard_tab(self, parent: wx.Panel):
        sizer = wx.BoxSizer(wx.VERTICAL)

        # 1. Barra de Captura del Portapapeles
        top_box = wx.StaticBox(parent, label=" 1. Captura del Bloque Copiado (Ctrl+C en KiCad) ")
        top_sizer = wx.StaticBoxSizer(top_box, wx.HORIZONTAL)

        self.btn_read_clip = wx.Button(parent, label="📋 Leer Portapapeles (wl-paste)")
        self.btn_read_clip.Bind(wx.EVT_BUTTON, lambda e: self._read_clipboard(show_msg=True))
        top_sizer.Add(self.btn_read_clip, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 6)

        self.lbl_clip_info = wx.StaticText(
            parent, label="Copia un bloque en KiCad con Ctrl+C y pulsa 'Leer Portapapeles'."
        )
        top_sizer.Add(self.lbl_clip_info, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 6)
        sizer.Add(top_sizer, 0, wx.EXPAND | wx.ALL, 6)

        # 2. Controles de Configuración de Duplicación
        params_box = wx.StaticBox(parent, label=" 2. Parámetros de Duplicación ")
        params_sizer = wx.StaticBoxSizer(params_box, wx.HORIZONTAL)

        # Número de copias N
        lbl_n = wx.StaticText(parent, label="Cantidad Total (N):")
        self.spin_n = wx.SpinCtrl(parent, value=str(self.config_data.get("num_copies", 4)), min=2, max=64)
        self.spin_n.Bind(wx.EVT_SPINCTRL, lambda e: self._update_clipboard_preview())
        params_sizer.Add(lbl_n, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        params_sizer.Add(self.spin_n, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 6)

        # Dirección
        lbl_dir = wx.StaticText(parent, label="Dirección:")
        self.choice_dir = wx.Choice(parent, choices=["Vertical (Hacia abajo)", "Horizontal (Derecha)", "Matriz / Cuadrícula"])
        self.choice_dir.SetSelection(0)
        self.choice_dir.Bind(wx.EVT_CHOICE, lambda e: self._update_clipboard_preview())
        params_sizer.Add(lbl_dir, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 12)
        params_sizer.Add(self.choice_dir, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 6)

        # Separación (Pitch)
        lbl_pitch = wx.StaticText(parent, label="Separación (mm):")
        self.spin_pitch = wx.SpinCtrlDouble(
            parent, value=str(self.config_data.get("pitch_y_mm", 50.8)),
            min=5.08, max=300.0, inc=1.27
        )
        self.spin_pitch.Bind(wx.EVT_SPINCTRLDOUBLE, lambda e: self._update_clipboard_preview())
        params_sizer.Add(lbl_pitch, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 12)
        params_sizer.Add(self.spin_pitch, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 6)

        # Anotación de Referencias
        lbl_ann = wx.StaticText(parent, label="Referencias:")
        self.choice_ann = wx.Choice(
            parent,
            choices=[
                "Opción B: Resetear a '?' (R?, U? - Anotar en KiCad)",
                "Secuencial automática (R7, R8...)"
            ]
        )
        self.choice_ann.SetSelection(0)
        self.choice_ann.Bind(wx.EVT_CHOICE, lambda e: self._update_clipboard_preview())
        params_sizer.Add(lbl_ann, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 12)
        params_sizer.Add(self.choice_ann, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 6)

        sizer.Add(params_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # 3. Tabla de Vista Previa (Dry-Run)
        prev_box = wx.StaticBox(parent, label=" 3. Vista Previa del Renombrado (Dry-Run) ")
        prev_sizer = wx.StaticBoxSizer(prev_box, wx.VERTICAL)

        self.list_clip_preview = wx.ListCtrl(parent, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        prev_sizer.Add(self.list_clip_preview, 1, wx.EXPAND | wx.ALL, 4)
        sizer.Add(prev_sizer, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # 4. Botón de Acción Principal
        btn_action_box = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_duplicate_clipboard = wx.Button(
            parent, label="⚡ Duplicar y Copiar al Portapapeles (wl-copy)", size=(-1, 42)
        )
        self.btn_duplicate_clipboard.SetFont(self.btn_duplicate_clipboard.GetFont().Bold())
        self.btn_duplicate_clipboard.Bind(wx.EVT_BUTTON, self._on_duplicate_clipboard_clicked)
        btn_action_box.Add(self.btn_duplicate_clipboard, 1, wx.EXPAND | wx.ALL, 6)
        sizer.Add(btn_action_box, 0, wx.EXPAND | wx.BOTTOM, 6)

        parent.SetSizer(sizer)

    # -------------------------------------------------------------------------
    # PESTAÑA 2: MODO ARCHIVO (.kicad_sch)
    # -------------------------------------------------------------------------
    def _build_file_tab(self, parent: wx.Panel):
        sizer = wx.BoxSizer(wx.VERTICAL)

        # 1. Barra de Selección de Archivo
        file_box = wx.StaticBox(parent, label=" 1. Archivo de Esquemático (.kicad_sch) ")
        file_sizer = wx.StaticBoxSizer(file_box, wx.HORIZONTAL)

        self.btn_browse_file = wx.Button(parent, label="📂 Abrir Esquemático")
        self.btn_browse_file.Bind(wx.EVT_BUTTON, lambda e: self._on_menu_open())
        self.txt_file_path = wx.TextCtrl(parent, style=wx.TE_READONLY | wx.BORDER_SUNKEN)
        self.txt_file_path.SetHint("Selecciona un archivo .kicad_sch...")
        self.btn_reload_file = wx.Button(parent, label="🔄 Recargar")
        self.btn_reload_file.Bind(wx.EVT_BUTTON, lambda e: self._reload_file())

        file_sizer.Add(self.btn_browse_file, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        file_sizer.Add(self.txt_file_path, 1, wx.RIGHT | wx.EXPAND, 6)
        file_sizer.Add(self.btn_reload_file, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(file_sizer, 0, wx.EXPAND | wx.ALL, 6)

        # 2. Selector de Componentes del Bloque
        comp_box = wx.StaticBox(parent, label=" 2. Componentes del Bloque a Duplicar ")
        comp_sizer = wx.StaticBoxSizer(comp_box, wx.VERTICAL)

        top_btns = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_sel_all = wx.Button(parent, label="Seleccionar Todo")
        self.btn_desel_all = wx.Button(parent, label="Deseleccionar")
        self.lbl_comp_count = wx.StaticText(parent, label="0 componentes cargados")
        self.btn_sel_all.Bind(wx.EVT_BUTTON, lambda e: self._select_all_file_symbols(True))
        self.btn_desel_all.Bind(wx.EVT_BUTTON, lambda e: self._select_all_file_symbols(False))

        top_btns.Add(self.btn_sel_all, 0, wx.RIGHT, 6)
        top_btns.Add(self.btn_desel_all, 0, wx.RIGHT, 12)
        top_btns.Add(self.lbl_comp_count, 0, wx.ALIGN_CENTER_VERTICAL)
        comp_sizer.Add(top_btns, 0, wx.ALL, 4)

        self.list_file_symbols = wx.CheckListBox(parent, style=wx.LB_MULTIPLE | wx.BORDER_SUNKEN)
        self.list_file_symbols.Bind(wx.EVT_CHECKLISTBOX, lambda e: self._update_file_preview())
        comp_sizer.Add(self.list_file_symbols, 1, wx.EXPAND | wx.ALL, 4)
        sizer.Add(comp_sizer, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # 3. Opciones de Seguridad y Sincronización
        sec_box = wx.StaticBox(parent, label=" 3. Opciones de Ejecución y Seguridad ")
        sec_sizer = wx.StaticBoxSizer(sec_box, wx.HORIZONTAL)

        self.chk_create_bak = wx.CheckBox(parent, label="Crear respaldo .bak automático antes de guardar")
        self.chk_create_bak.SetValue(True)
        self.chk_sync_parent = wx.CheckBox(parent, label="Sincronizar pines en hoja padre automáticamente")
        self.chk_sync_parent.SetValue(self.config_data.get("auto_sync_parent_sheet", True))

        sec_sizer.Add(self.chk_create_bak, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 6)
        sec_sizer.Add(self.chk_sync_parent, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 12)
        sizer.Add(sec_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # 4. Botones de Acción
        action_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_validate_erc = wx.Button(parent, label="🩺 Validar ERC con kicad-cli")
        self.btn_validate_erc.Bind(wx.EVT_BUTTON, self._on_validate_erc_clicked)
        self.btn_apply_file = wx.Button(parent, label="💾 Aplicar Duplicación al Archivo", size=(-1, 40))
        self.btn_apply_file.SetFont(self.btn_apply_file.GetFont().Bold())
        self.btn_apply_file.Bind(wx.EVT_BUTTON, self._on_apply_file_clicked)

        action_row.Add(self.btn_validate_erc, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 8)
        action_row.Add(self.btn_apply_file, 1, wx.EXPAND)
        sizer.Add(action_row, 0, wx.EXPAND | wx.ALL, 6)

        parent.SetSizer(sizer)

    # -------------------------------------------------------------------------
    # MÉTODOS DEL MODO PORTAPAPELES
    # -------------------------------------------------------------------------
    def _auto_read_clipboard(self):
        """Lee el portapapeles de manera silenciosa al iniciar."""
        self._read_clipboard(show_msg=False)

    def _read_clipboard(self, show_msg: bool = False):
        """Captura y procesa el portapapeles del sistema (wl-paste o wx)."""
        raw_text = BlockDetector.read_system_clipboard()

        if not raw_text:
            # Fallback a wx.Clipboard
            if wx.TheClipboard.Open():
                if wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_TEXT)):
                    data = wx.TextDataObject()
                    wx.TheClipboard.GetData(data)
                    raw_text = data.GetText()
                wx.TheClipboard.Close()

        if not raw_text or not raw_text.strip().startswith("("):
            self.lbl_clip_info.SetLabel("⚠️ El portapapeles no contiene elementos S-expressions de KiCad.")
            if show_msg:
                wx.MessageBox(
                    "No se detectó un bloque de KiCad en el portapapeles.\n\n"
                    "En KiCad Eeschema:\n"
                    "1. Selecciona con el ratón el bloque deseado.\n"
                    "2. Pulsa Ctrl+C.\n"
                    "3. Vuelve a esta ventana y pulsa 'Leer Portapapeles'.",
                    "Portapapeles Vacío o Incompatible",
                    wx.ICON_INFORMATION
                )
            return

        self.clipboard_raw_text = raw_text
        block = BlockDetector.from_clipboard_text(raw_text)

        if not block or (not block.symbols and not block.wires and not block.labels):
            self.lbl_clip_info.SetLabel("⚠️ No se encontraron componentes o cables en el portapapeles.")
            return

        self.clipboard_block = block
        num_syms = len(block.symbols)
        num_wires = len(block.wires)
        num_lbls = len(block.labels)

        # Extraer referencias detectadas
        refs = [s.get_prop("Reference") or "?" for s in block.symbols]
        refs_preview = ", ".join(refs[:8]) + ("..." if len(refs) > 8 else "")

        info_text = f"✅ Bloque detectado: {num_syms} componentes ({refs_preview}), {num_wires} cables, {num_lbls} etiquetas."
        self.lbl_clip_info.SetLabel(info_text)
        self.status_bar.SetStatusText(info_text, 0)

        self._update_clipboard_preview()

    def _update_clipboard_preview(self):
        """Actualiza la tabla de vista previa de la pestaña portapapeles."""
        self.list_clip_preview.ClearAll()
        if not self.clipboard_block:
            return

        n_copies = self.spin_n.GetValue()
        ann_mode = (
            ReferenceAnnotationMode.RESET_TO_QUESTION_MARK
            if self.choice_ann.GetSelection() == 0
            else ReferenceAnnotationMode.AUTO_SEQUENTIAL
        )

        cfg = DuplicationConfig(
            num_copies=n_copies,
            annotation_mode=ann_mode,
            renaming_rule=RenamingRule(exceptions=set(self.config_data.get("exceptions", [])))
        )
        duplicator = BlockDuplicator(cfg)

        # Configurar columnas de la tabla
        self.list_clip_preview.InsertColumn(0, "Tipo de Elemento", width=140)
        self.list_clip_preview.InsertColumn(1, "Original", width=120)
        for i in range(2, n_copies + 1):
            self.list_clip_preview.InsertColumn(i, f"Copia #{i}", width=110)

        row_idx = 0

        # Filas para etiquetas
        for node, lbl_type, orig_name in self.clipboard_block.labels:
            type_desc = {
                "hierarchical": "Etiqueta Jerárquica",
                "global": "Etiqueta Global",
                "local": "Etiqueta Local"
            }.get(lbl_type, "Etiqueta")

            self.list_clip_preview.InsertItem(row_idx, type_desc)
            self.list_clip_preview.SetItem(row_idx, 1, orig_name)

            for c_idx in range(2, n_copies + 1):
                new_val = duplicator.renamer.rename_label(orig_name, c_idx)
                self.list_clip_preview.SetItem(row_idx, c_idx, new_val)
            row_idx += 1

        # Filas para componentes (referencias)
        allocated_refs = {s.get_prop("Reference") for s in self.clipboard_block.symbols if s.get_prop("Reference")}
        prefix_counters = {}

        for sym in self.clipboard_block.symbols:
            orig_ref = sym.get_prop("Reference") or "?"
            val = sym.get_prop("Value") or ""
            desc = f"Componente ({val})"

            self.list_clip_preview.InsertItem(row_idx, desc)
            self.list_clip_preview.SetItem(row_idx, 1, orig_ref)

            temp_sym = sym.clone()
            for c_idx in range(2, n_copies + 1):
                from core.reference_annotator import ReferenceAnnotator
                new_ref = ReferenceAnnotator.annotate_for_copy(
                    temp_sym, c_idx, mode=ann_mode,
                    allocated_refs=allocated_refs,
                    prefix_counters=prefix_counters
                )
                self.list_clip_preview.SetItem(row_idx, c_idx, new_ref)
            row_idx += 1

    def _on_duplicate_clipboard_clicked(self, event):
        """Duplica el bloque en memoria y lo deposita en el portapapeles del sistema."""
        if not self.clipboard_block:
            wx.MessageBox("Primero debes leer un bloque válido desde el portapapeles.", "Aviso", wx.ICON_WARNING)
            return

        n_copies = self.spin_n.GetValue()
        dir_idx = self.choice_dir.GetSelection()
        direction = "vertical" if dir_idx == 0 else ("horizontal" if dir_idx == 1 else "matrix")
        pitch = self.spin_pitch.GetValue()
        ann_mode = (
            ReferenceAnnotationMode.RESET_TO_QUESTION_MARK
            if self.choice_ann.GetSelection() == 0
            else ReferenceAnnotationMode.AUTO_SEQUENTIAL
        )

        cfg = DuplicationConfig(
            num_copies=n_copies,
            direction=direction,
            pitch_y_mm=pitch if direction != "horizontal" else 0.0,
            pitch_x_mm=pitch if direction != "vertical" else 0.0,
            annotation_mode=ann_mode,
            renaming_rule=RenamingRule(exceptions=set(self.config_data.get("exceptions", [])))
        )

        duplicator = BlockDuplicator(cfg)
        report = duplicator.duplicate_block(self.clipboard_block)

        # Armar el texto resultante que KiCad espera
        # Todos los elementos originales + todos los elementos nuevos clonados
        all_elements = list(self.clipboard_block.items) + report.new_items

        # Si el texto original venía envuelto en (kicad_sch ...), recrear el contenedor
        nodes_orig = SExprParser.parse_many(self.clipboard_raw_text)
        if len(nodes_orig) == 1 and nodes_orig[0].tag == "kicad_sch":
            root = nodes_orig[0].clone()
            # Mantener encabezados y lib_symbols, agregar los nuevos items
            for item in report.new_items:
                root.add_child(item)
            output_sexpr = SExprSerializer.serialize(root)
        else:
            # Lista suelta de nodos S-expressions
            output_sexpr = SExprSerializer.serialize(all_elements)

        # Copiar al portapapeles del sistema mediante wl-copy y wx.TheClipboard
        copied_ok = False
        try:
            p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE, text=True)
            p.communicate(input=output_sexpr)
            if p.returncode == 0:
                copied_ok = True
        except Exception:
            pass

        if not copied_ok and wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(output_sexpr))
            wx.TheClipboard.Close()
            copied_ok = True

        msg = (
            f"🎉 ¡Éxito! El bloque se duplicó {n_copies} veces.\n\n"
            f"• Símbolos creados: {report.symbols_created}\n"
            f"• Etiquetas renombradas: {len(report.labels_renamed)}\n\n"
            "El resultado ya está en tu portapapeles.\n"
            "Ve a KiCad Eeschema y presiona Ctrl+V para ubicar el bloque duplicado."
        )
        wx.MessageBox(msg, "Duplicación Lista", wx.ICON_INFORMATION)
        self.status_bar.SetStatusText(f"Bloque duplicado x{n_copies} en portapapeles", 0)

    # -------------------------------------------------------------------------
    # MÉTODOS DEL MODO ARCHIVO (.kicad_sch)
    # -------------------------------------------------------------------------
    def _on_menu_open(self):
        wildcard = "Esquemáticos KiCad (*.kicad_sch)|*.kicad_sch|Todos los archivos (*.*)|*.*"
        dlg = wx.FileDialog(self, "Abrir Esquemático KiCad", wildcard=wildcard, style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            self._open_file(path)
            self.notebook.SetSelection(1)  # Pasar a la pestaña archivo
        dlg.Destroy()

    def _open_file(self, path: str):
        if not os.path.isfile(path):
            return
        self.current_sch_path = os.path.abspath(path)
        self.txt_file_path.SetValue(self.current_sch_path)
        self._reload_file()

    def _reload_file(self):
        if not self.current_sch_path or not os.path.isfile(self.current_sch_path):
            return

        with open(self.current_sch_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        self.sch_root = SExprParser.parse(content)
        if not self.sch_root:
            wx.MessageBox("Error al parsear el archivo esquemático.", "Error", wx.ICON_ERROR)
            return

        self.file_symbols = [
            it for it in self.sch_root.items if isinstance(it, SNode) and it.tag == "symbol"
        ]

        self.list_file_symbols.Clear()
        for sym in self.file_symbols:
            ref = sym.get_prop("Reference") or "?"
            val = sym.get_prop("Value") or ""
            pos = sym.get_position()
            pos_str = f"({pos[0]:.1f}, {pos[1]:.1f})" if pos else ""
            self.list_file_symbols.Append(f"{ref:8s} | {val:15s} | {pos_str}")

        count_text = f"{len(self.file_symbols)} componentes en el esquemático"
        self.lbl_comp_count.SetLabel(count_text)
        self.status_bar.SetStatusText(f"Archivo cargado: {os.path.basename(self.current_sch_path)}", 0)

    def _select_all_file_symbols(self, select: bool):
        for i in range(self.list_file_symbols.GetCount()):
            self.list_file_symbols.Check(i, select)
        self._update_file_preview()

    def _update_file_preview(self):
        pass  # Actualización dinámica si se requiere

    def _on_apply_file_clicked(self, event):
        """Aplica la duplicación directamente sobre el archivo .kicad_sch."""
        if not self.current_sch_path or not self.sch_root:
            wx.MessageBox("Abre primero un archivo esquemático.", "Aviso", wx.ICON_WARNING)
            return

        # Obtener símbolos seleccionados
        selected_refs = []
        for i in range(self.list_file_symbols.GetCount()):
            if self.list_file_symbols.IsChecked(i):
                ref = self.file_symbols[i].get_prop("Reference")
                if ref:
                    selected_refs.append(ref)

        if not selected_refs:
            wx.MessageBox("Selecciona al menos un componente del bloque a duplicar.", "Aviso", wx.ICON_WARNING)
            return

        # 1. Respaldo de seguridad
        if self.chk_create_bak.GetValue():
            bak_path = SafetyManager.create_backup(self.current_sch_path)
            if bak_path:
                self.status_bar.SetStatusText(f"Respaldo creado: {os.path.basename(bak_path)}", 0)

        # 2. Extraer bloque por referencias y conectividad
        block = BlockDetector.from_schematic_by_references(self.sch_root, selected_refs)

        n_copies = self.spin_n.GetValue()
        pitch = self.spin_pitch.GetValue()
        ann_mode = (
            ReferenceAnnotationMode.RESET_TO_QUESTION_MARK
            if self.choice_ann.GetSelection() == 0
            else ReferenceAnnotationMode.AUTO_SEQUENTIAL
        )

        cfg = DuplicationConfig(
            num_copies=n_copies,
            direction="vertical",
            pitch_y_mm=pitch,
            annotation_mode=ann_mode,
            renaming_rule=RenamingRule(exceptions=set(self.config_data.get("exceptions", [])))
        )

        duplicator = BlockDuplicator(cfg)
        report = duplicator.duplicate_block(block)

        # Insertar elementos nuevos en el AST raíz
        for item in report.new_items:
            self.sch_root.add_child(item)

        # Serializar y guardar en disco
        new_content = SExprSerializer.serialize(self.sch_root)
        with open(self.current_sch_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        # 3. Sincronizar hoja padre si está habilitado
        synced_pins_msg = ""
        if self.chk_sync_parent.GetValue():
            parent_path = HierarchicalManager.find_parent_sheet_file(self.current_sch_path)
            if parent_path:
                hier_renames = [
                    (orig, new) for orig, new, idx in report.labels_renamed
                    if any(l[1] == "hierarchical" and l[2] == orig for l in block.labels)
                ]
                added_pins = HierarchicalManager.sync_parent_sheet_pins(
                    parent_path, self.current_sch_path, hier_renames
                )
                if added_pins:
                    synced_pins_msg = f"\n• Pines añadidos a hoja padre ({os.path.basename(parent_path)}): {', '.join(added_pins)}"

        # 4. Validar con kicad-cli
        erc_ok, erc_out, _ = SafetyManager.validate_with_kicad_erc(self.current_sch_path)

        msg = (
            f"✅ Esquemático actualizado con éxito.\n\n"
            f"• Copias generadas: {report.total_copies_created}\n"
            f"• Símbolos creados: {report.symbols_created}\n"
            f"• Etiquetas renombradas: {len(report.labels_renamed)}"
            f"{synced_pins_msg}\n\n"
            f"Validación ERC de KiCad: {'Exitosa (0 errores)' if erc_ok else 'Revisa el reporte de ERC'}\n"
            "En KiCad, recarga el esquemático para ver los cambios."
        )
        wx.MessageBox(msg, "Duplicación Completada", wx.ICON_INFORMATION)
        self._reload_file()

    def _on_validate_erc_clicked(self, event):
        """Ejecuta kicad-cli sch erc y muestra el resultado en un diálogo."""
        if not self.current_sch_path:
            wx.MessageBox("Abre un archivo de esquemático primero.", "Aviso", wx.ICON_WARNING)
            return

        success, output, infractions = SafetyManager.validate_with_kicad_erc(self.current_sch_path)
        dlg = wx.MessageDialog(
            self,
            f"Resultado de verificación ERC:\n\n{output}",
            "Validación KiCad ERC",
            wx.OK | (wx.ICON_INFORMATION if success else wx.ICON_WARNING)
        )
        dlg.ShowModal()
        dlg.Destroy()

    # -------------------------------------------------------------------------
    # CONFIGURACIÓN Y AYUDA
    # -------------------------------------------------------------------------
    def _on_menu_config(self):
        dlg = ConfigDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            self.config_data = self._load_config()
            self._update_clipboard_preview()
        dlg.Destroy()

    def _show_hyprland_guide(self):
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "main.py"))
        guide = (
            "🚀 Integración con Hyprland / Omarchy 4:\n\n"
            "Para lanzar esta herramienta rápidamente con un atajo global:\n\n"
            "Edita ~/.config/hypr/hyprland.conf o tu archivo de keybinds y añade:\n\n"
            f"bind = $mainMod, D, exec, python3 {script_path}\n\n"
            "Flujo de trabajo con el atajo:\n"
            "1. En KiCad Eeschema, selecciona tu bloque y presiona Ctrl+C.\n"
            "2. Presiona Super + D para abrir esta herramienta.\n"
            "3. Pulsa Enter o 'Duplicar y Copiar al Portapapeles'.\n"
            "4. Vuelve a KiCad y presiona Ctrl+V para pegar todas las copias."
        )
        dlg = wx.MessageDialog(self, guide, "Guía de Atajos Hyprland", wx.OK | wx.ICON_INFORMATION)
        dlg.ShowModal()
        dlg.Destroy()

    def _show_about(self):
        about = (
            "KiCad Block Duplicator & Label Incrementor v1.0.0\n\n"
            "Herramienta de productividad para KiCad 10 en Arch Linux / Hyprland.\n"
            "Duplica bloques jerárquicos y globales incrementando etiquetas automáticas,\n"
            "alineando a grilla de 1.27 mm y preservando redes de alimentación.\n\n"
            "Desarrollado para Emerson."
        )
        wx.MessageBox(about, "Acerca de", wx.ICON_INFORMATION)
