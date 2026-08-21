"""Align repeated PCB blocks using a selected reference block.

This first version moves footprints only. It deliberately does not touch tracks,
zones, nets, or schematic data.
"""

import os

import pcbnew
import wx


def footprint_name(footprint):
    """Return a stable library footprint name across KiCad API variants."""
    try:
        return str(footprint.GetFPID().GetLibItemName())
    except AttributeError:
        try:
            return str(footprint.GetFPID().GetLibId())
        except AttributeError:
            return ""


def footprint_key(footprint):
    """Properties that identify equivalent component roles in a block."""
    pad_count = len(list(footprint.Pads()))
    return (str(footprint.GetValue()), footprint_name(footprint), pad_count)


def position(footprint):
    point = footprint.GetPosition()
    return int(point[0]), int(point[1])


def set_position(footprint, x, y):
    try:
        footprint.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
    except TypeError:
        footprint.SetPosition(pcbnew.wxPoint(int(x), int(y)))


def set_orientation(footprint, source):
    """Copy KiCad's native angle object instead of converting units."""
    footprint.SetOrientation(source.GetOrientation())


def select_footprints(board):
    return [fp for fp in board.GetFootprints() if fp.IsSelected()]


def pad_net_id(pad):
    """Get a net identifier without relying on the net name."""
    try:
        return int(pad.GetNetCode())
    except AttributeError:
        return str(pad.GetNetname())


def connectivity_signature(footprint, block):
    """Describe this footprint's connections to other footprints in its block.

    Net names and net codes are intentionally omitted because repeated schematic
    blocks normally use different nets. External connections are represented by
    an empty peer list.
    """
    peers_by_pad = []
    for pad in footprint.Pads():
        net_id = pad_net_id(pad)
        peers = []
        if net_id not in (0, "", None):
            for other in block:
                if other is footprint:
                    continue
                for other_pad in other.Pads():
                    if pad_net_id(other_pad) == net_id:
                        peers.append(
                            (
                                footprint_key(other),
                                str(other_pad.GetNumber()),
                            )
                        )
        peers_by_pad.append(
            (
                str(pad.GetNumber()),
                tuple(sorted(peers)) if peers else ("external",),
            )
        )
    return tuple(sorted(peers_by_pad))


def centroid(footprints):
    xs = [position(fp)[0] for fp in footprints]
    ys = [position(fp)[1] for fp in footprints]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def ordered_components(footprints, center, block):
    """Group equivalent parts and order duplicates by circuit role."""
    groups = {}
    for footprint in footprints:
        groups.setdefault(footprint_key(footprint), []).append(footprint)

    result = {}
    for key, group in groups.items():
        result[key] = sorted(
            group,
            key=lambda fp: (
                connectivity_signature(fp, block),
                position(fp)[1] - center[1],
                position(fp)[0] - center[0],
                fp.GetReference(),
            ),
        )
    return result


def plan_block(reference, target):
    ref_center = centroid(reference)
    target_center = centroid(target)
    ref_groups = ordered_components(reference, ref_center, reference)
    target_groups = ordered_components(target, target_center, target)

    if set(ref_groups) != set(target_groups):
        return False, "Los componentes o footprints no coinciden."

    for key, ref_parts in ref_groups.items():
        target_parts = target_groups[key]
        if len(ref_parts) != len(target_parts):
            return False, "La cantidad de componentes equivalentes no coincide."

    plan = []
    for key, ref_parts in ref_groups.items():
        for ref_fp, target_fp in zip(ref_parts, target_groups[key]):
            ref_x, ref_y = position(ref_fp)
            new_x = target_center[0] + (ref_x - ref_center[0])
            new_y = target_center[1] + (ref_y - ref_center[1])
            if target_fp.IsLocked():
                return False, "El footprint {} está bloqueado.".format(
                    target_fp.GetReference()
                )
            plan.append((target_fp, new_x, new_y, ref_fp))

    return True, plan


def apply_plan(plan):
    for target_fp, x, y, source_fp in plan:
        set_position(target_fp, x, y)
        set_orientation(target_fp, source_fp)


def validate_block(reference, target):
    """Validate a destination without changing the board."""
    errors = []
    if any(target_fp.GetReference() == ref_fp.GetReference() for target_fp in target for ref_fp in reference):
        errors.append("incluye footprints del bloque de referencia")

    ref_groups = ordered_components(reference, centroid(reference), reference)
    target_groups = ordered_components(target, centroid(target), target)
    if set(ref_groups) != set(target_groups):
        errors.append("sus componentes o footprints no coinciden")
    else:
        for key, ref_parts in ref_groups.items():
            if len(ref_parts) != len(target_groups[key]):
                errors.append("la cantidad de componentes equivalentes no coincide")
                break

    locked = [fp.GetReference() for fp in target if fp.IsLocked()]
    if locked:
        errors.append("tiene footprints bloqueados: {}".format(", ".join(locked)))

    matched = min(len(reference), len(target)) if not errors else 0
    return errors, matched


