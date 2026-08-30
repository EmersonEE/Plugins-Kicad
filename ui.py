"""wxPython UI for Block Aligner."""

import os

import pcbnew
import wx

from . import config as config_module
from . import core
from . import discovery
from . import schematic
from . import tracks


def _fmt_angle(rot):
    """Format a rotation angle compactly (integer degrees or one decimal)."""
    rot = float(rot)
    if abs(rot - round(rot)) < 1e-9:
        return "{}°".format(int(round(rot)))
    return "{:.1f}°".format(rot)


def generate_diagnostic_report(board, reference, existing_targets, discovered_blocks):
    """Generate a detailed diagnostic log of reference, board nets, and detected blocks."""
    lines = []
    lines.append("=== BLOCK ALIGNER DIAGNOSTIC LOG ===")
    lines.append("Total footprints on board: {}".format(len(list(board.GetFootprints()))))
    lines.append("")

    # 1. Reference Block
    lines.append("--- REFERENCE BLOCK ({} footprints) ---".format(len(reference)))
    for fp in sorted(reference, key=lambda f: f.GetReference()):
        ref = fp.GetReference()
        val = fp.GetValue()
        fp_name = core.footprint_name(fp)
        sheet = (
            "{}::{}".format(fp.GetSheetfile(), fp.GetSheetname())
            if (fp.GetSheetfile() or fp.GetSheetname())
            else ""
        )
        try:
            path_str = fp.GetPath().AsString()
        except Exception:
            path_str = ""
        pads_info = []
        for pad in fp.Pads():
            p_num = str(pad.GetNumber())
            net_name = str(pad.GetNetname())
            net_code = pad.GetNetCode()
            pads_info.append("Pin {}: Net '{}' (ID {})".format(p_num, net_name, net_code))
        lines.append(
            "  [{}] Val: '{}' | FP: '{}' | Sheet: '{}' | Path: '{}'".format(
                ref, val, fp_name, sheet, path_str
            )
        )
        lines.append("       Pads: {}".format(", ".join(pads_info)))
    lines.append("")

    # 2. Existing Targets
    if existing_targets:
        lines.append(
            "--- EXISTING TARGETS ({} targets) ---".format(len(existing_targets))
        )
        for idx, entry in enumerate(existing_targets, 1):
            fps = entry["footprints"]
            ref_names = [f.GetReference() for f in fps]
            lines.append(
                "  Target {} ({} fps, rot {}°{}): {}".format(
                    idx,
                    len(fps),
                    entry.get("rotation", 0),
                    " +Espejo" if entry.get("mirror_x") else "",
                    ", ".join(ref_names),
                )
            )
        lines.append("")

    # 3. Discovered Blocks
    lines.append(
        "--- DISCOVERED BLOCKS ({} blocks) ---".format(len(discovered_blocks))
    )
    for idx, block in enumerate(discovered_blocks, 1):
        lines.append("  Discovered Block {} ({} footprints):".format(idx, len(block)))
        for fp in sorted(block, key=lambda f: f.GetReference()):
            ref = fp.GetReference()
            val = fp.GetValue()
            fp_name = core.footprint_name(fp)
            pads_info = []
            for pad in fp.Pads():
                p_num = str(pad.GetNumber())
                net_name = str(pad.GetNetname())
                net_code = pad.GetNetCode()
                pads_info.append(
                    "Pin {}: Net '{}' (ID {})".format(p_num, net_name, net_code)
                )
            lines.append("    [{}] Val: '{}' | FP: '{}'".format(ref, val, fp_name))
            lines.append("         Pads: {}".format(", ".join(pads_info)))
    lines.append("")

    # 4. Remaining Footprints on Board with matching component types
    ref_keys = set(core.footprint_key(fp) for fp in reference)
    used_refs = set(fp.GetReference() for fp in reference)
    for entry in existing_targets:
        for fp in entry["footprints"]:
            used_refs.add(fp.GetReference())
    for block in discovered_blocks:
        for fp in block:
            used_refs.add(fp.GetReference())

    remaining_matching = [
        fp
        for fp in board.GetFootprints()
        if fp.GetReference() not in used_refs
        and core.footprint_key(fp) in ref_keys
    ]
    if remaining_matching:
        lines.append(
            "--- OTHER MATCHING FOOTPRINTS ON BOARD ({} footprints) ---".format(
                len(remaining_matching)
            )
        )
        for fp in sorted(remaining_matching, key=lambda f: f.GetReference()):
            ref = fp.GetReference()
            val = fp.GetValue()
            pads_info = [
                "Pin {}: Net '{}'".format(pad.GetNumber(), pad.GetNetname())
                for pad in fp.Pads()
            ]
            lines.append("  [{}] Val: '{}' | Pads: {}".format(ref, val, ", ".join(pads_info)))
    lines.append("")
    lines.append("=== END OF DIAGNOSTIC LOG ===")

    return "\n".join(lines)


