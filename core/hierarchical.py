"""Sincronización automática de pines en hojas jerárquicas padre para KiCad.

Cuando se duplican etiquetas jerárquicas en una subhoja (ej. OUT_1 -> OUT_2..OUT_N),
este módulo localiza el bloque (sheet ...) en el esquemático padre y añade
los pines correspondientes alineados a la grilla, ampliando la hoja si es necesario.
"""

from __future__ import annotations

import os
import uuid
from typing import List, Optional, Tuple

from core.sexpr import SAtom, SExprParser, SExprSerializer, SNode


class HierarchicalManager:
    """Gestiona la sincronización entre subhojas y sus hojas padre."""

    PIN_SPACING_MM = 2.54  # Separación vertical estándar entre pines en el bloque sheet (100 mil)

    @classmethod
    def find_parent_sheet_file(cls, child_sch_path: str) -> Optional[str]:
        """Busca el archivo de esquemático padre que contiene una referencia a child_sch_path."""
        abs_child = os.path.abspath(child_sch_path)
        parent_dir = os.path.dirname(abs_child)
        child_filename = os.path.basename(abs_child)

        # Buscar en el mismo directorio archivos .kicad_sch
        try:
            for fname in os.listdir(parent_dir):
                if fname.endswith(".kicad_sch") and fname != child_filename:
                    candidate_path = os.path.join(parent_dir, fname)
                    with open(candidate_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    if child_filename in content:
                        return candidate_path
        except Exception:
            pass

        return None

    @classmethod
    def sync_parent_sheet_pins(
        cls,
        parent_sch_path: str,
        child_sch_path: str,
        new_hierarchical_labels: List[Tuple[str, str]],  # [(base_label, new_label), ...]
    ) -> List[str]:
        """Añade los pines nuevos al bloque (sheet ...) en el archivo padre.

        Retorna la lista de pines añadidos exitosamente.
        """
        if not os.path.isfile(parent_sch_path):
            return []

        child_filename = os.path.basename(child_sch_path)

        with open(parent_sch_path, "r", encoding="utf-8") as f:
            content = f.read()

        root = SExprParser.parse(content)
        if not root:
            return []

        # Buscar el nodo (sheet ...) que apunta a child_filename
        target_sheet: Optional[SNode] = None
        for item in root.items:
            if isinstance(item, SNode) and item.tag == "sheet":
                sheetfile = item.get_prop("Sheetfile")
                if sheetfile and (sheetfile == child_filename or os.path.basename(sheetfile) == child_filename):
                    target_sheet = item
                    break

        if not target_sheet:
            return []

        # Obtener pines existentes
        existing_pins: List[SNode] = target_sheet.get_children("pin")
        existing_names = {str(p.get_atom(0, "")) for p in existing_pins}

        # Obtener dimensiones del bloque (sheet (at X Y) (size W H) ...)
        sheet_at = target_sheet.get_child("at")
        sheet_size = target_sheet.get_child("size")
        sheet_x = float(str(sheet_at.get_atom(0, 0))) if sheet_at else 0.0
        sheet_y = float(str(sheet_at.get_atom(1, 0))) if sheet_at else 0.0
        sheet_w = float(str(sheet_size.get_atom(0, 50.8))) if sheet_size else 50.8
        sheet_h = float(str(sheet_size.get_atom(1, 50.8))) if sheet_size else 50.8

        added_pins: List[str] = []

        # Para cada etiqueta nueva, clonar el formato del pin base
        for base_label, new_label in new_hierarchical_labels:
            if new_label in existing_names:
                continue

            # Buscar pin base en el sheet
            base_pin = None
            for p in existing_pins:
                if str(p.get_atom(0, "")) == base_label:
                    base_pin = p
                    break

            if not base_pin:
                # Si no hay pin base, usar el último pin como plantilla
                base_pin = existing_pins[-1] if existing_pins else None

            if not base_pin:
                continue

            # Clonar el pin base
            new_pin = base_pin.clone()
            new_pin.items[0] = SAtom(new_label, is_quoted=True)
            new_pin.set_uuid(str(uuid.uuid4()))

            # Calcular nueva posición vertical (Y)
            base_pos = base_pin.get_position()
            if base_pos:
                pin_x, pin_y, pin_r = base_pos
                # Determinar el desplazamiento respecto a los pines existentes
                current_count = len(existing_pins) + len(added_pins)
                new_pin_y = pin_y + (len(added_pins) + 1) * cls.PIN_SPACING_MM
                new_pin.set_position(pin_x, new_pin_y, pin_r)

                # Si el nuevo pin sobrepasa la altura del sheet, agrandar el sheet
                needed_h = (new_pin_y - sheet_y) + cls.PIN_SPACING_MM * 2
                if needed_h > sheet_h and sheet_size:
                    new_h = round(needed_h + cls.PIN_SPACING_MM, 2)
                    sheet_size.items[1] = SAtom(new_h)
                    sheet_h = new_h

            target_sheet.add_child(new_pin)
            existing_names.add(new_label)
            added_pins.append(new_label)

        if added_pins:
            # Guardar el archivo padre actualizado
            new_content = SExprSerializer.serialize(root)
            with open(parent_sch_path, "w", encoding="utf-8") as f:
                f.write(new_content)

        return added_pins
