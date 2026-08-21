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


def centroid(footprints):
    xs = [position(fp)[0] for fp in footprints]
    ys = [position(fp)[1] for fp in footprints]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def ordered_components(footprints, center):
    """Group equivalent parts and order duplicates by their local position."""
    groups = {}
    for footprint in footprints:
        groups.setdefault(footprint_key(footprint), []).append(footprint)

    result = {}
    for key, group in groups.items():
        result[key] = sorted(
            group,
            key=lambda fp: (
                position(fp)[1] - center[1],
                position(fp)[0] - center[0],
                fp.GetReference(),
            ),
        )
    return result


def align_block(reference, target):
    ref_center = centroid(reference)
    target_center = centroid(target)
    ref_groups = ordered_components(reference, ref_center)
    target_groups = ordered_components(target, target_center)

    if set(ref_groups) != set(target_groups):
        return False, "Los componentes o footprints no coinciden."

    for key, ref_parts in ref_groups.items():
        target_parts = target_groups[key]
        if len(ref_parts) != len(target_parts):
            return False, "La cantidad de componentes equivalentes no coincide."

    moved = []
    for key, ref_parts in ref_groups.items():
        for ref_fp, target_fp in zip(ref_parts, target_groups[key]):
            ref_x, ref_y = position(ref_fp)
            new_x = target_center[0] + (ref_x - ref_center[0])
            new_y = target_center[1] + (ref_y - ref_center[1])
            if target_fp.IsLocked():
                return False, "El footprint {} está bloqueado.".format(
                    target_fp.GetReference()
                )
            set_position(target_fp, new_x, new_y)
            set_orientation(target_fp, ref_fp)
            moved.append(target_fp.GetReference())

    return True, "Alineados {} footprints.".format(len(moved))


class BlockAlignerDialog(wx.Dialog):
    def __init__(self, parent, board):
        super().__init__(parent, title="Block Aligner", size=(510, 390))
        self.board = board
        self.reference = []
        self.targets = []
        self.status = wx.StaticText(self, label="Selecciona footprints en la PCB.")
        self.target_list = wx.ListBox(self, style=wx.LB_SINGLE)

        capture = wx.Button(self, label="Capturar referencia")
        add_target = wx.Button(self, label="Añadir destino seleccionado")
        align = wx.Button(self, label="Alinear destinos")
        clear = wx.Button(self, label="Limpiar")
        capture.Bind(wx.EVT_BUTTON, self.capture_reference)
        add_target.Bind(wx.EVT_BUTTON, self.add_target)
        align.Bind(wx.EVT_BUTTON, self.align_targets)
        clear.Bind(wx.EVT_BUTTON, self.clear)

        instructions = wx.StaticText(
            self,
            label=(
                "1. Selecciona todos los footprints del bloque de referencia.\n"
                "2. Pulsa 'Capturar referencia'.\n"
                "3. Selecciona cada bloque destino y añádelo.\n"
                "4. Pulsa 'Alinear destinos'."
            ),
        )
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.Add(capture, 0, wx.ALL, 4)
        buttons.Add(add_target, 0, wx.ALL, 4)
        buttons.Add(align, 0, wx.ALL, 4)
        buttons.Add(clear, 0, wx.ALL, 4)

        layout = wx.BoxSizer(wx.VERTICAL)
        layout.Add(instructions, 0, wx.ALL, 10)
        layout.Add(self.status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        layout.Add(self.target_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        layout.Add(buttons, 0, wx.ALIGN_CENTER | wx.ALL, 8)
        self.SetSizer(layout)

    def capture_reference(self, _event):
        selected = select_footprints(self.board)
        if not selected:
            wx.MessageBox("Selecciona el bloque de referencia primero.", "Block Aligner")
            return
        self.reference = selected
        self.status.SetLabel(
            "Referencia capturada: {} footprints.".format(len(selected))
        )

    def add_target(self, _event):
        if not self.reference:
            wx.MessageBox("Captura primero el bloque de referencia.", "Block Aligner")
            return
        selected = select_footprints(self.board)
        if not selected:
            wx.MessageBox("Selecciona un bloque destino.", "Block Aligner")
            return
        self.targets.append(selected)
        self.target_list.Append(
            "Destino {}: {} footprints".format(len(self.targets), len(selected))
        )
        self.status.SetLabel("Destinos añadidos: {}.".format(len(self.targets)))

    def align_targets(self, _event):
        if not self.reference or not self.targets:
            wx.MessageBox("Captura una referencia y añade al menos un destino.", "Block Aligner")
            return
        errors = []
        aligned = 0
        for index, target in enumerate(self.targets, 1):
            ok, message = align_block(self.reference, target)
            if ok:
                aligned += 1
            else:
                errors.append("Destino {}: {}".format(index, message))
        pcbnew.Refresh()
        if errors:
            wx.MessageBox("{} alineados.\n\n{}".format(aligned, "\n".join(errors)), "Block Aligner")
        else:
            wx.MessageBox("{} bloques alineados correctamente.".format(aligned), "Block Aligner")

    def clear(self, _event):
        self.reference = []
        self.targets = []
        self.target_list.Clear()
        self.status.SetLabel("Selecciona footprints en la PCB.")


class BlockAlignerPlugin(pcbnew.ActionPlugin):
    def __init__(self):
        super().__init__()
        self.dialog = None

    def defaults(self):
        self.name = "Block Aligner"
        self.category = "Layout Helper"
        self.description = "Alinea bloques repetidos copiando posiciones y orientaciones."
        self.show_toolbar_button = False
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