class ErrorDetailsDialog(wx.Dialog):
    """Modal dialog displaying formatted diagnostic breakdown of a destination block."""

    def __init__(self, parent, target_idx, diagnosis):
        super().__init__(
            parent,
            title="Diagnóstico de Error - Destino {}".format(target_idx),
            size=(640, 520),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.SetMinSize((520, 380))

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        header_pnl = wx.Panel(self)
        header_sizer = wx.BoxSizer(wx.VERTICAL)

        if diagnosis["is_valid"]:
            status_txt = wx.StaticText(
                header_pnl,
                label="✓ El bloque es válido y compatible con la referencia.",
            )
            status_txt.SetForegroundColour(wx.Colour(0, 140, 0))
        else:
            status_txt = wx.StaticText(
                header_pnl,
                label="✕ Se detectaron discrepancias en el Destino {}:".format(target_idx),
            )
            status_txt.SetForegroundColour(wx.Colour(200, 0, 0))
        status_txt.SetFont(status_txt.GetFont().Bold())

        summary_txt = wx.StaticText(
            header_pnl,
            label="Componentes esperados: {} | Encontrados en destino: {}".format(
                diagnosis["expected_count"], diagnosis["found_count"]
            ),
        )
        header_sizer.Add(status_txt, 0, wx.ALL, 4)
        header_sizer.Add(summary_txt, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
        header_pnl.SetSizer(header_sizer)
        main_sizer.Add(header_pnl, 0, wx.EXPAND | wx.ALL, 8)

        report_lines = []
        if diagnosis["missing"]:
            report_lines.append("■ COMPONENTES FALTANTES EN EL DESTINO:")
            for item in diagnosis["missing"]:
                report_lines.append("   - {}".format(item))
            report_lines.append("")

        if diagnosis["extra"]:
            report_lines.append("■ COMPONENTES SOBRANTES O NO ESPERADOS:")
            for item in diagnosis["extra"]:
                report_lines.append("   + {}".format(item))
            report_lines.append("")

        if diagnosis["locked"]:
            report_lines.append("■ FOOTPRINTS BLOQUEADOS EN PCB (Desbloquear para mover):")
            report_lines.append("   ⚠ {}".format(", ".join(diagnosis["locked"])))
            report_lines.append("")

        if diagnosis["overlap"]:
            report_lines.append("■ FOOTPRINTS QUE PERTENECEN AL BLOQUE DE REFERENCIA:")
            report_lines.append("   ✕ {}".format(", ".join(diagnosis["overlap"])))
            report_lines.append("")

        suggestions = core.suggest_fixes(diagnosis)
        if suggestions and not diagnosis["is_valid"]:
            report_lines.append("■ SUGERENCIAS:")
            for hint in suggestions:
                report_lines.append("   → {}".format(hint))
            report_lines.append("")

        if not report_lines:
            report_lines.append("No se detectaron problemas en este bloque.")

        text_ctrl = wx.TextCtrl(
            self,
            value="\n".join(report_lines),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_SUNKEN,
        )
        text_ctrl.SetFont(
            wx.Font(
                9,
                wx.FONTFAMILY_TELETYPE,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
            )
        )
        main_sizer.Add(text_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_close = wx.Button(self, wx.ID_CANCEL, label="Cerrar")
        btn_close.Bind(wx.EVT_BUTTON, lambda _evt: self.EndModal(wx.ID_CANCEL))
        btn_sizer.Add(btn_close, 0, wx.ALL, 6)
        main_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.BOTTOM, 6)

        self.SetSizer(main_sizer)


class DiagnosticLogDialog(wx.Dialog):
    """Modal dialog displaying full diagnostic breakdown and copy button."""

    def __init__(self, parent, report_text):
        super().__init__(
            parent,
            title="Diagnóstico de Auto-Detección y Componentes",
            size=(760, 540),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.report_text = report_text
        self._init_ui()

    def _init_ui(self):
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        info_lbl = wx.StaticText(
            self,
            label="Informe de componentes de referencia, conexiones de redes y bloques encontrados.\n"
            "Puedes copiar este informe o se guardará automáticamente en 'debug_log.txt'.",
        )
        main_sizer.Add(info_lbl, 0, wx.ALL, 10)

        self.text_ctrl = wx.TextCtrl(
            self,
            value=self.report_text,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_SUNKEN,
        )
        self.text_ctrl.SetFont(
            wx.Font(
                9,
                wx.FONTFAMILY_TELETYPE,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
            )
        )
        main_sizer.Add(self.text_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_copy = wx.Button(self, label="📋 Copiar al Portapapeles")
        btn_copy.Bind(wx.EVT_BUTTON, self._on_copy)
        btn_close = wx.Button(self, wx.ID_CANCEL, label="Cerrar")
        btn_close.Bind(wx.EVT_BUTTON, lambda _evt: self.EndModal(wx.ID_CANCEL))

        btn_sizer.Add(btn_copy, 0, wx.RIGHT, 8)
        btn_sizer.Add(btn_close, 0)
        main_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.BOTTOM, 10)

        self.SetSizer(main_sizer)

    def _on_copy(self, _event):
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(self.report_text))
            wx.TheClipboard.Close()
            wx.MessageBox(
                "¡Informe copiado al portapapeles con éxito!",
                "Diagnóstico",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )


class BlockAlignerDialog(wx.Dialog):
    def __init__(self, parent, board):
        super().__init__(
            parent,
            title="Block Aligner",
            size=(960, 640),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.SetMinSize((760, 540))
        self.board = board
        self.reference = []
        self.targets = []
        self.config = config_module.load_config()

        self._init_ui()

    def _fmt_angle(self, rot):
        return _fmt_angle(rot)

    def _rot_display(self, entry):
        s = self._fmt_angle(float(entry.get("rotation", 0.0)))
        if entry.get("mirror_x"):
            s += " +E"
        return s

    def _init_ui(self):
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ---------------------------------------------------------------------
        # 1. Sección: Bloque de Referencia
        # ---------------------------------------------------------------------
        ref_box = wx.StaticBox(self, label=" 1. Bloque de Referencia ")
        ref_sizer = wx.StaticBoxSizer(ref_box, wx.VERTICAL)

        ref_top_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_capture = wx.Button(self, label="Capturar referencia")
        self.btn_view_ref = wx.Button(self, label="Ver en PCB")
        self.btn_capture.Bind(wx.EVT_BUTTON, self.capture_reference)
        self.btn_view_ref.Bind(wx.EVT_BUTTON, self.view_reference_in_pcb)

        self.ref_status = wx.StaticText(self, label="Ningún bloque de referencia capturado.")
        bold_font = self.ref_status.GetFont().Bold()
        self.ref_status.SetFont(bold_font)

        ref_top_row.Add(self.btn_capture, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        ref_top_row.Add(self.btn_view_ref, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 10)
        ref_top_row.Add(self.ref_status, 1, wx.ALIGN_CENTER_VERTICAL)

        self.ref_details = wx.StaticText(
            self,
            label="Selecciona los footprints en PCB Editor y haz clic en 'Capturar referencia'.",
        )
        self.ref_details.SetForegroundColour(wx.Colour(120, 120, 120))

        anchor_row = wx.BoxSizer(wx.HORIZONTAL)
        anchor_lbl = wx.StaticText(self, label="Punto de anclaje (origen):")
        self.anchor_choice = wx.Choice(self, choices=["Centroide del bloque"])
        self.anchor_choice.SetSelection(0)
        self.anchor_choice.Bind(wx.EVT_CHOICE, self._on_anchor_changed)

        anchor_row.Add(anchor_lbl, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 8)
        anchor_row.Add(self.anchor_choice, 0, wx.ALIGN_CENTER_VERTICAL)

        ref_sizer.Add(ref_top_row, 0, wx.EXPAND | wx.ALL, 6)
        ref_sizer.Add(self.ref_details, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
        ref_sizer.Add(anchor_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        main_sizer.Add(ref_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # ---------------------------------------------------------------------
        # 2. Sección: Bloques Destino
        # ---------------------------------------------------------------------
        target_box = wx.StaticBox(self, label=" 2. Bloques Destino ")
        target_sizer = wx.StaticBoxSizer(target_box, wx.VERTICAL)

        self.target_list = wx.ListCtrl(
            self,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN,
        )
        self.target_list.InsertColumn(0, "#", wx.LIST_FORMAT_CENTER, 40)
        self.target_list.InsertColumn(1, "Footprints / Componentes", wx.LIST_FORMAT_LEFT, 320)
        self.target_list.InsertColumn(2, "Cantidad", wx.LIST_FORMAT_CENTER, 75)
        self.target_list.InsertColumn(3, "Rotación", wx.LIST_FORMAT_CENTER, 90)
        self.target_list.InsertColumn(4, "Estado de Validación", wx.LIST_FORMAT_LEFT, 240)

        self.target_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_target_selection_change)
        self.target_list.Bind(wx.EVT_LIST_ITEM_DESELECTED, self._on_target_selection_change)
        self.target_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_target_activated)
        self.target_list.Bind(wx.EVT_KEY_DOWN, self._on_key_down)

        target_btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_add_target = wx.Button(self, label="Añadir selección")
        self.btn_auto_discover = wx.Button(self, label="Auto-detectar")
        self.btn_remove_target = wx.Button(self, label="Eliminar")
        self.btn_view_target = wx.Button(self, label="Ver en PCB")
        self.btn_inspect_error = wx.Button(self, label="Detalles error")
        self.btn_export_log = wx.Button(self, label="📋 Diagnóstico")
        self.btn_clear = wx.Button(self, label="Limpiar todo")

        self.btn_add_target.Bind(wx.EVT_BUTTON, self.add_target)
        self.btn_auto_discover.Bind(wx.EVT_BUTTON, self.auto_discover)
        self.btn_remove_target.Bind(wx.EVT_BUTTON, self.remove_target)
        self.btn_view_target.Bind(wx.EVT_BUTTON, self.view_target_in_pcb)
        self.btn_inspect_error.Bind(wx.EVT_BUTTON, self.show_error_details)
        self.btn_export_log.Bind(wx.EVT_BUTTON, self.export_diagnostic_log)
        self.btn_clear.Bind(wx.EVT_BUTTON, self.clear)

        target_btn_row.Add(self.btn_add_target, 0, wx.RIGHT, 4)
        target_btn_row.Add(self.btn_auto_discover, 0, wx.RIGHT, 4)
        target_btn_row.Add(self.btn_remove_target, 0, wx.RIGHT, 4)
        target_btn_row.Add(self.btn_view_target, 0, wx.RIGHT, 4)
        target_btn_row.Add(self.btn_inspect_error, 0, wx.RIGHT, 4)
        target_btn_row.Add(self.btn_export_log, 0, wx.RIGHT, 4)
        target_btn_row.Add(self.btn_clear, 0)

        # Transformaciones del destino seleccionado, en una fila separada para
        # mantener legible el flujo en ventanas estrechas.
        transform_row = wx.BoxSizer(wx.HORIZONTAL)
        rot_lbl = wx.StaticText(self, label="Rotación:")
        self.btn_rot_ccw = wx.Button(self, label="↺ -90°", size=(62, -1))
        self.btn_rot_cw = wx.Button(self, label="↻ +90°", size=(62, -1))
        self.rotation_spin = wx.SpinCtrlDouble(
            self, value="0", min=-360.0, max=360.0, inc=90.0, size=(90, -1)
        )
        self.chk_mirror = wx.CheckBox(self, label="Espejo X")

        self.btn_rot_ccw.Bind(wx.EVT_BUTTON, self._on_rotate_ccw)
        self.btn_rot_cw.Bind(wx.EVT_BUTTON, self._on_rotate_cw)
        self.rotation_spin.Bind(wx.EVT_SPINCTRLDOUBLE, self._on_rotation_changed)
        self.chk_mirror.Bind(wx.EVT_CHECKBOX, self._on_mirror_changed)

        transform_row.Add(
            wx.StaticText(self, label="Transformar destino seleccionado:"),
            0,
            wx.RIGHT | wx.ALIGN_CENTER_VERTICAL,
            10,
        )
        transform_row.Add(rot_lbl, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 4)
        transform_row.Add(self.btn_rot_ccw, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 2)
        transform_row.Add(self.btn_rot_cw, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 4)
        transform_row.Add(self.rotation_spin, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 8)
        transform_row.Add(self.chk_mirror, 0, wx.ALIGN_CENTER_VERTICAL)

        target_sizer.Add(self.target_list, 1, wx.EXPAND | wx.ALL, 6)
        target_sizer.Add(target_btn_row, 0, wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        target_sizer.Add(transform_row, 0, wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        main_sizer.Add(target_sizer, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # ---------------------------------------------------------------------
        # 3. Sección: Barra Inferior de Acciones
        # ---------------------------------------------------------------------
        separator = wx.StaticLine(self, wx.ID_ANY, style=wx.LI_HORIZONTAL)
        main_sizer.Add(separator, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        options_row = wx.BoxSizer(wx.HORIZONTAL)
        self.chk_create_groups = wx.CheckBox(
            self, label="Agrupar componentes en KiCad (PCB_GROUP)"
        )
        self.chk_create_groups.SetValue(bool(self.config.get("create_groups_default", True)))
        self.chk_replicate_tracks = wx.CheckBox(
            self, label="Replicar cobre de la referencia (pistas, vías, zonas, formas)"
        )
        self.chk_replicate_tracks.SetValue(bool(self.config.get("replicate_tracks_default", False)))

        options_row.Add(self.chk_create_groups, 0, wx.RIGHT | wx.TOP | wx.BOTTOM, 12)
        options_row.Add(self.chk_replicate_tracks, 0, wx.LEFT | wx.TOP | wx.BOTTOM, 6)
        main_sizer.Add(options_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        bottom_row = wx.BoxSizer(wx.HORIZONTAL)
        self.summary_status = wx.StaticText(self, label="Listo.")
        self.summary_status.SetForegroundColour(wx.Colour(100, 100, 100))

        self.btn_preview = wx.Button(self, label="3. Vista previa y aplicar")
        self.btn_close = wx.Button(self, wx.ID_CANCEL, label="Cerrar")

        self.btn_preview.Bind(wx.EVT_BUTTON, self.align_targets)
        self.btn_close.Bind(wx.EVT_BUTTON, lambda _evt: self.Close())

        bottom_row.Add(self.summary_status, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)
        bottom_row.Add(self.btn_preview, 0, wx.ALL, 6)
        bottom_row.Add(self.btn_close, 0, wx.ALL, 6)

        main_sizer.Add(bottom_row, 0, wx.EXPAND | wx.ALL, 6)
        self.SetSizer(main_sizer)
        self._update_ui_state()

    def _update_ui_state(self):
        """Update enable/disable status of buttons based on current state and selection."""
        has_reference = bool(self.reference)
        has_targets = bool(self.targets)
        selected_row = self.target_list.GetFirstSelected()
        has_target_selected = selected_row != -1 and selected_row < len(self.targets)

        self.btn_view_ref.Enable(has_reference)
        self.anchor_choice.Enable(has_reference)
        self.btn_add_target.Enable(has_reference)
        self.btn_auto_discover.Enable(has_reference)
        self.btn_remove_target.Enable(has_target_selected)
        self.btn_view_target.Enable(has_target_selected)
        self.btn_inspect_error.Enable(has_target_selected and has_reference)
        self.btn_export_log.Enable(has_reference)
        self.btn_rot_ccw.Enable(has_target_selected)
        self.btn_rot_cw.Enable(has_target_selected)
        self.rotation_spin.Enable(has_target_selected)
        self.chk_mirror.Enable(has_target_selected)
        self.btn_clear.Enable(has_reference or has_targets)
        self.btn_preview.Enable(has_reference and has_targets)

        if has_target_selected:
            entry = self.targets[selected_row]
            self.rotation_spin.SetValue(float(entry.get("rotation", 0.0)))
            self.chk_mirror.SetValue(bool(entry.get("mirror_x", False)))
        else:
            self.rotation_spin.SetValue(0)
            self.chk_mirror.SetValue(False)

    def _on_target_selection_change(self, _event):
        self._update_ui_state()

    def _on_target_activated(self, event):
        selected_idx = self.target_list.GetFirstSelected()
        if selected_idx == -1 or selected_idx >= len(self.targets):
            return
        target_fps = self.targets[selected_idx]["footprints"]
        if self.reference:
            errors, _ = core.validate_block(self.reference, target_fps)
            if errors:
                self.show_error_details(event)
                return
        self.view_target_in_pcb(event)

    def _on_key_down(self, event):
        keycode = event.GetKeyCode()
        if keycode in (ord("R"), ord("r")):
            if event.ShiftDown():
                self._on_rotate_ccw(None)
            else:
                self._on_rotate_cw(None)
            return
        elif keycode == wx.WXK_DELETE:
            if self.target_list.GetFirstSelected() != -1:
                self.remove_target(None)
            return
        event.Skip()

    def _on_rotate_cw(self, _event):
        selected_idx = self.target_list.GetFirstSelected()
        if selected_idx != -1 and selected_idx < len(self.targets):
            current_rot = float(self.targets[selected_idx].get("rotation", 0.0))
            new_rot = (current_rot + 90.0) % 360.0
            self.targets[selected_idx]["rotation"] = new_rot
            self.rotation_spin.SetValue(new_rot)
            self.target_list.SetItem(selected_idx, 3, self._rot_display(self.targets[selected_idx]))
            self.summary_status.SetLabel(
                "Destino {}: Rotación configurada en {}.".format(selected_idx + 1, self._fmt_angle(new_rot))
            )

    def _on_rotate_ccw(self, _event):
        selected_idx = self.target_list.GetFirstSelected()
        if selected_idx != -1 and selected_idx < len(self.targets):
            current_rot = float(self.targets[selected_idx].get("rotation", 0.0))
            new_rot = (current_rot - 90.0) % 360.0
            self.targets[selected_idx]["rotation"] = new_rot
            self.rotation_spin.SetValue(new_rot)
            self.target_list.SetItem(selected_idx, 3, self._rot_display(self.targets[selected_idx]))
            self.summary_status.SetLabel(
                "Destino {}: Rotación configurada en {}.".format(selected_idx + 1, self._fmt_angle(new_rot))
            )

    def _on_rotation_changed(self, _event):
        selected_idx = self.target_list.GetFirstSelected()
        if selected_idx != -1 and selected_idx < len(self.targets):
            rot = float(self.rotation_spin.GetValue())
            self.targets[selected_idx]["rotation"] = rot
            self.target_list.SetItem(selected_idx, 3, self._rot_display(self.targets[selected_idx]))
            self.summary_status.SetLabel(
                "Destino {}: Rotación configurada en {}.".format(selected_idx + 1, self._fmt_angle(rot))
            )

    def _on_mirror_changed(self, _event):
        selected_idx = self.target_list.GetFirstSelected()
        if selected_idx != -1 and selected_idx < len(self.targets):
            self.targets[selected_idx]["mirror_x"] = bool(self.chk_mirror.GetValue())
            self.target_list.SetItem(selected_idx, 3, self._rot_display(self.targets[selected_idx]))
            state = "activado" if self.targets[selected_idx]["mirror_x"] else "desactivado"
            self.summary_status.SetLabel(
                "Destino {}: Espejo X {}.".format(selected_idx + 1, state)
            )

    def _on_anchor_changed(self, _event):
        anchor_name = self.anchor_choice.GetStringSelection()
        self.summary_status.SetLabel("Punto de anclaje seleccionado: {}.".format(anchor_name))

    def _update_targets_table(self):
        """Refresh the target ListCtrl with current targets and validation status."""
        self.target_list.DeleteAllItems()
        for idx, entry in enumerate(self.targets, 1):
            target_fps = entry["footprints"]
            item_idx = self.target_list.InsertItem(idx - 1, str(idx))
            refs_str = core.format_references(target_fps, max_display=10)
            self.target_list.SetItem(item_idx, 1, refs_str)
            self.target_list.SetItem(item_idx, 2, "{} fps".format(len(target_fps)))
            self.target_list.SetItem(item_idx, 3, self._rot_display(entry))

            if self.reference:
                errors, matched = core.validate_block(self.reference, target_fps)
                if errors:
                    self.target_list.SetItem(item_idx, 4, "✕ Error: {}".format(errors[0]))
                    self.target_list.SetItemTextColour(item_idx, wx.Colour(180, 20, 20))
                    self.target_list.SetItemBackgroundColour(item_idx, wx.Colour(255, 240, 240))
                else:
                    self.target_list.SetItem(item_idx, 4, "✓ Válido ({} coincidentes)".format(matched))
                    self.target_list.SetItemTextColour(item_idx, wx.Colour(20, 120, 20))
                    self.target_list.SetItemBackgroundColour(item_idx, wx.Colour(240, 252, 240))
            else:
                self.target_list.SetItem(item_idx, 4, "Pendiente de referencia")

        self.summary_status.SetLabel("Destinos registrados: {}.".format(len(self.targets)))
        self._update_ui_state()

    def _log_dir(self):
        return os.path.expanduser(str(self.config.get("log_dir", "~/Block_Aligner")))

    def _write_log(self, report):
        try:
            log_dir = self._log_dir()
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "debug_log.txt")
            with open(log_path, "w", encoding="utf-8") as handle:
                handle.write(report)
            return True
        except OSError as exc:
            self.summary_status.SetLabel("No se pudo guardar el diagnóstico: {}".format(exc))
            return False

    def capture_reference(self, _event):
        try:
            self.board = pcbnew.GetBoard()
        except Exception:
            pass
        selected = tracks.select_footprints(self.board)
        if not selected:
            wx.MessageBox(
                "Selecciona primero los footprints del bloque de referencia en PCB Editor.",
                "Block Aligner",
                wx.OK | wx.ICON_WARNING,
            )
            return
        self.reference = selected
        ref_tracks = tracks.collect_reference_tracks(self.board, selected, self.config)
        refs = sorted(fp.GetReference() for fp in selected)
        refs_str = core.format_references(selected, max_display=12)
        track_info = ", {} pistas/vías".format(len(ref_tracks)) if ref_tracks else ""
        self.ref_status.SetLabel(
            "✓ Referencia capturada: {} footprints{}".format(len(selected), track_info)
        )
        self.ref_details.SetLabel("Componentes: {}".format(refs_str))

        current_anchor = self.anchor_choice.GetStringSelection()
        choices = ["Centroide del bloque"] + refs
        self.anchor_choice.Clear()
        self.anchor_choice.Append(choices)
        if current_anchor in choices:
            self.anchor_choice.SetStringSelection(current_anchor)
        else:
            self.anchor_choice.SetSelection(0)

        self._update_targets_table()

    def view_reference_in_pcb(self, _event):
        if not self.reference:
            return
        tracks.select_in_board(self.board, self.reference)
        self.summary_status.SetLabel(
            "Referencia seleccionada en PCB ({} footprints).".format(len(self.reference))
        )

    def view_target_in_pcb(self, _event):
        selected_idx = self.target_list.GetFirstSelected()
        if selected_idx == -1 or selected_idx >= len(self.targets):
            return
        target_fps = self.targets[selected_idx]["footprints"]
        tracks.select_in_board(self.board, target_fps)
        self.summary_status.SetLabel(
            "Destino {} seleccionado en PCB ({} footprints).".format(selected_idx + 1, len(target_fps))
        )

    def show_error_details(self, _event):
        selected_idx = self.target_list.GetFirstSelected()
        if selected_idx == -1 or selected_idx >= len(self.targets):
            return
        if not self.reference:
            wx.MessageBox(
                "Captura primero un bloque de referencia para diagnosticar discrepancias.",
                "Block Aligner",
                wx.OK | wx.ICON_INFORMATION,
            )
            return
        target_fps = self.targets[selected_idx]["footprints"]
        diag = core.diagnose_block(self.reference, target_fps)
        dlg = ErrorDetailsDialog(self, selected_idx + 1, diag)
        dlg.ShowModal()
        dlg.Destroy()

    def export_diagnostic_log(self, _event):
        if not self.reference:
            wx.MessageBox(
                "Captura primero un bloque de referencia para generar el diagnóstico.",
                "Diagnóstico",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return
        discovered = discovery.auto_discover_blocks(self.board, self.reference, self.targets, self.config)
        report = generate_diagnostic_report(self.board, self.reference, self.targets, discovered)
        self._write_log(report)

        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(report))
            wx.TheClipboard.Close()

        dlg = DiagnosticLogDialog(self, report)
        dlg.ShowModal()
        dlg.Destroy()

    def auto_discover(self, _event):
        if not self.reference:
            wx.MessageBox(
                "Captura primero el bloque de referencia antes de auto-detectar.",
                "Block Aligner",
                wx.OK | wx.ICON_WARNING,
            )
            return

        try:
            self.board = pcbnew.GetBoard()
        except Exception:
            pass

        if not self._validate_schematic_sync():
            return

        if self.targets:
            confirm = wx.MessageDialog(
                self,
                "Ya hay {} destino(s) registrado(s). La auto-detección los reemplazará.\n\n¿Continuar?".format(len(self.targets)),
                "Auto-Detección de Bloques",
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
            )
            if confirm.ShowModal() != wx.ID_YES:
                confirm.Destroy()
                return
            confirm.Destroy()

        self.targets = []

        wx.BeginBusyCursor()
        try:
            def progress(done, total):
                self.summary_status.SetLabel("Auto-detección: analizando bloque {}/{}...".format(done, total))
                wx.SafeYield()

            discovered = discovery.auto_discover_blocks(
                self.board, self.reference, [], self.config, progress_cb=progress
            )
        finally:
            wx.EndBusyCursor()

        report = generate_diagnostic_report(self.board, self.reference, self.targets, discovered)
        self._write_log(report)

        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(report))
            wx.TheClipboard.Close()

        if not discovered:
            self._update_targets_table()
            wx.MessageBox(
                "No se encontraron bloques adicionales coincidentes con la referencia en la PCB.\n\n"
                "Se ha guardado un informe en 'debug_log.txt' y puedes verlo con el botón '📋 Diagnóstico'.",
                "Auto-Detección de Bloques",
                wx.OK | wx.ICON_INFORMATION,
            )
            return
        for block in discovered:
            self.targets.append({"footprints": block, "rotation": 0.0, "mirror_x": False})
        self._update_targets_table()
        wx.MessageBox(
            "Se auto-detectaron y añadieron {} bloque(s) destino válido(s).\n\n"
            "📄 El log de diagnóstico se ha guardado en 'debug_log.txt' y copiado a tu portapapeles.".format(len(discovered)),
            "Auto-Detección de Bloques",
            wx.OK | wx.ICON_INFORMATION,
        )

    def _validate_schematic_sync(self):
        """Block unsafe auto-discovery when saved schematic and PCB nets differ."""
        self.summary_status.SetLabel("Comprobando sincronización con el esquemático...")
        wx.BeginBusyCursor()
        try:
            exported = schematic.export_pin_nets(self.board)
        finally:
            wx.EndBusyCursor()

        if not exported["available"]:
            self.summary_status.SetLabel(
                "No se pudo verificar el esquemático: {}".format(exported["reason"])
            )
            return True

        reference_keys = {core.footprint_key(fp) for fp in self.reference}
        candidates = [
            fp for fp in self.board.GetFootprints()
            if core.footprint_key(fp) in reference_keys
        ]
        mismatches = schematic.compare_footprint_nets(
            candidates, exported["pin_nets"]
        )
        if not mismatches:
            self.summary_status.SetLabel(
                "PCB sincronizada con el esquemático; iniciando auto-detección."
            )
            return True

        samples = mismatches[:10]
        detail_lines = []
        for item in samples:
            detail_lines.append(
                "{} pad {}: PCB='{}' | Esquema='{}'".format(
                    item["reference"], item["pin"],
                    item["pcb_net"] or "(sin red)", item["schematic_net"],
                )
            )
        if len(mismatches) > len(samples):
            detail_lines.append(
                "... y {} diferencia(s) más.".format(len(mismatches) - len(samples))
            )

        report = (
            "=== PCB / SCHEMATIC SYNC CHECK ===\n"
            "Schematic: {}\n"
            "Mismatched pads: {}\n\n{}\n".format(
                exported.get("schematic_path", ""),
                len(mismatches),
                "\n".join(detail_lines),
            )
        )
        self._write_log(report)
        self.summary_status.SetLabel(
            "Auto-detección detenida: PCB y esquemático no están sincronizados."
        )
        wx.MessageBox(
            "El PCB no coincide con el esquemático guardado ({} pads diferentes).\n\n"
            "Guarda el esquemático, ejecuta F8 (Actualizar PCB desde el esquemático), "
            "guarda el PCB y vuelve a capturar la referencia.\n\n"
            "Ejemplos:\n{}\n\nEl diagnóstico completo se guardó en debug_log.txt.".format(
                len(mismatches), "\n".join(detail_lines)
            ),
            "PCB desactualizada",
            wx.OK | wx.ICON_WARNING,
        )
        return False

    def add_target(self, _event):
        if not self.reference:
            wx.MessageBox(
                "Captura primero el bloque de referencia antes de añadir destinos.",
                "Block Aligner",
                wx.OK | wx.ICON_WARNING,
            )
            return
        try:
            self.board = pcbnew.GetBoard()
        except Exception:
            pass
        selected = tracks.select_footprints(self.board)
        if not selected:
            wx.MessageBox(
                "Selecciona un bloque de footprints destino en PCB Editor.",
                "Block Aligner",
                wx.OK | wx.ICON_WARNING,
            )
            return
        selected_refs = {fp.GetReference() for fp in selected}
        reference_refs = {fp.GetReference() for fp in self.reference}
        if selected_refs & reference_refs:
            wx.MessageBox(
                "El destino contiene footprints del bloque de referencia.",
                "Block Aligner",
                wx.OK | wx.ICON_ERROR,
            )
            return
        registered_refs = {
            fp.GetReference()
            for entry in self.targets
            for fp in entry["footprints"]
        }
        overlap = selected_refs & registered_refs
        if overlap:
            wx.MessageBox(
                "El destino se solapa con otro destino ya registrado: {}.".format(", ".join(sorted(overlap))),
                "Block Aligner",
                wx.OK | wx.ICON_ERROR,
            )
            return
        self.targets.append({"footprints": selected, "rotation": 0.0, "mirror_x": False})
        self._update_targets_table()

    def remove_target(self, _event):
        selected_idx = self.target_list.GetFirstSelected()
        if selected_idx == -1:
            wx.MessageBox(
                "Selecciona un destino en la tabla para eliminarlo.",
                "Block Aligner",
                wx.OK | wx.ICON_INFORMATION,
            )
            return
        del self.targets[selected_idx]
        self._update_targets_table()

    def align_targets(self, _event):
        if not self.reference or not self.targets:
            wx.MessageBox(
                "Captura una referencia y añade al menos un destino antes de alinear.",
                "Block Aligner",
                wx.OK | wx.ICON_WARNING,
            )
            return

        errors = []
        summary = []
        plans = []
        anchor_name = self.anchor_choice.GetStringSelection()
        replicate_tracks = self.chk_replicate_tracks.GetValue()

        ref_tracks, ref_zones, ref_shapes = [], [], []
        if replicate_tracks:
            ref_tracks = tracks.collect_reference_tracks(self.board, self.reference, self.config)
            ref_zones, ref_shapes = tracks.collect_reference_zones_and_shapes(
                self.board, self.reference, self.config
            )

        for index, entry in enumerate(self.targets, 1):
            target_fps = entry["footprints"]
            rot = float(entry.get("rotation", 0.0))
            mirror_x = bool(entry.get("mirror_x", False))
            validation_errors, matched = core.validate_block(self.reference, target_fps)
            if validation_errors:
                errors.append("Destino {}: {}".format(index, "; ".join(validation_errors)))
                continue

            ok, plan = core.plan_block(
                self.reference, target_fps,
                anchor_ref_name=anchor_name, rotation=rot, mirror_x=mirror_x,
            )
            if not ok:
                errors.append("Destino {}: {}".format(index, plan))
                continue

            if replicate_tracks:
                track_plan = tracks.plan_tracks(
                    self.board, plan["pairs"], ref_tracks,
                    plan["ref_origin"], plan["target_origin"], rot, mirror_x,
                    zones=ref_zones, shapes=ref_shapes,
                )
                plan["cloned_tracks"] = track_plan["cloned_tracks"]
                plan["omitted_count"] = track_plan["omitted_count"]
            else:
                plan["cloned_tracks"] = []
                plan["omitted_count"] = 0

            # Keep rotation/mirror for the commit pass (fresh re-clone).
            plan["_rotation"] = rot
            plan["_mirror_x"] = mirror_x

            plans.append(plan)

            track_count = len(plan["cloned_tracks"])
            omitted = plan["omitted_count"]
            copper_info = ", {} cobre".format(track_count) if track_count else ""
            if omitted:
                copper_info += " ({} omitidas sin red válida)".format(omitted)
            mirror_info = " + Espejo X" if mirror_x else ""
            summary.append(
                "Destino {}: {} footprints{} (Rotación: {}{})".format(
                    index, matched, copper_info, self._fmt_angle(rot), mirror_info
                )
            )

        if errors:
            wx.MessageBox(
                "No se aplicaron cambios debido a errores de validación:\n\n{}\n\n"
                "Puedes pulsar 'Detalles error' para inspeccionar qué componentes fallaron.".format(
                    "\n".join(errors)
                ),
                "Validación de Block Aligner",
                wx.OK | wx.ICON_ERROR,
            )
            return

        # F7: avisar de solapamiento espacial entre bloques destino planificados.
        bboxes = core.planned_bboxes([p["footprint_plan"] for p in plans])
        overlaps = core.overlapping_pairs(bboxes, self.config["overlap_margin_nm"])
        if overlaps:
            overlap_msg = wx.MessageDialog(
                self,
                "Los siguientes bloques destino quedarán solapados espacialmente:\n\n{}\n\n"
                "¿Continuar de todos modos?".format(
                    "\n".join("Destino {} y {}".format(a, b) for a, b in overlaps)
                ),
                "Solapamiento de bloques",
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
            )
            if overlap_msg.ShowModal() != wx.ID_YES:
                overlap_msg.Destroy()
                self.summary_status.SetLabel("Alineación cancelada por solapamiento.")
                return
            overlap_msg.Destroy()

        # Guardar posiciones y orientaciones originales para revertir la vista previa.
        original_positions = []
        for plan in plans:
            for target_fp, x, y, source_fp, rot, mirror in plan["footprint_plan"]:
                original_positions.append(
                    (target_fp, core.position(target_fp), target_fp.GetOrientation())
                )

        # Aplicación temporal (vista previa). Si falla cualquier objeto, se
        # restaura todo y nunca se deja una previsualización parcial.
        created_tracks = []
        try:
            for plan in plans:
                tracks.apply_plan(plan["footprint_plan"])
                for track in plan["cloned_tracks"]:
                    self.board.Add(track)
                    created_tracks.append(track)
        except Exception as exc:
            self._rollback_preview(original_positions, created_tracks)
            wx.MessageBox(
                "No se pudo generar la vista previa. La PCB fue restaurada.\n\n{}".format(exc),
                "Error de vista previa",
                wx.OK | wx.ICON_ERROR,
            )
            return
        pcbnew.Refresh()

        confirmation = wx.MessageDialog(
            self,
            "Aplicación temporal (vista previa). Los footprints y el cobre se muestran ahora "
            "en sus nuevas posiciones (Anclaje: {}, rotaciones/espejos aplicados).\n\n{}\n\n"
            "¿Aplicar definitivamente estos cambios?".format(anchor_name, "\n".join(summary)),
            "Vista previa de Block Aligner",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
        )
        proceed = confirmation.ShowModal() == wx.ID_YES
        confirmation.Destroy()

        if not proceed:
            self._rollback_preview(original_positions, created_tracks)
            self.summary_status.SetLabel("Vista previa cancelada. Posiciones y cobre restaurados.")
            return

        # BOARD_COMMIT pertenece a la API C++ y no está exportado por todas las
        # versiones de pcbnew/SWIG (incluido KiCad 10 en varias distribuciones).
        # En ese caso la vista previa confirmada ya contiene la alineación final:
        # la conservamos y añadimos los grupos con rollback manual ante errores.
        if not hasattr(pcbnew, "BOARD_COMMIT"):
            created_groups = []
            try:
                if self.chk_create_groups.GetValue():
                    for index, plan in enumerate(plans, 1):
                        group_items = plan["target_footprints"] + plan["cloned_tracks"]
                        group = tracks.create_pcb_group(
                            self.board,
                            group_items,
                            group_name="Bloque_Destino_{}".format(index),
                        )
                        if group is None:
                            raise RuntimeError(
                                "KiCad no pudo crear el grupo del destino {}.".format(index)
                            )
                        created_groups.append(group)
            except Exception as exc:
                for group in reversed(created_groups):
                    try:
                        self.board.Remove(group)
                    except Exception:
                        pass
                self._rollback_preview(original_positions, created_tracks)
                wx.MessageBox(
                    "No se pudo completar la alineación. La PCB fue restaurada.\n\n{}".format(exc),
                    "Error al aplicar Block Aligner",
                    wx.OK | wx.ICON_ERROR,
                )
                return

            pcbnew.Refresh()
            total_copper = len(created_tracks)
            copper_msg = (
                " y {} elementos de cobre replicados".format(total_copper)
                if total_copper else ""
            )
            self.summary_status.SetLabel(
                "Alineación aplicada con éxito{} (sin Ctrl+Z nativo).".format(copper_msg)
            )
            wx.MessageBox(
                "Alineación aplicada con éxito{}.\n\n"
                "Tu versión de pcbnew no expone el deshacer nativo para plugins. "
                "Guarda la PCB solo después de revisar el resultado.".format(copper_msg),
                "Block Aligner",
                wx.OK | wx.ICON_INFORMATION,
            )
            return

        # F1: revertir la vista previa y volver a aplicar dentro de un commit
        # nativo para que Ctrl+Z deshaga la alineación completa.
        created_groups = []
        try:
            commit = pcbnew.BOARD_COMMIT(self.board)
            # 1. Restaurar footprints a su estado original.
            for target_fp, (x, y), old_orientation in original_positions:
                tracks.set_position(target_fp, x, y)
                target_fp.SetOrientation(old_orientation)
            # 2. Eliminar el cobre de la vista previa.
            for track in created_tracks:
                try:
                    self.board.Remove(track)
                except Exception:
                    pass
            created_tracks = []

            # 3. Reaplicar bajo commit, con cobre recién clonado.
            for plan in plans:
                for target_fp, x, y, source_fp, rot, mirror in plan["footprint_plan"]:
                    commit.Modify(target_fp)
                    tracks.set_position(target_fp, x, y)
                    tracks.set_orientation_with_rotation(target_fp, source_fp, rot, mirror)

                if replicate_tracks:
                    fresh = tracks.plan_tracks(
                        self.board, plan["pairs"], ref_tracks,
                        plan["ref_origin"], plan["target_origin"],
                        plan["_rotation"], plan["_mirror_x"],
                        zones=ref_zones, shapes=ref_shapes,
                    )
                    plan["cloned_tracks"] = fresh["cloned_tracks"]
                for track in plan["cloned_tracks"]:
                    commit.Add(track)
                    created_tracks.append(track)

            # Los grupos forman parte del mismo commit que footprints y cobre.
            if self.chk_create_groups.GetValue():
                for index, plan in enumerate(plans, 1):
                    group_items = plan["target_footprints"] + plan["cloned_tracks"]
                    group = tracks.create_pcb_group(
                        self.board,
                        group_items,
                        group_name="Bloque_Destino_{}".format(index),
                        add_to_board=False,
                    )
                    if group is None:
                        raise RuntimeError(
                            "KiCad no pudo crear el grupo del destino {}.".format(index)
                        )
                    commit.Add(group)
                    created_groups.append(group)

            commit.Push("Block Aligner: alinear bloques")
        except Exception as exc:
            try:
                commit.Revert()
            except Exception:
                # Algunas versiones antiguas de los bindings no exponen
                # Revert(); el rollback manual de abajo sigue siendo obligatorio.
                pass
            for group in reversed(created_groups):
                try:
                    self.board.Remove(group)
                except Exception:
                    pass
            self._rollback_preview(original_positions, created_tracks)
            wx.MessageBox(
                "No fue posible registrar una operación segura para Ctrl+Z. "
                "La alineación se canceló y la PCB fue restaurada.\n\n{}".format(exc),
                "Error al aplicar Block Aligner",
                wx.OK | wx.ICON_ERROR,
            )
            return
        pcbnew.Refresh()

        total_copper = len(created_tracks)
        copper_msg = " y {} elementos de cobre replicados".format(total_copper) if total_copper else ""
        undo_msg = "Puedes deshacer toda la operación con Ctrl+Z."
        self.summary_status.SetLabel("Alineación aplicada con éxito{}.".format(copper_msg))
        wx.MessageBox(
            "Alineación aplicada con éxito{}.\n{}".format(copper_msg, undo_msg),
            "Block Aligner",
            wx.OK | wx.ICON_INFORMATION,
        )

    def _rollback_preview(self, original_positions, created_items):
        """Restore a preview without leaving partial changes on the board."""
        for target_fp, (x, y), old_orientation in original_positions:
            tracks.set_position(target_fp, x, y)
            target_fp.SetOrientation(old_orientation)
        for item in reversed(created_items):
            try:
                self.board.Remove(item)
            except Exception:
                pass
        pcbnew.Refresh()

    def clear(self, _event):
        self.reference = []
        self.targets = []
        self.ref_status.SetLabel("Ningún bloque de referencia capturado.")
        self.ref_details.SetLabel(
            "Selecciona los footprints en PCB Editor y haz clic en 'Capturar referencia'."
        )
        self.anchor_choice.Clear()
        self.anchor_choice.Append(["Centroide del bloque"])
        self.anchor_choice.SetSelection(0)
        self.rotation_spin.SetValue(0)
        self.chk_mirror.SetValue(False)
        self._update_targets_table()
        self.summary_status.SetLabel("Listo.")
