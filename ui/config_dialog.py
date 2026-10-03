"""Diálogo de configuración para excepciones de etiquetas y parámetros de grilla."""

from __future__ import annotations

import json
import os
import wx
from typing import Set

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "default_config.json"
)


class ConfigDialog(wx.Dialog):
    """Diálogo modal para editar excepciones de alimentación y preferencias."""

    def __init__(self, parent: wx.Window):
        super().__init__(
            parent,
            title="Configuración de Duplicación y Excepciones",
            size=(520, 520),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.config_data = self._load_config()
        self._init_ui()
        self.CentreOnParent()

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
        sizer = wx.BoxSizer(wx.VERTICAL)

        # 1. Lista de excepciones de red
        box_exc = wx.StaticBox(panel, label=" Excepciones de Alimentación y Tierra (No renombrar) ")
        sizer_exc = wx.StaticBoxSizer(box_exc, wx.VERTICAL)

        lbl_info = wx.StaticText(
            panel,
            label="Estas etiquetas no se renombrarán al clonar para que permanezcan\n"
                  "conectadas entre todas las copias (ej. +5V, GND, VCC)."
        )
        sizer_exc.Add(lbl_info, 0, wx.ALL, 6)

        self.txt_exceptions = wx.TextCtrl(
            panel,
            value="\n".join(self.config_data.get("exceptions", [])),
            style=wx.TE_MULTILINE | wx.BORDER_SUNKEN,
            size=(-1, 160)
        )
        sizer_exc.Add(self.txt_exceptions, 1, wx.EXPAND | wx.ALL, 6)
        sizer.Add(sizer_exc, 1, wx.EXPAND | wx.ALL, 10)

        # 2. Opciones de Cuadrícula y Hojas
        box_grid = wx.StaticBox(panel, label=" Opciones Avanzadas ")
        sizer_grid = wx.StaticBoxSizer(box_grid, wx.VERTICAL)

        self.chk_auto_sync = wx.CheckBox(
            panel, label="Sincronizar automáticamente pines en la hoja jerárquica padre"
        )
        self.chk_auto_sync.SetValue(self.config_data.get("auto_sync_parent_sheet", True))
        sizer_grid.Add(self.chk_auto_sync, 0, wx.ALL, 6)

        grid_row = wx.BoxSizer(wx.HORIZONTAL)
        lbl_grid = wx.StaticText(panel, label="Alineación de Grilla KiCad (mm):")
        self.spin_grid = wx.SpinCtrlDouble(
            panel, value=str(self.config_data.get("grid_snap_mm", 1.27)),
            min=0.635, max=5.08, inc=0.635
        )
        grid_row.Add(lbl_grid, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        grid_row.Add(self.spin_grid, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_grid.Add(grid_row, 0, wx.ALL, 6)

        sizer.Add(sizer_grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # 3. Botones Guardar / Cancelar
        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(panel, wx.ID_OK, label="💾 Guardar")
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, label="Cancelar")
        btn_ok.Bind(wx.EVT_BUTTON, self._on_save)

        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        panel.SetSizer(sizer)

    def _on_save(self, event):
        raw_text = self.txt_exceptions.GetValue()
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        self.config_data["exceptions"] = lines
        self.config_data["auto_sync_parent_sheet"] = self.chk_auto_sync.GetValue()
        self.config_data["grid_snap_mm"] = self.spin_grid.GetValue()

        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            wx.MessageBox(f"Error al guardar configuración: {str(e)}", "Error", wx.ICON_ERROR)
            return

        self.EndModal(wx.ID_OK)

    def get_exceptions_set(self) -> Set[str]:
        return set(self.config_data.get("exceptions", []))
