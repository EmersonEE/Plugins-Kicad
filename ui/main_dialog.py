"""Interactive wxPython dialog for KiCad 3D Model Propagator."""

import os
import sys
import wx
from typing import List, Optional

import pcbnew

_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _base_dir not in sys.path:
    sys.path.insert(0, _base_dir)

try:
    from ..core.model_propagator import (
        BoardPropagationAudit,
        FootprintCandidate,
        ModelSearchCandidate,
        apply_3d_models_to_footprint,
        audit_and_propagate_all_board,
        clear_3d_models_for_entire_family,
        clear_3d_models_from_candidates,
        clear_3d_models_from_footprint,
        export_3d_presets,
        filter_candidate_footprints,
        find_candidate_footprints,
        find_matching_3d_models,
        format_model_info,
        get_footprint_fpid,
        get_footprint_models,
        get_footprint_name,
        get_model_transform,
        import_3d_presets,
        update_footprint_model_transform,
    )
except (ImportError, ValueError):
    from core.model_propagator import (
        BoardPropagationAudit,
        FootprintCandidate,
        ModelSearchCandidate,
        apply_3d_models_to_footprint,
        audit_and_propagate_all_board,
        clear_3d_models_for_entire_family,
        clear_3d_models_from_candidates,
        clear_3d_models_from_footprint,
        export_3d_presets,
        filter_candidate_footprints,
        find_candidate_footprints,
        find_matching_3d_models,
        format_model_info,
        get_footprint_fpid,
        get_footprint_models,
        get_footprint_name,
        get_model_transform,
        import_3d_presets,
        update_footprint_model_transform,
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
            "info": wx.Colour(120, 190, 255),
            "danger": wx.Colour(255, 120, 120),
            "muted": wx.Colour(175, 175, 175),
        }
    else:
        return {
            "is_dark": False,
            "success": wx.Colour(0, 130, 20),
            "warning": wx.Colour(180, 90, 0),
            "info": wx.Colour(0, 90, 200),
            "danger": wx.Colour(190, 20, 20),
            "muted": wx.Colour(100, 100, 100),
        }


