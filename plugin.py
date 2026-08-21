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


class BlockAlignerDialog(wx.Dialog):
    def __init__(self, parent, board):
        super().__init__(
            parent,
            title="Block Aligner",
            size=(720, 520),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.SetMinSize((620, 440))
        self.board = board
        self.reference = []
        self.targets = []
        self.status = wx.StaticText(self, label="Listo para capturar el bloque de referencia.")
        self.reference_status = wx.StaticText(self, label="No capturada")
        self.target_list = wx.ListCtrl(
            self,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN,
        )
        self.target_list.InsertColumn(0, "Destino", width=110)
        self.target_list.InsertColumn(1, "Footprints", width=100)
        self.target_list.InsertColumn(2, "Estado", width=430)

        capture = wx.Button(self, label="Capturar referencia")
        add_target = wx.Button(self, label="Añadir destino")
        remove_target = wx.Button(self, label="Eliminar destino")
        align = wx.Button(self, label="Vista previa")
        clear = wx.Button(self, label="Limpiar")
        self._set_button_art(capture, wx.ART_FIND)
        self._set_button_art(add_target, wx.ART_NEW)
        self._set_button_art(remove_target, wx.ART_DELETE)
        self._set_button_art(align, wx.ART_FIND)
        self._set_button_art(clear, wx.ART_REDO)
        capture.SetToolTip("Captura los footprints seleccionados como referencia.")
        add_target.SetToolTip("Añade la selección actual como un bloque destino.")
        remove_target.SetToolTip("Elimina el destino seleccionado en la tabla.")
        align.SetToolTip("Muestra una vista previa y permite aplicar o cancelar.")
        clear.SetToolTip("Borra la referencia y todos los destinos de esta sesión.")
        capture.Bind(wx.EVT_BUTTON, self.capture_reference)
        add_target.Bind(wx.EVT_BUTTON, self.add_target)
        remove_target.Bind(wx.EVT_BUTTON, self.remove_target)
        align.Bind(wx.EVT_BUTTON, self.align_targets)
        clear.Bind(wx.EVT_BUTTON, self.clear)

        instructions = wx.StaticText(
            self,
            label=(
                "Selecciona footprints en la PCB y usa los controles de cada sección. "
                "Los destinos se validan antes de la vista previa."
            ),
        )
        reference_box = wx.StaticBoxSizer(wx.VERTICAL, self, "Bloque de referencia")
        reference_box.Add(
            wx.StaticText(self, label="Footprints capturados:"), 0, wx.LEFT | wx.TOP, 6
        )
        reference_box.Add(self.reference_status, 0, wx.ALL, 6)
        reference_box.Add(capture, 0, wx.ALL, 6)

        targets_box = wx.StaticBoxSizer(wx.VERTICAL, self, "Bloques destino")
        targets_box.Add(
            wx.StaticText(
                self,
                label="Selecciona un bloque en la PCB y pulsa 'Añadir destino'.",
            ),
            0,
            wx.ALL,
            6,
        )
        targets_box.Add(self.target_list, 1, wx.EXPAND | wx.ALL, 6)
        target_buttons = wx.BoxSizer(wx.HORIZONTAL)
        target_buttons.Add(add_target, 0, wx.RIGHT, 6)
        target_buttons.Add(remove_target, 0)
        targets_box.Add(target_buttons, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        actions_box = wx.StaticBoxSizer(wx.HORIZONTAL, self, "Acciones")
        actions_box.Add(align, 0, wx.ALL, 6)
        actions_box.Add(clear, 0, wx.ALL, 6)

        status_box = wx.StaticBoxSizer(wx.VERTICAL, self, "Estado")
        status_box.Add(self.status, 0, wx.ALL, 6)

        layout = wx.BoxSizer(wx.VERTICAL)
        layout.Add(instructions, 0, wx.EXPAND | wx.ALL, 10)
        layout.Add(reference_box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        layout.Add(targets_box, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        layout.Add(actions_box, 0, wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        layout.Add(status_box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.SetSizer(layout)

    @staticmethod
    def _set_button_art(button, art_id):
        try:
            bitmap = wx.ArtProvider.GetBitmap(art_id, wx.ART_BUTTON, (16, 16))
            if bitmap.IsOk():
                button.SetBitmap(bitmap)
        except Exception:
            pass

    def _update_target_row(self, index):
        target = self.targets[index]
        errors, matched = validate_block(self.reference, target)
        state = "Válido" if not errors else "; ".join(errors)
        colour = wx.Colour(190, 235, 190) if not errors else wx.Colour(255, 210, 180)
        self.target_list.SetItem(index, 1, str(len(target)))
        self.target_list.SetItem(index, 2, state)
        self.target_list.SetItemBackgroundColour(index, colour)

    def _refresh_target_rows(self):
        for index in range(len(self.targets)):
            self._update_target_row(index)

    def capture_reference(self, _event):
        selected = select_footprints(self.board)
        if not selected:
            wx.MessageBox("Selecciona el bloque de referencia primero.", "Block Aligner")
            return
        self.reference = selected
        self.reference_status.SetLabel("{} footprints capturados".format(len(selected)))
        self.status.SetLabel("Referencia capturada. Añade ahora los bloques destino.")
        self._refresh_target_rows()

    def add_target(self, _event):
        if not self.reference:
            wx.MessageBox("Captura primero el bloque de referencia.", "Block Aligner")
            return
        selected = select_footprints(self.board)
        if not selected:
            wx.MessageBox("Selecciona un bloque destino.", "Block Aligner")
            return
        self.targets.append(selected)
        row = self.target_list.InsertItem(self.target_list.GetItemCount(), "Destino {}".format(len(self.targets)))
        self.target_list.SetItem(row, 1, str(len(selected)))
        self._update_target_row(row)
        self.status.SetLabel(
            "{} destinos añadidos. Revisa los estados antes de la vista previa.".format(
                len(self.targets)
            )
        )

    def remove_target(self, _event):
        index = self.target_list.GetNextItem(
            -1,
            wx.LIST_NEXT_ALL,
            wx.LIST_STATE_SELECTED,
        )
        if index == wx.NOT_FOUND:
            wx.MessageBox("Selecciona un destino de la tabla para eliminarlo.", "Block Aligner")
            return
        self.target_list.Delete(index)
        del self.targets[index]
        for row in range(index, len(self.targets)):
            self.target_list.SetItem(row, 0, "Destino {}".format(row + 1))
            self._update_target_row(row)
        self.status.SetLabel("{} destinos añadidos.".format(len(self.targets)))

    def align_targets(self, _event):
        if not self.reference or not self.targets:
            wx.MessageBox("Captura una referencia y añade al menos un destino.", "Block Aligner")
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
                summary.append("Destino {}: {} footprints coincidentes".format(index, matched))
                ok, result = plan_block(self.reference, target)
                if ok:
                    plans.append(result)
                else:
                    errors.append("Destino {}: {}".format(index, result))

        if errors:
            self.status.SetLabel("Hay destinos inválidos. Corrige la tabla antes de continuar.")
            wx.MessageBox(
                "No se aplicaron cambios.\n\n{}".format("\n".join(errors)),
                "Validación de Block Aligner",
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
            "sus nuevas posiciones.\n\n{}\n\n¿Aplicar estos cambios?".format(
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
            self.status.SetLabel("Vista previa cancelada. No se aplicaron cambios.")
            return
        self.status.SetLabel("Vista previa aplicada correctamente.")
        wx.MessageBox("Vista previa aplicada correctamente.", "Block Aligner")

    def clear(self, _event):
        self.reference = []
        self.targets = []
        self.target_list.DeleteAllItems()
        self.reference_status.SetLabel("No capturada")
        self.status.SetLabel("Sesión limpiada. Listo para capturar una referencia.")


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