def format_references(footprints, max_display=8):
    """Format a readable list of footprint reference designators."""
    if not footprints:
        return "Ninguno"
    refs = sorted(fp.GetReference() for fp in footprints)
    if len(refs) <= max_display:
        return ", ".join(refs)
    return ", ".join(refs[:max_display]) + f", ... (+{len(refs) - max_display} más)"


class BlockAlignerDialog(wx.Dialog):
    def __init__(self, parent, board):
        super().__init__(
            parent,
            title="Block Aligner",
            size=(820, 560),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.SetMinSize((680, 480))
        self.board = board
        self.reference = []
        self.targets = []

        self._init_ui()

    def _init_ui(self):
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ---------------------------------------------------------------------
        # 1. Sección: Bloque de Referencia
        # ---------------------------------------------------------------------
        ref_box = wx.StaticBox(self, label=" 1. Bloque de Referencia ")
        ref_sizer = wx.StaticBoxSizer(ref_box, wx.VERTICAL)

        ref_top_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_capture = wx.Button(self, label="Capturar referencia")
        self.btn_capture.Bind(wx.EVT_BUTTON, self.capture_reference)

        self.ref_status = wx.StaticText(
            self, label="Ningún bloque de referencia capturado."
        )
        bold_font = self.ref_status.GetFont().Bold()
        self.ref_status.SetFont(bold_font)

        ref_top_row.Add(self.btn_capture, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 10)
        ref_top_row.Add(self.ref_status, 1, wx.ALIGN_CENTER_VERTICAL)

        self.ref_details = wx.StaticText(
            self,
            label="Selecciona los footprints en PCB Editor y haz clic en 'Capturar referencia'.",
        )
        self.ref_details.SetForegroundColour(wx.Colour(120, 120, 120))

        ref_sizer.Add(ref_top_row, 0, wx.EXPAND | wx.ALL, 6)
        ref_sizer.Add(
            self.ref_details, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6
        )
        main_sizer.Add(ref_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # ---------------------------------------------------------------------
        # 2. Sección: Bloques Destino
        # ---------------------------------------------------------------------
        target_box = wx.StaticBox(self, label=" 2. Bloques Destino ")
        target_sizer = wx.StaticBoxSizer(target_box, wx.VERTICAL)

        # Tabla estructurada de destinos
        self.target_list = wx.ListCtrl(
            self,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN,
        )
        self.target_list.InsertColumn(0, "#", wx.LIST_FORMAT_CENTER, 45)
        self.target_list.InsertColumn(
            1, "Footprints / Componentes", wx.LIST_FORMAT_LEFT, 330
        )
        self.target_list.InsertColumn(2, "Cantidad", wx.LIST_FORMAT_CENTER, 85)
        self.target_list.InsertColumn(
            3, "Estado de Validación", wx.LIST_FORMAT_LEFT, 260
        )

        # Botones de gestión de destinos
        target_btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_add_target = wx.Button(self, label="Añadir selección")
        self.btn_remove_target = wx.Button(self, label="Eliminar destino")
        self.btn_clear = wx.Button(self, label="Limpiar todo")

        self.btn_add_target.Bind(wx.EVT_BUTTON, self.add_target)
        self.btn_remove_target.Bind(wx.EVT_BUTTON, self.remove_target)
        self.btn_clear.Bind(wx.EVT_BUTTON, self.clear)

        target_btn_row.Add(self.btn_add_target, 0, wx.RIGHT, 6)
        target_btn_row.Add(self.btn_remove_target, 0, wx.RIGHT, 6)
        target_btn_row.Add(self.btn_clear, 0, wx.RIGHT, 6)

        target_sizer.Add(self.target_list, 1, wx.EXPAND | wx.ALL, 6)
        target_sizer.Add(
            target_btn_row, 0, wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6
        )
        main_sizer.Add(target_sizer, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # ---------------------------------------------------------------------
        # 3. Sección: Barra Inferior de Acciones
        # ---------------------------------------------------------------------
        separator = wx.StaticLine(self, wx.ID_ANY, style=wx.LI_HORIZONTAL)
        main_sizer.Add(separator, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        bottom_row = wx.BoxSizer(wx.HORIZONTAL)
        self.summary_status = wx.StaticText(self, label="Listo.")
        self.summary_status.SetForegroundColour(wx.Colour(100, 100, 100))

        self.btn_preview = wx.Button(self, label="Vista previa")
        self.btn_close = wx.Button(self, wx.ID_CANCEL, label="Cerrar")

        self.btn_preview.Bind(wx.EVT_BUTTON, self.align_targets)
        self.btn_close.Bind(wx.EVT_BUTTON, lambda _evt: self.Close())

        bottom_row.Add(self.summary_status, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)
        bottom_row.Add(self.btn_preview, 0, wx.ALL, 6)
        bottom_row.Add(self.btn_close, 0, wx.ALL, 6)

        main_sizer.Add(bottom_row, 0, wx.EXPAND | wx.ALL, 6)
        self.SetSizer(main_sizer)

    def _update_targets_table(self):
        """Refresh the target ListCtrl with current targets and validation status."""
        self.target_list.DeleteAllItems()
        for idx, target in enumerate(self.targets, 1):
            item_idx = self.target_list.InsertItem(idx - 1, str(idx))
            refs_str = format_references(target, max_display=10)
            self.target_list.SetItem(item_idx, 1, refs_str)
            self.target_list.SetItem(item_idx, 2, f"{len(target)} fps")

            if self.reference:
                errors, matched = validate_block(self.reference, target)
                if errors:
                    self.target_list.SetItem(item_idx, 3, f"✕ Error: {errors[0]}")
                else:
                    self.target_list.SetItem(
                        item_idx, 3, f"✓ Válido ({matched} coincidentes)"
                    )
            else:
                self.target_list.SetItem(item_idx, 3, "Pendiente de referencia")

        self.summary_status.SetLabel(f"Destinos registrados: {len(self.targets)}.")

    def capture_reference(self, _event):
        selected = select_footprints(self.board)
        if not selected:
            wx.MessageBox(
                "Selecciona primero los footprints del bloque de referencia en PCB Editor.",
                "Block Aligner",
                wx.OK | wx.ICON_WARNING,
            )
            return
        self.reference = selected
        refs_str = format_references(selected, max_display=12)
        self.ref_status.SetLabel(
            f"✓ Referencia capturada: {len(selected)} footprints"
        )
        self.ref_details.SetLabel(f"Componentes: {refs_str}")
        self._update_targets_table()

    def add_target(self, _event):
        if not self.reference:
            wx.MessageBox(
                "Captura primero el bloque de referencia antes de añadir destinos.",
                "Block Aligner",
                wx.OK | wx.ICON_WARNING,
            )
            return
        selected = select_footprints(self.board)
        if not selected:
            wx.MessageBox(
                "Selecciona un bloque de footprints destino en PCB Editor.",
                "Block Aligner",
                wx.OK | wx.ICON_WARNING,
            )
            return
        self.targets.append(selected)
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
        for index, target in enumerate(self.targets, 1):
            validation_errors, matched = validate_block(self.reference, target)
            if validation_errors:
                errors.append(
                    "Destino {}: {}".format(index, "; ".join(validation_errors))
                )
            else:
                summary.append(
                    "Destino {}: {} footprints coincidentes".format(index, matched)
                )
                ok, result = plan_block(self.reference, target)
                if ok:
                    plans.append(result)
                else:
                    errors.append("Destino {}: {}".format(index, result))

        if errors:
            wx.MessageBox(
                "No se aplicaron cambios debido a errores de validación:\n\n{}".format(
                    "\n".join(errors)
                ),
                "Validación de Block Aligner",
                wx.OK | wx.ICON_ERROR,
            )
            return

        original_positions = []
        for plan in plans:
            for target_fp, x, y, source_fp in plan:
                original_positions.append(
                    (target_fp, position(target_fp), target_fp.GetOrientation())
                )
        for plan in plans:
            apply_plan(plan)
        pcbnew.Refresh()

        confirmation = wx.MessageDialog(
            self,
            "Vista previa activa. Los footprints se muestran temporalmente en "
            "sus nuevas posiciones.\n\n{}\n\n¿Deseas aplicar estos cambios definitivamente?".format(
                "\n".join(summary)
            ),
            "Vista previa de Block Aligner",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
        )
        proceed = confirmation.ShowModal() == wx.ID_YES
        confirmation.Destroy()
        if not proceed:
            for target_fp, (x, y), old_orientation in original_positions:
                set_position(target_fp, x, y)
                target_fp.SetOrientation(old_orientation)
            pcbnew.Refresh()
            self.summary_status.SetLabel(
                "Vista previa cancelada. Posiciones restauradas."
            )
            return
        self.summary_status.SetLabel("Alineación aplicada correctamente.")
        wx.MessageBox(
            "Alineación aplicada con éxito.",
            "Block Aligner",
            wx.OK | wx.ICON_INFORMATION,
        )

    def clear(self, _event):
        self.reference = []
        self.targets = []
        self.ref_status.SetLabel("Ningún bloque de referencia capturado.")
        self.ref_details.SetLabel(
            "Selecciona los footprints en PCB Editor y haz clic en 'Capturar referencia'."
        )
        self._update_targets_table()
        self.summary_status.SetLabel("Listo.")


class BlockAlignerPlugin(pcbnew.ActionPlugin):
    def __init__(self):
        super().__init__()
        self.dialog = None

    def defaults(self):
        self.name = "Block Aligner"
        self.category = "Layout Helper"
        self.description = "Alinea bloques repetidos copiando posiciones y orientaciones."
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(os.path.dirname(__file__), "icon.png")

    def Run(self):
        board = pcbnew.GetBoard()
        if self.dialog is not None and self.dialog.IsShown():
            self.dialog.Raise()
            return
        self.dialog = BlockAlignerDialog(None, board)
        self.dialog.Bind(wx.EVT_CLOSE, self._close_dialog)
        self.dialog.Show()

    def _close_dialog(self, event):
        if self.dialog is not None:
            self.dialog.Destroy()
            self.dialog = None
        event.Skip()