class ModelSearchDialog(wx.Dialog):
    """Interactive dialog for searching and assigning 3D models from KiCad libraries."""

    def __init__(self, parent, footprint, initial_candidates: List[ModelSearchCandidate]):
        super().__init__(
            parent,
            title="Búsqueda Inteligente de Modelos 3D en Bibliotecas de KiCad",
            size=(960, 600),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX,
        )
        self.SetMinSize((800, 480))
        self.footprint = footprint
        self.candidates = initial_candidates
        self.selected_candidate: Optional[ModelSearchCandidate] = None

        self._init_ui()
        self._populate_list(self.candidates)

    def _init_ui(self):
        palette = get_theme_palette()
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        fpid = get_footprint_fpid(self.footprint) if self.footprint else ""
        item_name = get_footprint_name(self.footprint) if self.footprint else ""

        # Top info box
        info_box = wx.StaticBox(self, label=" Footprint Objetivo ")
        info_sizer = wx.StaticBoxSizer(info_box, wx.VERTICAL)
        lbl_target = wx.StaticText(
            self,
            label=f"Huella: {fpid} (Item: '{item_name}') | Componente: {self.footprint.GetReference() if self.footprint else '-'}",
        )
        lbl_target.SetFont(lbl_target.GetFont().Bold())
        info_sizer.Add(lbl_target, 0, wx.ALL, 4)
        main_sizer.Add(info_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

        # Search Bar
        search_sizer = wx.BoxSizer(wx.HORIZONTAL)
        lbl_search = wx.StaticText(self, label="🔍 Filtrar / Buscar:")
        self.txt_search = wx.TextCtrl(self, value=item_name, style=wx.TE_PROCESS_ENTER)
        self.txt_search.Bind(wx.EVT_TEXT, self._on_search_text_changed)
        self.txt_search.Bind(wx.EVT_TEXT_ENTER, self._on_search_text_changed)

        self.btn_re_search = wx.Button(self, label="Buscar")
        self.btn_re_search.Bind(wx.EVT_BUTTON, self._on_search_text_changed)

        search_sizer.Add(lbl_search, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        search_sizer.Add(self.txt_search, 1, wx.RIGHT | wx.EXPAND, 6)
        search_sizer.Add(self.btn_re_search, 0, wx.ALIGN_CENTER_VERTICAL)
        main_sizer.Add(search_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # Results table
        self.list_ctrl = wx.ListCtrl(
            self,
            style=wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_SINGLE_SEL | wx.LC_VRULES | wx.LC_HRULES,
        )
        self.list_ctrl.InsertColumn(0, "Confianza", wx.LIST_FORMAT_LEFT, 190)
        self.list_ctrl.InsertColumn(1, "Archivo 3D", wx.LIST_FORMAT_LEFT, 260)
        self.list_ctrl.InsertColumn(2, "Tipo", wx.LIST_FORMAT_CENTER, 70)
        self.list_ctrl.InsertColumn(3, "Librería 3D", wx.LIST_FORMAT_LEFT, 210)
        self.list_ctrl.InsertColumn(4, "Tamaño", wx.LIST_FORMAT_RIGHT, 80)
        self.list_ctrl.InsertColumn(5, "Ruta KiCad", wx.LIST_FORMAT_LEFT, 320)

        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_item_selected)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_item_double_clicked)

        main_sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Bottom row
        bottom_row = wx.BoxSizer(wx.HORIZONTAL)
        self.lbl_count = wx.StaticText(self, label="Modelos encontrados: 0")
        self.lbl_count.SetForegroundColour(palette["muted"])

        self.btn_assign = wx.Button(self, wx.ID_OK, label="✔ Asignar Modelo Seleccionado")
        self.btn_assign.SetFont(self.btn_assign.GetFont().Bold())
        self.btn_assign.Enable(False)

        btn_cancel = wx.Button(self, wx.ID_CANCEL, label="Cancelar")

        bottom_row.Add(self.lbl_count, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)
        bottom_row.Add(self.btn_assign, 0, wx.RIGHT, 6)
        bottom_row.Add(btn_cancel, 0)
        main_sizer.Add(bottom_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.SetSizer(main_sizer)

    def _populate_list(self, candidates: List[ModelSearchCandidate]):
        palette = get_theme_palette()
        self.list_ctrl.DeleteAllItems()
        for row, cand in enumerate(candidates):
            self.list_ctrl.InsertItem(row, cand.confidence_label)
            self.list_ctrl.SetItem(row, 1, cand.filename)
            self.list_ctrl.SetItem(row, 2, cand.file_type)
            self.list_ctrl.SetItem(row, 3, cand.library_folder)
            self.list_ctrl.SetItem(row, 4, f"{cand.size_kb:.1f} KB")
            self.list_ctrl.SetItem(row, 5, cand.kicad_path)

            if cand.score >= 100:
                self.list_ctrl.SetItemTextColour(row, palette["success"])
            elif cand.score >= 70:
                self.list_ctrl.SetItemTextColour(row, palette["info"])

        self.lbl_count.SetLabel(f"Modelos encontrados: {len(candidates)}")
        if candidates:
            self.list_ctrl.Select(0)
            self.selected_candidate = candidates[0]
            self.btn_assign.Enable(True)
        else:
            self.selected_candidate = None
            self.btn_assign.Enable(False)

    def _on_search_text_changed(self, _event):
        q = self.txt_search.GetValue()
        self.candidates = find_matching_3d_models(self.footprint, custom_query=q)
        self._populate_list(self.candidates)

    def _on_item_selected(self, event):
        idx = event.GetIndex()
        if 0 <= idx < len(self.candidates):
            self.selected_candidate = self.candidates[idx]
            self.btn_assign.Enable(True)

    def _on_item_double_clicked(self, event):
        idx = event.GetIndex()
        if 0 <= idx < len(self.candidates):
            self.selected_candidate = self.candidates[idx]
            self.EndModal(wx.ID_OK)


class BoardAuditSummaryDialog(wx.Dialog):
    """Detailed summary dialog showing the results of global PCB propagation."""

    def __init__(self, parent, audit: BoardPropagationAudit):
        super().__init__(
            parent,
            title="Informe de Auditoría y Propagación Global del PCB",
            size=(820, 560),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX,
        )
        self.audit = audit
        self._init_ui()

    def _init_ui(self):
        palette = get_theme_palette()
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        summary_box = wx.StaticBox(self, label=" Resumen Global ")
        summary_sizer = wx.StaticBoxSizer(summary_box, wx.VERTICAL)

        stat_text = (
            f"• Total de componentes en PCB: {self.audit.total_footprints}\n"
            f"• Total de familias de huellas: {self.audit.total_families}\n"
            f"• Familias propagadas con éxito: {len(self.audit.families_completed)}\n"
            f"• Huellas que recibieron modelo 3D nuevo: {self.audit.total_fps_updated} ({self.audit.total_models_added} modelos asignados)\n"
            f"• Familias que ya tenían 3D completo: {len(self.audit.families_already_full)}\n"
            f"• Familias sin modelo 3D en la placa: {len(self.audit.families_skipped_no_model)}"
        )
        lbl_stats = wx.StaticText(self, label=stat_text)
        lbl_stats.SetFont(lbl_stats.GetFont().Bold())
        summary_sizer.Add(lbl_stats, 0, wx.ALL, 6)
        main_sizer.Add(summary_sizer, 0, wx.EXPAND | wx.ALL, 10)

        notebook = wx.Notebook(self)

        panel_completed = wx.Panel(notebook)
        p1_sizer = wx.BoxSizer(wx.VERTICAL)
        list_completed = wx.ListCtrl(
            panel_completed, style=wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_VRULES | wx.LC_HRULES
        )
        list_completed.InsertColumn(0, "Familia / Huella", wx.LIST_FORMAT_LEFT, 280)
        list_completed.InsertColumn(1, "Huella Ref", wx.LIST_FORMAT_CENTER, 80)
        list_completed.InsertColumn(2, "Actualizados", wx.LIST_FORMAT_CENTER, 90)
        list_completed.InsertColumn(3, "Componentes que recibieron 3D", wx.LIST_FORMAT_LEFT, 300)

        for row, res in enumerate(self.audit.families_completed):
            list_completed.InsertItem(row, res.family_key)
            list_completed.SetItem(row, 1, res.reference_ref or "-")
            list_completed.SetItem(row, 2, f"{len(res.updated_refs)} / {res.total_footprints}")
            list_completed.SetItem(row, 3, ", ".join(res.updated_refs))
            list_completed.SetItemTextColour(row, palette["success"])

        p1_sizer.Add(list_completed, 1, wx.EXPAND | wx.ALL, 6)
        panel_completed.SetSizer(p1_sizer)
        notebook.AddPage(panel_completed, f"✓ Actualizadas ({len(self.audit.families_completed)})")

        panel_skipped = wx.Panel(notebook)
        p2_sizer = wx.BoxSizer(wx.VERTICAL)
        list_skipped = wx.ListCtrl(
            panel_skipped, style=wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_VRULES | wx.LC_HRULES
        )
        list_skipped.InsertColumn(0, "Familia / Huella", wx.LIST_FORMAT_LEFT, 320)
        list_skipped.InsertColumn(1, "Total Huellas", wx.LIST_FORMAT_CENTER, 100)
        list_skipped.InsertColumn(2, "Estado", wx.LIST_FORMAT_LEFT, 320)

        for row, res in enumerate(self.audit.families_skipped_no_model):
            list_skipped.InsertItem(row, res.family_key)
            list_skipped.SetItem(row, 1, str(res.total_footprints))
            list_skipped.SetItem(row, 2, "Ningún componente de esta familia tiene modelo 3D")
            list_skipped.SetItemTextColour(row, palette["warning"])

        p2_sizer.Add(list_skipped, 1, wx.EXPAND | wx.ALL, 6)
        panel_skipped.SetSizer(p2_sizer)
        notebook.AddPage(panel_skipped, f"⚠ Sin Modelo 3D ({len(self.audit.families_skipped_no_model)})")

        panel_full = wx.Panel(notebook)
        p3_sizer = wx.BoxSizer(wx.VERTICAL)
        list_full = wx.ListCtrl(
            panel_full, style=wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_VRULES | wx.LC_HRULES
        )
        list_full.InsertColumn(0, "Familia / Huella", wx.LIST_FORMAT_LEFT, 320)
        list_full.InsertColumn(1, "Total Huellas", wx.LIST_FORMAT_CENTER, 100)
        list_full.InsertColumn(2, "Componentes con 3D", wx.LIST_FORMAT_LEFT, 320)

        for row, res in enumerate(self.audit.families_already_full):
            list_full.InsertItem(row, res.family_key)
            list_full.SetItem(row, 1, str(res.total_footprints))
            list_full.SetItem(row, 2, ", ".join(res.already_had_model_refs))

        p3_sizer.Add(list_full, 1, wx.EXPAND | wx.ALL, 6)
        panel_full.SetSizer(p3_sizer)
        notebook.AddPage(panel_full, f"Completas Previamente ({len(self.audit.families_already_full)})")

        main_sizer.Add(notebook, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_copy_report = wx.Button(self, label="📋 Copiar Informe")
        self.btn_copy_report.Bind(wx.EVT_BUTTON, self._on_copy_report)

        btn_ok = wx.Button(self, wx.ID_OK, label="Aceptar")

        btn_row.Add(self.btn_copy_report, 0, wx.RIGHT, 10)
        btn_row.AddStretchSpacer(1)
        btn_row.Add(btn_ok, 0)
        main_sizer.Add(btn_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.SetSizer(main_sizer)

    def _on_copy_report(self, _event):
        report_lines = [
            "==================================================",
            "INFORME DE PROPAGACIÓN GLOBAL 3D (KiCad)",
            "==================================================",
            f"Total de componentes: {self.audit.total_footprints}",
            f"Total de familias: {self.audit.total_families}",
            f"Familias completadas: {len(self.audit.families_completed)}",
            f"Huellas actualizadas: {self.audit.total_fps_updated}",
            f"Familias sin modelo de referencia: {len(self.audit.families_skipped_no_model)}",
            "",
            "--- DETALLE DE FAMILIAS COMPLETADAS ---",
        ]
        for res in self.audit.families_completed:
            report_lines.append(
                f"[✓] {res.family_key} (Ref: {res.reference_ref}): Actualizados: {', '.join(res.updated_refs)}"
            )

        if self.audit.families_skipped_no_model:
            report_lines.append("\n--- FAMILIAS SIN MODELO 3D EN EL PCB ---")
            for res in self.audit.families_skipped_no_model:
                report_lines.append(f"[!] {res.family_key} ({res.total_footprints} huellas)")

        report_text = "\n".join(report_lines)
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(report_text))
            wx.TheClipboard.Close()
            wx.MessageBox(
                "Informe copiado al portapapeles con éxito.",
                "Copiar Informe",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )


class ModelPropagatorDialog(wx.Dialog):
    """Main dialog to pick reference, scan candidates, tune 3D, and propagate."""

    def __init__(self, parent, board):
        super().__init__(
            parent,
            title="KiCad 3D Model Propagator - Propagador de Modelos 3D",
            size=(1120, 830),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX,
        )
        self.SetMinSize((960, 660))
        self.board = board
        self.reference_fp = None
        self.candidates: List[FootprintCandidate] = []
        self.filtered_candidates: List[FootprintCandidate] = []
        self._updating_widgets = False

        self._init_ui()
        self._auto_select_initial_reference()

    def _init_ui(self):
        palette = get_theme_palette()
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ---------------------------------------------------------------------
        # 1. Sección: Footprint de Referencia
        # ---------------------------------------------------------------------
        ref_box = wx.StaticBox(self, label=" 1. Footprint de Referencia (Origen del Modelo 3D) ")
        ref_sizer = wx.StaticBoxSizer(ref_box, wx.VERTICAL)

        ref_top_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_capture_ref = wx.Button(self, label="📍 Capturar Selección de PCB")
        self.btn_capture_ref.SetFont(self.btn_capture_ref.GetFont().Bold())
        self.btn_capture_ref.Bind(wx.EVT_BUTTON, self._on_capture_reference)

        ref_lbl = wx.StaticText(self, label="O elegir de la placa:")
        self.ref_choice = wx.Choice(self, choices=["(Ninguno)"])
        self.ref_choice.SetSelection(0)
        self.ref_choice.Bind(wx.EVT_CHOICE, self._on_ref_choice_changed)

        self.btn_view_ref = wx.Button(self, label="👁 Ver en PCB")
        self.btn_view_ref.Bind(wx.EVT_BUTTON, self._on_view_ref_in_pcb)
        self.btn_view_ref.Enable(False)

        ref_top_row.Add(self.btn_capture_ref, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 10)
        ref_top_row.Add(ref_lbl, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        ref_top_row.Add(self.ref_choice, 1, wx.RIGHT | wx.EXPAND, 8)
        ref_top_row.Add(self.btn_view_ref, 0, wx.ALIGN_CENTER_VERTICAL)
        ref_sizer.Add(ref_top_row, 0, wx.EXPAND | wx.ALL, 6)

        self.lbl_ref_info = wx.StaticText(
            self, label="Selecciona un footprint en el PCB o elígelo del menú superior."
        )
        self.lbl_ref_info.SetForegroundColour(palette["muted"])
        ref_sizer.Add(self.lbl_ref_info, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        model_row = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_model_summary = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_SUNKEN,
            size=(-1, 55),
        )
        self.txt_model_summary.SetFont(
            wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        )
        self.txt_model_summary.SetValue("Modelo 3D: (Ninguno asignado)")

        self.btn_auto_search_3d = wx.Button(self, label="✨ Búsqueda Inteligente 3D...")
        self.btn_auto_search_3d.SetFont(self.btn_auto_search_3d.GetFont().Bold())
        self.btn_auto_search_3d.Bind(wx.EVT_BUTTON, self._on_auto_search_3d)

        self.btn_assign_model = wx.Button(self, label="📁 Examinar (.step, .wrl)...")
        self.btn_assign_model.Bind(wx.EVT_BUTTON, self._on_browse_3d_model)

        self.btn_clear_ref_3d = wx.Button(self, label="🗑 Limpiar 3D de Ref")
        self.btn_clear_ref_3d.Bind(wx.EVT_BUTTON, self._on_clear_ref_3d)

        model_row.Add(self.txt_model_summary, 1, wx.RIGHT | wx.EXPAND, 8)
        model_row.Add(self.btn_auto_search_3d, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        model_row.Add(self.btn_assign_model, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        model_row.Add(self.btn_clear_ref_3d, 0, wx.ALIGN_CENTER_VERTICAL)
        ref_sizer.Add(model_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # Fase 2: Editor de Offset, Rotación y Escala en Vivo
        tuning_box = wx.StaticBox(self, label=" 🎛️ Ajuste Fino 3D en Vivo (Offset, Rotación y Escala) ")
        tuning_sizer = wx.StaticBoxSizer(tuning_box, wx.VERTICAL)

        m_sel_row = wx.BoxSizer(wx.HORIZONTAL)
        lbl_mod_idx = wx.StaticText(self, label="Modelo 3D a ajustar:")
        self.choice_model_idx = wx.Choice(self, choices=["[1] Modelo Principal"])
        self.choice_model_idx.SetSelection(0)
        self.choice_model_idx.Bind(wx.EVT_CHOICE, self._on_model_sub_choice_changed)

        m_sel_row.Add(lbl_mod_idx, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        m_sel_row.Add(self.choice_model_idx, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 16)
        tuning_sizer.Add(m_sel_row, 0, wx.EXPAND | wx.ALL, 4)

        grid = wx.FlexGridSizer(3, 8, 4, 6)
        grid.AddGrowableCol(1)
        grid.AddGrowableCol(3)
        grid.AddGrowableCol(5)

        # Row 1: Offset (X, Y, Z in mm)
        lbl_off = wx.StaticText(self, label="Offset (mm):")
        lbl_off.SetFont(lbl_off.GetFont().Bold())

        self.spin_off_x = wx.SpinCtrlDouble(self, value="0.0", min=-1000.0, max=1000.0, inc=0.1)
        self.spin_off_x.SetDigits(2)
        self.spin_off_y = wx.SpinCtrlDouble(self, value="0.0", min=-1000.0, max=1000.0, inc=0.1)
        self.spin_off_y.SetDigits(2)
        self.spin_off_z = wx.SpinCtrlDouble(self, value="0.0", min=-1000.0, max=1000.0, inc=0.1)
        self.spin_off_z.SetDigits(2)

        for sp in [self.spin_off_x, self.spin_off_y, self.spin_off_z]:
            sp.Bind(wx.EVT_SPINCTRLDOUBLE, self._on_transform_changed)

        btn_zero_offset = wx.Button(self, label="↺ Cero Offset", size=(-1, 24))
        btn_zero_offset.Bind(wx.EVT_BUTTON, self._on_zero_offset)

        grid.Add(lbl_off, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._create_axis_pair("X:", self.spin_off_x), 1, wx.EXPAND)
        grid.Add(self._create_axis_pair("Y:", self.spin_off_y), 1, wx.EXPAND)
        grid.Add(self._create_axis_pair("Z:", self.spin_off_z), 1, wx.EXPAND)
        grid.Add(btn_zero_offset, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(wx.StaticText(self, label=""), 0)
        grid.Add(wx.StaticText(self, label=""), 0)
        grid.Add(wx.StaticText(self, label=""), 0)

        # Row 2: Rotation (X, Y, Z in degrees)
        lbl_rot = wx.StaticText(self, label="Rotación (°):")
        lbl_rot.SetFont(lbl_rot.GetFont().Bold())

        self.spin_rot_x = wx.SpinCtrlDouble(self, value="0.0", min=-360.0, max=360.0, inc=15.0)
        self.spin_rot_x.SetDigits(1)
        self.spin_rot_y = wx.SpinCtrlDouble(self, value="0.0", min=-360.0, max=360.0, inc=15.0)
        self.spin_rot_y.SetDigits(1)
        self.spin_rot_z = wx.SpinCtrlDouble(self, value="0.0", min=-360.0, max=360.0, inc=15.0)
        self.spin_rot_z.SetDigits(1)

        for sp in [self.spin_rot_x, self.spin_rot_y, self.spin_rot_z]:
            sp.Bind(wx.EVT_SPINCTRLDOUBLE, self._on_transform_changed)

        btn_z_plus90 = wx.Button(self, label="Z +90°", size=(-1, 24))
        btn_z_minus90 = wx.Button(self, label="Z -90°", size=(-1, 24))
        btn_z_180 = wx.Button(self, label="Z 180°", size=(-1, 24))
        btn_zero_rot = wx.Button(self, label="↺ 0°", size=(-1, 24))

        btn_z_plus90.Bind(wx.EVT_BUTTON, lambda _e: self._step_rotation("z", 90.0))
        btn_z_minus90.Bind(wx.EVT_BUTTON, lambda _e: self._step_rotation("z", -90.0))
        btn_z_180.Bind(wx.EVT_BUTTON, lambda _e: self._step_rotation("z", 180.0))
        btn_zero_rot.Bind(wx.EVT_BUTTON, self._on_zero_rotation)

        grid.Add(lbl_rot, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._create_axis_pair("X:", self.spin_rot_x), 1, wx.EXPAND)
        grid.Add(self._create_axis_pair("Y:", self.spin_rot_y), 1, wx.EXPAND)
        grid.Add(self._create_axis_pair("Z:", self.spin_rot_z), 1, wx.EXPAND)
        grid.Add(btn_z_plus90, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(btn_z_minus90, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(btn_z_180, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(btn_zero_rot, 0, wx.ALIGN_CENTER_VERTICAL)

        # Row 3: Scale (X, Y, Z with Uniform linking)
        lbl_scale = wx.StaticText(self, label="Escala:")
        lbl_scale.SetFont(lbl_scale.GetFont().Bold())

        self.spin_scale_x = wx.SpinCtrlDouble(self, value="1.0", min=0.0001, max=1000.0, inc=0.1)
        self.spin_scale_x.SetDigits(4)
        self.spin_scale_y = wx.SpinCtrlDouble(self, value="1.0", min=0.0001, max=1000.0, inc=0.1)
        self.spin_scale_y.SetDigits(4)
        self.spin_scale_z = wx.SpinCtrlDouble(self, value="1.0", min=0.0001, max=1000.0, inc=0.1)
        self.spin_scale_z.SetDigits(4)

        self.spin_scale_x.Bind(wx.EVT_SPINCTRLDOUBLE, lambda e: self._on_scale_changed("x"))
        self.spin_scale_y.Bind(wx.EVT_SPINCTRLDOUBLE, lambda e: self._on_scale_changed("y"))
        self.spin_scale_z.Bind(wx.EVT_SPINCTRLDOUBLE, lambda e: self._on_scale_changed("z"))

        self.chk_uniform_scale = wx.CheckBox(self, label="🔗 Uniforme")
        self.chk_uniform_scale.SetValue(True)

        btn_reset_scale = wx.Button(self, label="↺ 1.0", size=(-1, 24))
        btn_reset_scale.Bind(wx.EVT_BUTTON, self._on_reset_scale)

        btn_inch_mm = wx.Button(self, label="Pulg→mm", size=(-1, 24))
        btn_inch_mm.SetToolTip("Aplica factor 0.3937 para modelos en pulgadas/WRL")
        btn_inch_mm.Bind(wx.EVT_BUTTON, self._on_scale_inch_to_mm)

        grid.Add(lbl_scale, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._create_axis_pair("X:", self.spin_scale_x), 1, wx.EXPAND)
        grid.Add(self._create_axis_pair("Y:", self.spin_scale_y), 1, wx.EXPAND)
        grid.Add(self._create_axis_pair("Z:", self.spin_scale_z), 1, wx.EXPAND)
        grid.Add(self.chk_uniform_scale, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(btn_reset_scale, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(btn_inch_mm, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(wx.StaticText(self, label=""), 0)

        tuning_sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 4)

        tune_btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.lbl_tune_status = wx.StaticText(self, label="Ajustes sincronizados con la referencia.")
        self.lbl_tune_status.SetForegroundColour(palette["success"])

        self.btn_apply_tuning = wx.Button(self, label="✔ Guardar Ajuste a Referencia (Refrescar 3D)")
        self.btn_apply_tuning.SetFont(self.btn_apply_tuning.GetFont().Bold())
        self.btn_apply_tuning.Bind(wx.EVT_BUTTON, self._on_apply_tuning_clicked)

        tune_btn_row.Add(self.lbl_tune_status, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)
        tune_btn_row.Add(self.btn_apply_tuning, 0)
        tuning_sizer.Add(tune_btn_row, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 4)

        ref_sizer.Add(tuning_sizer, 0, wx.EXPAND | wx.ALL, 4)
        main_sizer.Add(ref_sizer, 0, wx.EXPAND | wx.ALL, 8)

        # ---------------------------------------------------------------------
        # 2. Sección: Opciones de Detección y Presets JSON (Fase 3)
        # ---------------------------------------------------------------------
        opts_row = wx.BoxSizer(wx.HORIZONTAL)

        self.chk_name_only = wx.CheckBox(
            self, label="Coincidir solo por nombre de huella (ignorar librería)"
        )
        self.chk_name_only.SetValue(False)
        self.chk_name_only.Bind(wx.EVT_CHECKBOX, lambda _e: self._scan_candidates())

        self.chk_overwrite = wx.CheckBox(
            self, label="Sobrescribir huellas que ya tengan otro modelo 3D asignado"
        )
        self.chk_overwrite.SetValue(False)
        self.chk_overwrite.Bind(wx.EVT_CHECKBOX, lambda _e: self._scan_candidates())

        self.btn_rescan = wx.Button(self, label="🔍 Detectar Candidatos")
        self.btn_rescan.Bind(wx.EVT_BUTTON, lambda _e: self._scan_candidates())

        self.btn_export_preset = wx.Button(self, label="💾 Exportar Preset...")
        self.btn_export_preset.Bind(wx.EVT_BUTTON, self._on_export_preset)

        self.btn_import_preset = wx.Button(self, label="📂 Importar Preset...")
        self.btn_import_preset.Bind(wx.EVT_BUTTON, self._on_import_preset)

        opts_row.Add(self.chk_name_only, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 12)
        opts_row.Add(self.chk_overwrite, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 12)
        opts_row.Add(self.btn_rescan, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 12)
        opts_row.AddStretchSpacer(1)
        opts_row.Add(self.btn_export_preset, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        opts_row.Add(self.btn_import_preset, 0, wx.ALIGN_CENTER_VERTICAL)
        main_sizer.Add(opts_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # ---------------------------------------------------------------------
        # 3. Sección: Tabla de Footprints Candidatos (Con Filtros - Fase 5)
        # ---------------------------------------------------------------------
        table_box = wx.StaticBox(self, label=" 2. Footprints Candidatos para Propagación ")
        table_sizer = wx.StaticBoxSizer(table_box, wx.VERTICAL)

        filter_bar_row = wx.BoxSizer(wx.HORIZONTAL)
        lbl_quick_filter = wx.StaticText(self, label="🔍 Filtrar:")
        lbl_quick_filter.SetFont(lbl_quick_filter.GetFont().Bold())

        self.txt_filter_table = wx.TextCtrl(
            self,
            style=wx.TE_PROCESS_ENTER,
            size=(240, -1),
        )
        self.txt_filter_table.SetHint("Buscar Ref (R1, R*), Valor (10k) o Huella...")
        self.txt_filter_table.Bind(wx.EVT_TEXT, self._on_table_filter_changed)

        self.choice_status_filter = wx.Choice(
            self,
            choices=["Estado 3D: Todos", "Solo sin modelo 3D", "Solo con modelo 3D"],
        )
        self.choice_status_filter.SetSelection(0)
        self.choice_status_filter.Bind(wx.EVT_CHOICE, self._on_table_filter_changed)

        self.btn_clear_filter = wx.Button(self, label="↺ Limpiar", size=(-1, 24))
        self.btn_clear_filter.Bind(wx.EVT_BUTTON, self._on_clear_table_filter)

        self.btn_select_visible = wx.Button(self, label="☑ Marcar Visibles")
        self.btn_select_visible.Bind(wx.EVT_BUTTON, self._on_select_visible)

        self.btn_unselect_visible = wx.Button(self, label="☐ Desmarcar Visibles")
        self.btn_unselect_visible.Bind(wx.EVT_BUTTON, self._on_unselect_visible)

        self.btn_invert_visible = wx.Button(self, label="⇄ Invertir Visibles")
        self.btn_invert_visible.Bind(wx.EVT_BUTTON, self._on_invert_visible)

        filter_bar_row.Add(lbl_quick_filter, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 4)
        filter_bar_row.Add(self.txt_filter_table, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        filter_bar_row.Add(self.choice_status_filter, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        filter_bar_row.Add(self.btn_clear_filter, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 14)
        filter_bar_row.Add(self.btn_select_visible, 0, wx.RIGHT, 4)
        filter_bar_row.Add(self.btn_unselect_visible, 0, wx.RIGHT, 4)
        filter_bar_row.Add(self.btn_invert_visible, 0, wx.RIGHT, 6)
        table_sizer.Add(filter_bar_row, 0, wx.EXPAND | wx.ALL, 4)

        self.lbl_candidate_count = wx.StaticText(self, label="Candidatos encontrados: 0")
        self.lbl_candidate_count.SetFont(self.lbl_candidate_count.GetFont().Bold())
        table_sizer.Add(self.lbl_candidate_count, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)

        self.list_ctrl = wx.ListCtrl(
            self,
            style=wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_VRULES | wx.LC_HRULES,
        )
        self.list_ctrl.EnableCheckBoxes(True)

        self.list_ctrl.InsertColumn(0, "Sel", wx.LIST_FORMAT_CENTER, 45)
        self.list_ctrl.InsertColumn(1, "Referencia", wx.LIST_FORMAT_CENTER, 90)
        self.list_ctrl.InsertColumn(2, "Valor", wx.LIST_FORMAT_LEFT, 110)
        self.list_ctrl.InsertColumn(3, "Huella (FPID)", wx.LIST_FORMAT_LEFT, 280)
        self.list_ctrl.InsertColumn(4, "Posición PCB", wx.LIST_FORMAT_CENTER, 140)
        self.list_ctrl.InsertColumn(5, "Estado 3D Actual", wx.LIST_FORMAT_LEFT, 170)

        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_CHECKED, self._on_item_checked)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_UNCHECKED, self._on_item_unchecked)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_item_double_clicked)

        table_sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, 4)
        main_sizer.Add(table_sizer, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # ---------------------------------------------------------------------
        # 4. Sección: Barra Inferior de Aplicación y Limpieza (Fase 6)
        # ---------------------------------------------------------------------
        bottom_row = wx.BoxSizer(wx.HORIZONTAL)
        self.status_bar_lbl = wx.StaticText(self, label="Listo.")
        self.status_bar_lbl.SetForegroundColour(palette["muted"])

        # Fase 6: Acciones de Limpieza con estilo nativo limpio
        self.btn_clear_selected = wx.Button(self, label="🗑 Limpiar Marcados")
        self.btn_clear_selected.Bind(wx.EVT_BUTTON, self._on_clear_selected)

        self.btn_clear_family = wx.Button(self, label="💥 Limpiar Familia")
        self.btn_clear_family.Bind(wx.EVT_BUTTON, self._on_clear_family)

        self.btn_propagate_all_board = wx.Button(self, label="🌐 Propagar Todo el PCB (1-Clic)")
        self.btn_propagate_all_board.SetFont(self.btn_propagate_all_board.GetFont().Bold())
        self.btn_propagate_all_board.Bind(wx.EVT_BUTTON, self._on_propagate_all_board)

        self.btn_apply_selected = wx.Button(self, label="⚡ Aplicar a Marcados")
        self.btn_apply_selected.SetFont(self.btn_apply_selected.GetFont().Bold())
        self.btn_apply_selected.Bind(wx.EVT_BUTTON, self._on_apply_selected)

        self.btn_apply_all = wx.Button(self, label="⚡ Aplicar a Esta Familia")
        self.btn_apply_all.SetFont(self.btn_apply_all.GetFont().Bold())
        self.btn_apply_all.Bind(wx.EVT_BUTTON, self._on_apply_all)

        self.btn_close = wx.Button(self, wx.ID_CANCEL, label="Cerrar")
        self.btn_close.Bind(wx.EVT_BUTTON, lambda _e: self.Close())

        bottom_row.Add(self.status_bar_lbl, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        bottom_row.Add(self.btn_clear_selected, 0, wx.RIGHT, 6)
        bottom_row.Add(self.btn_clear_family, 0, wx.RIGHT, 10)
        bottom_row.Add(self.btn_propagate_all_board, 0, wx.RIGHT, 8)
        bottom_row.Add(self.btn_apply_selected, 0, wx.RIGHT, 6)
        bottom_row.Add(self.btn_apply_all, 0, wx.RIGHT, 6)
        bottom_row.Add(self.btn_close, 0)
        main_sizer.Add(bottom_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        self.SetSizer(main_sizer)
        self._populate_reference_dropdown()

    def _create_axis_pair(self, axis_label, spin_ctrl):
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(self, label=axis_label)
        sizer.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 2)
        sizer.Add(spin_ctrl, 1, wx.EXPAND)
        return sizer

    def _populate_reference_dropdown(self):
        if not self.board:
            return
        fps = list(self.board.GetFootprints())
        choices = ["(Elegir footprint...)"]
        self._fps_map = {}
        for fp in sorted(fps, key=lambda f: f.GetReference()):
            ref = fp.GetReference()
            val = fp.GetValue()
            name = get_footprint_name(fp)
            has_m = "✓3D" if get_footprint_models(fp) else "sin 3D"
            label = f"{ref} ({val}) - {name} [{has_m}]"
            choices.append(label)
            self._fps_map[label] = fp

        self.ref_choice.Clear()
        self.ref_choice.Append(choices)
        self.ref_choice.SetSelection(0)

    def _auto_select_initial_reference(self):
        if not self.board:
            return
        selected = [fp for fp in self.board.GetFootprints() if fp.IsSelected()]
        if selected:
            with_models = [fp for fp in selected if get_footprint_models(fp)]
            target = with_models[0] if with_models else selected[0]
            self._set_reference_footprint(target)

    def _set_reference_footprint(self, fp):
        self.reference_fp = fp
        if not fp:
            self.lbl_ref_info.SetLabel("Ningún footprint seleccionado como referencia.")
            self.txt_model_summary.SetValue("Modelo 3D: (Ninguno asignado)")
            self.btn_view_ref.Enable(False)
            self.btn_clear_ref_3d.Enable(False)
            self.choice_model_idx.Clear()
            self.choice_model_idx.Append(["(Sin modelos)"])
            self.choice_model_idx.SetSelection(0)
            self.candidates = []
            self.filtered_candidates = []
            self._refresh_candidate_table()
            return

        ref = fp.GetReference()
        val = fp.GetValue()
        fpid = get_footprint_fpid(fp)
        models = get_footprint_models(fp)

        self.lbl_ref_info.SetLabel(
            f"Referencia: {ref} | Valor: '{val}' | Huella (FPID): {fpid}"
        )
        self.btn_view_ref.Enable(True)
        self.btn_clear_ref_3d.Enable(len(models) > 0)

        self.choice_model_idx.Clear()
        if models:
            choices = []
            for i, m in enumerate(models, 1):
                fn = os.path.basename(m.m_Filename) if m.m_Filename else f"Modelo {i}"
                choices.append(f"[{i}] {fn}")
            self.choice_model_idx.Append(choices)
            self.choice_model_idx.SetSelection(0)

            lines = [f"Modelos 3D asignados ({len(models)}):"]
            for idx, m in enumerate(models, 1):
                lines.append(f"[{idx}] {format_model_info(m)}")
            self.txt_model_summary.SetValue("\n".join(lines))
            self._load_transform_into_widgets(models[0])
        else:
            self.choice_model_idx.Append(["(Sin modelos 3D asignados)"])
            self.choice_model_idx.SetSelection(0)
            self.txt_model_summary.SetValue(
                "⚠ Este footprint NO tiene ningún modelo 3D asignado actualmente.\n"
                "Usa '✨ Búsqueda Inteligente 3D...' para encontrarlo automáticamente en KiCad."
            )
            self._load_transform_into_widgets(None)

        for idx in range(1, self.ref_choice.GetCount()):
            label = self.ref_choice.GetString(idx)
            if label in self._fps_map and self._fps_map[label] == fp:
                self.ref_choice.SetSelection(idx)
                break

        self._scan_candidates()

    def _load_transform_into_widgets(self, model: Optional[pcbnew.FP_3DMODEL]):
        self._updating_widgets = True
        try:
            t = get_model_transform(model)
            ox, oy, oz = t["offset"]
            rx, ry, rz = t["rotation"]
            sx, sy, sz = t["scale"]

            self.spin_off_x.SetValue(ox)
            self.spin_off_y.SetValue(oy)
            self.spin_off_z.SetValue(oz)

            self.spin_rot_x.SetValue(rx)
            self.spin_rot_y.SetValue(ry)
            self.spin_rot_z.SetValue(rz)

            self.spin_scale_x.SetValue(sx)
            self.spin_scale_y.SetValue(sy)
            self.spin_scale_z.SetValue(sz)

            has_model = model is not None
            for ctrl in [
                self.spin_off_x, self.spin_off_y, self.spin_off_z,
                self.spin_rot_x, self.spin_rot_y, self.spin_rot_z,
                self.spin_scale_x, self.spin_scale_y, self.spin_scale_z,
                self.btn_apply_tuning,
            ]:
                ctrl.Enable(has_model)
        finally:
            self._updating_widgets = False

    def _get_current_model_idx(self) -> int:
        if not self.reference_fp:
            return 0
        models = get_footprint_models(self.reference_fp)
        idx = self.choice_model_idx.GetSelection()
        if 0 <= idx < len(models):
            return idx
        return 0

    def _on_model_sub_choice_changed(self, _event):
        if not self.reference_fp:
            return
        models = get_footprint_models(self.reference_fp)
        idx = self._get_current_model_idx()
        if idx < len(models):
            self._load_transform_into_widgets(models[idx])

    def _on_transform_changed(self, _event):
        if self._updating_widgets or not self.reference_fp:
            return
        self._apply_current_tuning_to_reference(notify=False)

    def _on_scale_changed(self, changed_axis):
        if self._updating_widgets:
            return
        if self.chk_uniform_scale.GetValue():
            self._updating_widgets = True
            try:
                if changed_axis == "x":
                    val = self.spin_scale_x.GetValue()
                    self.spin_scale_y.SetValue(val)
                    self.spin_scale_z.SetValue(val)
                elif changed_axis == "y":
                    val = self.spin_scale_y.GetValue()
                    self.spin_scale_x.SetValue(val)
                    self.spin_scale_z.SetValue(val)
                elif changed_axis == "z":
                    val = self.spin_scale_z.GetValue()
                    self.spin_scale_x.SetValue(val)
                    self.spin_scale_y.SetValue(val)
            finally:
                self._updating_widgets = False
        self._apply_current_tuning_to_reference(notify=False)

    def _step_rotation(self, axis: str, delta_deg: float):
        if not self.reference_fp:
            return
        if axis == "z":
            curr = self.spin_rot_z.GetValue()
            new_val = (curr + delta_deg) % 360.0
            if new_val > 180.0:
                new_val -= 360.0
            self.spin_rot_z.SetValue(new_val)
        elif axis == "x":
            curr = self.spin_rot_x.GetValue()
            self.spin_rot_x.SetValue((curr + delta_deg) % 360.0)
        elif axis == "y":
            curr = self.spin_rot_y.GetValue()
            self.spin_rot_y.SetValue((curr + delta_deg) % 360.0)
        self._apply_current_tuning_to_reference(notify=False)

    def _on_zero_offset(self, _event):
        self._updating_widgets = True
        try:
            self.spin_off_x.SetValue(0.0)
            self.spin_off_y.SetValue(0.0)
            self.spin_off_z.SetValue(0.0)
        finally:
            self._updating_widgets = False
        self._apply_current_tuning_to_reference(notify=False)

    def _on_zero_rotation(self, _event):
        self._updating_widgets = True
        try:
            self.spin_rot_x.SetValue(0.0)
            self.spin_rot_y.SetValue(0.0)
            self.spin_rot_z.SetValue(0.0)
        finally:
            self._updating_widgets = False
        self._apply_current_tuning_to_reference(notify=False)

    def _on_reset_scale(self, _event):
        self._updating_widgets = True
        try:
            self.spin_scale_x.SetValue(1.0)
            self.spin_scale_y.SetValue(1.0)
            self.spin_scale_z.SetValue(1.0)
        finally:
            self._updating_widgets = False
        self._apply_current_tuning_to_reference(notify=False)

    def _on_scale_inch_to_mm(self, _event):
        self._updating_widgets = True
        try:
            self.spin_scale_x.SetValue(0.3937)
            self.spin_scale_y.SetValue(0.3937)
            self.spin_scale_z.SetValue(0.3937)
        finally:
            self._updating_widgets = False
        self._apply_current_tuning_to_reference(notify=False)

    def _apply_current_tuning_to_reference(self, notify: bool = False):
        palette = get_theme_palette()
        if not self.reference_fp:
            return
        models = get_footprint_models(self.reference_fp)
        idx = self._get_current_model_idx()
        if idx >= len(models):
            return

        offset = (self.spin_off_x.GetValue(), self.spin_off_y.GetValue(), self.spin_off_z.GetValue())
        rot = (self.spin_rot_x.GetValue(), self.spin_rot_y.GetValue(), self.spin_rot_z.GetValue())
        scale = (self.spin_scale_x.GetValue(), self.spin_scale_y.GetValue(), self.spin_scale_z.GetValue())

        update_footprint_model_transform(self.reference_fp, idx, offset, rot, scale)
        pcbnew.Refresh()

        lines = [f"Modelos 3D asignados ({len(models)}):"]
        for i, m in enumerate(models, 1):
            lines.append(f"[{i}] {format_model_info(m)}")
        self.txt_model_summary.SetValue("\n".join(lines))
        self.lbl_tune_status.SetLabel(f"✓ Modelo [{idx + 1}] actualizado en referencia y vista 3D.")
        self.lbl_tune_status.SetForegroundColour(palette["success"])

        if notify:
            wx.MessageBox(
                f"Ajuste aplicado al modelo [{idx + 1}] de {self.reference_fp.GetReference()}.\n\n"
                f"Offset: {offset} mm\nRotación: {rot}°\nEscala: {scale}\n\n"
                "💡 Puedes verificar la alineación abriendo el Visor 3D (Alt + 3).",
                "Ajuste 3D Aplicado",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )

    def _on_apply_tuning_clicked(self, _event):
        self._apply_current_tuning_to_reference(notify=True)

    # -------------------------------------------------------------------------
    # Fase 6: Limpiar / Revertir Modelos 3D
    # -------------------------------------------------------------------------
    def _on_clear_ref_3d(self, _event):
        if not self.reference_fp:
            return
        models = get_footprint_models(self.reference_fp)
        if not models:
            return

        ans = wx.MessageBox(
            f"¿Estás seguro de que deseas eliminar los {len(models)} modelos 3D asignados al footprint de referencia {self.reference_fp.GetReference()}?",
            "Confirmar Eliminación 3D",
            wx.YES_NO | wx.ICON_WARNING,
            self,
        )
        if ans != wx.YES:
            return

        clear_3d_models_from_footprint(self.reference_fp)
        pcbnew.Refresh()
        self._set_reference_footprint(self.reference_fp)
        self.status_bar_lbl.SetLabel(f"Modelos 3D eliminados de {self.reference_fp.GetReference()}.")

    def _on_clear_selected(self, _event):
        targets = [c for c in self.candidates if c.checked and c.has_3d_model]
        if not targets:
            wx.MessageBox(
                "No hay footprints marcados con modelos 3D para eliminar.",
                "Limpiar Marcados",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        ans = wx.MessageBox(
            f"Se eliminarán los modelos 3D de {len(targets)} footprints marcados en la tabla.\n\n"
            "¿Deseas continuar con la eliminación?",
            "Confirmar Limpieza de Marcados",
            wx.YES_NO | wx.ICON_WARNING,
            self,
        )
        if ans != wx.YES:
            return

        cleared_fps, total_models = clear_3d_models_from_candidates(targets)
        pcbnew.Refresh()
        self.status_bar_lbl.SetLabel(
            f"✓ Se eliminaron {total_models} modelos 3D de {cleared_fps} footprints marcados."
        )
        wx.MessageBox(
            f"¡Limpieza completada!\n\n"
            f"• Footprints limpiados: {cleared_fps}\n"
            f"• Modelos 3D eliminados: {total_models}",
            "Modelos 3D Eliminados",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )
        self._scan_candidates()

    def _on_clear_family(self, _event):
        if not self.reference_fp or not self.board:
            wx.MessageBox(
                "Selecciona primero un footprint de referencia para identificar la familia.",
                "Limpiar Familia",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        match_by_name = self.chk_name_only.GetValue()
        family_key = get_footprint_name(self.reference_fp) if match_by_name else get_footprint_fpid(self.reference_fp)

        ans = wx.MessageBox(
            f"⚠ ATENCIÓN: Se eliminarán TODOS los modelos 3D de todos los componentes pertenecientes a la familia:\n\n"
            f"'{family_key}'\n\n"
            f"¿Confirmas la eliminación total de modelos 3D para esta familia en todo el PCB?",
            "Confirmar Eliminación Total de Familia",
            wx.YES_NO | wx.ICON_WARNING,
            self,
        )
        if ans != wx.YES:
            return

        cleared_fps, total_models, refs = clear_3d_models_for_entire_family(
            self.board, family_key, match_by_name_only=match_by_name
        )
        pcbnew.Refresh()

        refs_str = ", ".join(refs[:12])
        if len(refs) > 12:
            refs_str += f" ... (+{len(refs) - 12} más)"

        self.status_bar_lbl.SetLabel(
            f"✓ Familia '{family_key}' limpiada: {cleared_fps} footprints afectados."
        )
        wx.MessageBox(
            f"¡Familia 3D limpiada con éxito!\n\n"
            f"• Familia: {family_key}\n"
            f"• Footprints limpiados: {cleared_fps}\n"
            f"• Total de modelos eliminados: {total_models}\n"
            f"• Componentes: {refs_str if refs_str else 'Ninguno'}",
            "Familia Limpiada",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )
        self._set_reference_footprint(self.reference_fp)

    # -------------------------------------------------------------------------
    # Fase 4: Búsqueda Automática Inteligente 3D
    # -------------------------------------------------------------------------
    def _on_auto_search_3d(self, _event):
        if not self.reference_fp:
            wx.MessageBox(
                "Captura o selecciona primero un footprint de referencia en la lista superior.",
                "Búsqueda Inteligente 3D",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        candidates = find_matching_3d_models(self.reference_fp)
        dlg = ModelSearchDialog(self, self.reference_fp, candidates)
        if dlg.ShowModal() == wx.ID_OK and dlg.selected_candidate:
            chosen = dlg.selected_candidate
            new_mod = pcbnew.FP_3DMODEL()
            new_mod.m_Filename = chosen.kicad_path
            new_mod.m_Offset = pcbnew.VECTOR3D(0.0, 0.0, 0.0)
            new_mod.m_Scale = pcbnew.VECTOR3D(1.0, 1.0, 1.0)
            new_mod.m_Rotation = pcbnew.VECTOR3D(0.0, 0.0, 0.0)
            new_mod.m_Opacity = 1.0
            new_mod.m_Show = True

            try:
                self.reference_fp.Add3DModel(new_mod)
            except Exception:
                try:
                    self.reference_fp.Models().append(new_mod)
                except Exception:
                    pass

            self._set_reference_footprint(self.reference_fp)
            pcbnew.Refresh()

            wx.MessageBox(
                f"¡Modelo 3D asignado con éxito a {self.reference_fp.GetReference()}!\n\n"
                f"• Archivo: {chosen.filename}\n"
                f"• Ruta: {chosen.kicad_path}\n\n"
                "💡 Puedes ajustar su posición en el panel 'Ajuste Fino 3D' y luego propagarlo a los demás footprints.",
                "Modelo 3D Asignado",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
        dlg.Destroy()

    # -------------------------------------------------------------------------
    # Fase 3: Exportar / Importar Presets JSON
    # -------------------------------------------------------------------------
    def _on_export_preset(self, _event):
        if not self.board:
            return

        with wx.FileDialog(
            self,
            "Guardar Preset de Modelos 3D",
            wildcard="Archivos Preset JSON (*.json)|*.json",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            path = fileDialog.GetPath()
            if not path.endswith(".json"):
                path += ".json"

            preset_name = os.path.splitext(os.path.basename(path))[0]
            count = export_3d_presets(
                self.board,
                path,
                match_by_name_only=self.chk_name_only.GetValue(),
                preset_name=preset_name,
            )

            wx.MessageBox(
                f"¡Preset exportado con éxito!\n\n"
                f"• Mapeos de familias 3D guardados: {count}\n"
                f"• Archivo: {path}\n\n"
                "💡 Puedes importar este archivo en cualquier placa nueva para aplicar automáticamente estos modelos 3D.",
                "Preset Exportado",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )

    def _on_import_preset(self, _event):
        if not self.board:
            return

        with wx.FileDialog(
            self,
            "Seleccionar Preset de Modelos 3D",
            wildcard="Archivos Preset JSON (*.json)|*.json",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            path = fileDialog.GetPath()

            res = import_3d_presets(
                self.board,
                path,
                match_by_name_only=self.chk_name_only.GetValue(),
                overwrite=self.chk_overwrite.GetValue(),
            )

            if not res.get("success", False):
                wx.MessageBox(
                    f"No se pudo importar el preset:\n{res.get('error', 'Error desconocido')}",
                    "Error de Importación",
                    wx.OK | wx.ICON_ERROR,
                    self,
                )
                return

            pcbnew.Refresh()

            updated_count = res.get("total_updated", 0)
            matched_fam = res.get("matched_families", 0)
            refs_str = ", ".join(res.get("updated_refs", [])[:12])
            if len(res.get("updated_refs", [])) > 12:
                refs_str += f" ... (+{len(refs) - 12} más)"

            wx.MessageBox(
                f"¡Preset '{res.get('preset_name')}' importado con éxito!\n\n"
                f"• Familias coincidentes en este PCB: {matched_fam}\n"
                f"• Huellas actualizadas con modelos 3D: {updated_count}\n"
                f"• Componentes: {refs_str if refs_str else 'Ninguno modificado'}\n\n"
                "💡 Abre el Visor 3D de KiCad (Alt + 3) para ver los modelos asignados.",
                "Preset Importado",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )

            self._scan_candidates()

    # -------------------------------------------------------------------------
    # Fase 5: Filtrado de la Tabla de Candidatos
    # -------------------------------------------------------------------------
    def _on_table_filter_changed(self, _event):
        self._apply_table_filters()

    def _on_clear_table_filter(self, _event):
        self.txt_filter_table.SetValue("")
        self.choice_status_filter.SetSelection(0)
        self._apply_table_filters()

    def _apply_table_filters(self):
        query = self.txt_filter_table.GetValue()
        sel_idx = self.choice_status_filter.GetSelection()
        status_map = {0: "all", 1: "no_3d", 2: "has_3d"}
        status_filter = status_map.get(sel_idx, "all")

        self.filtered_candidates = filter_candidate_footprints(
            self.candidates,
            query=query,
            status_filter=status_filter,
        )
        self._refresh_candidate_table()

    def _scan_candidates(self):
        if not self.reference_fp or not self.board:
            self.candidates = []
            self.filtered_candidates = []
            self._refresh_candidate_table()
            return

        try:
            self.board = pcbnew.GetBoard()
        except Exception:
            pass

        match_by_name = self.chk_name_only.GetValue()
        include_with_models = self.chk_overwrite.GetValue()

        self.candidates = find_candidate_footprints(
            self.board,
            self.reference_fp,
            match_by_name_only=match_by_name,
            include_with_models=include_with_models,
        )

        self._apply_table_filters()

    def _refresh_candidate_table(self):
        palette = get_theme_palette()
        self.list_ctrl.DeleteAllItems()

        for row_idx, cand in enumerate(self.filtered_candidates):
            self.list_ctrl.InsertItem(row_idx, "")
            self.list_ctrl.CheckItem(row_idx, cand.checked)
            self.list_ctrl.SetItem(row_idx, 1, cand.reference)
            self.list_ctrl.SetItem(row_idx, 2, cand.value)
            self.list_ctrl.SetItem(row_idx, 3, cand.fpid)
            self.list_ctrl.SetItem(row_idx, 4, f"X:{cand.pos_x_mm:.1f}, Y:{cand.pos_y_mm:.1f} mm")

            if cand.has_3d_model:
                self.list_ctrl.SetItem(row_idx, 5, f"Tiene {cand.model_count} mod: {cand.models_summary}")
                self.list_ctrl.SetItemTextColour(row_idx, palette["warning"])
            else:
                self.list_ctrl.SetItem(row_idx, 5, "Sin modelo 3D")
                self.list_ctrl.SetItemTextColour(row_idx, palette["success"])

        checked_visible = sum(1 for c in self.filtered_candidates if c.checked)
        total_checked = sum(1 for c in self.candidates if c.checked)
        vis_count = len(self.filtered_candidates)
        total_count = len(self.candidates)

        if vis_count == total_count:
            self.lbl_candidate_count.SetLabel(
                f"Candidatos detectados: {total_count} (Marcados: {total_checked})"
            )
        else:
            self.lbl_candidate_count.SetLabel(
                f"Mostrando {vis_count} de {total_count} candidatos | Marcados visibles: {checked_visible} (Total marcados: {total_checked})"
            )

        has_models_to_apply = bool(self.reference_fp and get_footprint_models(self.reference_fp))
        self.btn_apply_selected.Enable(has_models_to_apply and total_checked > 0)
        self.btn_apply_all.Enable(has_models_to_apply and vis_count > 0)

        has_checked_with_models = any(c.checked and c.has_3d_model for c in self.candidates)
        self.btn_clear_selected.Enable(has_checked_with_models)
        self.btn_clear_family.Enable(bool(self.reference_fp))

    # -------------------------------------------------------------------------
    # Event Handlers
    # -------------------------------------------------------------------------
    def _on_capture_reference(self, _event):
        try:
            self.board = pcbnew.GetBoard()
        except Exception:
            pass

        selected = [fp for fp in self.board.GetFootprints() if fp.IsSelected()]
        if not selected:
            wx.MessageBox(
                "Selecciona primero un footprint en el PCB Editor de KiCad.",
                "Capturar Referencia",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        self._set_reference_footprint(selected[0])
        self.status_bar_lbl.SetLabel(f"Referencia capturada: {selected[0].GetReference()}.")

    def _on_ref_choice_changed(self, _event):
        idx = self.ref_choice.GetSelection()
        if idx > 0:
            label = self.ref_choice.GetString(idx)
            if label in self._fps_map:
                self._set_reference_footprint(self._fps_map[label])

    def _on_view_ref_in_pcb(self, _event):
        if not self.reference_fp or not self.board:
            return
        for fp in self.board.GetFootprints():
            try:
                fp.ClearSelected()
            except Exception:
                pass
        try:
            self.reference_fp.SetSelected()
        except Exception:
            pass
        pcbnew.Refresh()
        self.status_bar_lbl.SetLabel(
            f"Footprint {self.reference_fp.GetReference()} seleccionado en PCB."
        )

    def _on_browse_3d_model(self, _event):
        if not self.reference_fp:
            wx.MessageBox(
                "Captura o selecciona primero un footprint de referencia.",
                "Asignar Modelo 3D",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        with wx.FileDialog(
            self,
            "Seleccionar Archivo de Modelo 3D",
            wildcard="Modelos 3D (*.step;*.stp;*.wrl)|*.step;*.stp;*.wrl|Archivos STEP (*.step;*.stp)|*.step;*.stp|Archivos VRML (*.wrl)|*.wrl|Todos los archivos (*.*)|*.*",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            model_path = fileDialog.GetPath()

            new_mod = pcbnew.FP_3DMODEL()
            new_mod.m_Filename = model_path
            new_mod.m_Offset = pcbnew.VECTOR3D(0.0, 0.0, 0.0)
            new_mod.m_Scale = pcbnew.VECTOR3D(1.0, 1.0, 1.0)
            new_mod.m_Rotation = pcbnew.VECTOR3D(0.0, 0.0, 0.0)
            new_mod.m_Opacity = 1.0
            new_mod.m_Show = True

            try:
                self.reference_fp.Add3DModel(new_mod)
            except Exception:
                try:
                    self.reference_fp.Models().append(new_mod)
                except Exception:
                    pass

            self._set_reference_footprint(self.reference_fp)
            pcbnew.Refresh()
            wx.MessageBox(
                f"Modelo 3D asignado con éxito a {self.reference_fp.GetReference()}:\n{model_path}",
                "Modelo 3D Asignado",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )

    def _on_item_checked(self, event):
        row_idx = event.GetIndex()
        if row_idx < len(self.filtered_candidates):
            self.filtered_candidates[row_idx].checked = True
            self._update_counter_and_buttons()

    def _on_item_unchecked(self, event):
        row_idx = event.GetIndex()
        if row_idx < len(self.filtered_candidates):
            self.filtered_candidates[row_idx].checked = False
            self._update_counter_and_buttons()

    def _on_item_double_clicked(self, event):
        row_idx = event.GetIndex()
        if row_idx < len(self.filtered_candidates):
            cand = self.filtered_candidates[row_idx]
            for fp in self.board.GetFootprints():
                try:
                    fp.ClearSelected()
                except Exception:
                    pass
            try:
                cand.footprint.SetSelected()
            except Exception:
                pass
            pcbnew.Refresh()
            self.status_bar_lbl.SetLabel(f"Footprint {cand.reference} resaltado en PCB.")

    def _on_select_visible(self, _event):
        for c in self.filtered_candidates:
            c.checked = True
        for r in range(self.list_ctrl.GetItemCount()):
            self.list_ctrl.CheckItem(r, True)
        self._update_counter_and_buttons()

    def _on_unselect_visible(self, _event):
        for c in self.filtered_candidates:
            c.checked = False
        for r in range(self.list_ctrl.GetItemCount()):
            self.list_ctrl.CheckItem(r, False)
        self._update_counter_and_buttons()

    def _on_invert_visible(self, _event):
        for idx, c in enumerate(self.filtered_candidates):
            c.checked = not c.checked
            if idx < self.list_ctrl.GetItemCount():
                self.list_ctrl.CheckItem(idx, c.checked)
        self._update_counter_and_buttons()

    def _update_counter_and_buttons(self):
        checked_visible = sum(1 for c in self.filtered_candidates if c.checked)
        total_checked = sum(1 for c in self.candidates if c.checked)
        vis_count = len(self.filtered_candidates)
        total_count = len(self.candidates)

        if vis_count == total_count:
            self.lbl_candidate_count.SetLabel(
                f"Candidatos detectados: {total_count} (Marcados: {total_checked})"
            )
        else:
            self.lbl_candidate_count.SetLabel(
                f"Mostrando {vis_count} de {total_count} candidatos | Marcados visibles: {checked_visible} (Total marcados: {total_checked})"
            )

        has_models_to_apply = bool(self.reference_fp and get_footprint_models(self.reference_fp))
        self.btn_apply_selected.Enable(has_models_to_apply and total_checked > 0)
        self.btn_apply_all.Enable(has_models_to_apply and vis_count > 0)

        has_checked_with_models = any(c.checked and c.has_3d_model for c in self.candidates)
        self.btn_clear_selected.Enable(has_checked_with_models)
        self.btn_clear_family.Enable(bool(self.reference_fp))

    def _on_apply_selected(self, _event):
        selected_candidates = [c for c in self.candidates if c.checked]
        if not selected_candidates:
            wx.MessageBox(
                "No hay footprints marcados para aplicar el modelo 3D.",
                "Propagación 3D",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        self._execute_propagation(selected_candidates)

    def _on_apply_all(self, _event):
        targets = self.filtered_candidates if self.filtered_candidates else self.candidates
        if not targets:
            return
        self._execute_propagation(targets)

    def _execute_propagation(self, targets: List[FootprintCandidate]):
        if not self.reference_fp:
            return

        source_models = get_footprint_models(self.reference_fp)
        if not source_models:
            wx.MessageBox(
                "El footprint de referencia no tiene ningún modelo 3D asignado.",
                "Sin Modelo 3D",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        overwrite = self.chk_overwrite.GetValue()
        total_fps_updated = 0
        total_models_added = 0
        target_refs = []

        for cand in targets:
            added = apply_3d_models_to_footprint(
                source_models, cand.footprint, overwrite=overwrite
            )
            if added > 0:
                total_fps_updated += 1
                total_models_added += added
                target_refs.append(cand.reference)

        pcbnew.Refresh()

        refs_str = ", ".join(target_refs[:12])
        if len(target_refs) > 12:
            refs_str += f" ... (+{len(target_refs) - 12} más)"

        self.status_bar_lbl.SetLabel(
            f"✓ Modelo 3D propagado a {total_fps_updated} footprints ({refs_str})."
        )

        wx.MessageBox(
            f"¡Propagación completada con éxito!\n\n"
            f"• Footprints actualizados: {total_fps_updated}\n"
            f"• Modelos 3D asignados: {total_models_added}\n"
            f"• Componentes: {refs_str}\n\n"
            f"💡 Abre el Visor 3D de KiCad (Alt + 3) para ver los modelos renderizados.",
            "Propagación 3D Exitosa",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

        self._scan_candidates()

    def _on_propagate_all_board(self, _event):
        try:
            self.board = pcbnew.GetBoard()
        except Exception:
            pass

        if not self.board:
            wx.MessageBox(
                "No hay ninguna placa abierta en KiCad.",
                "Propagar Todo el PCB",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        ans = wx.MessageBox(
            "Se analizará todo el PCB para propagar modelos 3D a todas las familias de huellas que cuenten con al menos una referencia 3D.\n\n"
            "¿Deseas iniciar la propagación global del PCB?",
            "Confirmar Propagación Global",
            wx.YES_NO | wx.ICON_QUESTION,
            self,
        )
        if ans != wx.YES:
            return

        match_by_name = self.chk_name_only.GetValue()
        overwrite = self.chk_overwrite.GetValue()

        audit = audit_and_propagate_all_board(
            self.board,
            match_by_name_only=match_by_name,
            overwrite=overwrite,
        )

        pcbnew.Refresh()

        dlg = BoardAuditSummaryDialog(self, audit)
        dlg.ShowModal()
        dlg.Destroy()

        self.status_bar_lbl.SetLabel(
            f"✓ Auditoría global completada: {audit.total_fps_updated} huellas actualizadas en {len(audit.families_completed)} familias."
        )
        self._scan_candidates()
