"""Lógica de análisis e incremento de etiquetas para KiCad.

Maneja etiquetas jerárquicas, globales y locales.
Gestiona casos borde:
- Etiquetas con sufijo numérico (OUT_1 -> OUT_2).
- Ceros a la izquierda (OUT_01 -> OUT_02).
- Múltiples números en el nombre (CH1_DATA_1 -> CH1_DATA_2).
- Etiquetas sin número (NC -> NC_2, COM -> COM_2).
- Lista configurable de excepciones de alimentación (+5V, GND, etc.).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple


DEFAULT_EXCEPTIONS: Set[str] = {
    "+5V", "+3V3", "+3.3V", "+1.8V", "+12V", "+24V", "-12V", "-5V",
    "VCC", "VDD", "VSS", "VEE", "VBAT",
    "GND", "GNDA", "GNDD", "AGND", "DGND", "PGND", "EARTH", "0V"
}


@dataclass
class RenamingRule:
    """Configuración para el renombrado de etiquetas."""

    exceptions: Set[str] = field(default_factory=lambda: set(DEFAULT_EXCEPTIONS))
    case_sensitive_exceptions: bool = False

    def is_exception(self, name: str) -> bool:
        """Determina si una etiqueta está en la lista de excepciones (ej. power/gnd)."""
        clean_name = name.strip()
        # Verificar símbolos virtuales o flags de KiCad (#PWR, etc.)
        if clean_name.startswith("#"):
            return True

        if self.case_sensitive_exceptions:
            return clean_name in self.exceptions

        clean_lower = clean_name.lower()
        return any(ex.lower() == clean_lower for ex in self.exceptions)


class LabelRenamer:
    """Calcula los nuevos nombres de etiquetas para copias sucesivas."""

    # Regex para extraer prefijo, separador y número al final de una etiqueta
    # Grupo 1: prefijo
    # Grupo 2: separador (_ o vacio)
    # Grupo 3: dígitos numéricos
    REGEX_TRAILING_NUMBER = re.compile(r"^(.*?)(_?)(\d+)$")

    def __init__(self, rule: Optional[RenamingRule] = None):
        self.rule = rule or RenamingRule()

    def rename_label(self, original_name: str, copy_index: int) -> str:
        """Calcula el nombre de la etiqueta para una copia específica.

        copy_index: 1 para el original, 2 para la primera copia duplicada, etc.
        """
        if copy_index <= 1:
            return original_name

        # Si es una excepción (ej. +5V, GND), se mantiene idéntica
        if self.rule.is_exception(original_name):
            return original_name

        match = self.REGEX_TRAILING_NUMBER.match(original_name)
        if match:
            prefix, sep, num_str = match.groups()
            original_num = int(num_str)
            new_num = original_num + (copy_index - 1)

            # Conservar ceros a la izquierda si el original los tenía (ej. 01 -> 02)
            padded_num_str = f"{new_num:0{len(num_str)}d}"

            # Si no tenía separador pero tenía prefijo, ej OUT1 -> OUT2
            # O con separador OUT_1 -> OUT_2
            return f"{prefix}{sep}{padded_num_str}"

        # Caso sin número (ej. NC, COM, NA):
        # La copia 2 recibe _2, la 3 _3, etc.
        return f"{original_name}_{copy_index}"

    def preview_renaming(
        self, labels: List[str], num_copies: int
    ) -> List[Tuple[str, List[str]]]:
        """Genera una vista previa del renombrado para N copias.

        Retorna lista de (nombre_original, [nombre_copia_1, nombre_copia_2, ...])
        """
        results = []
        for lbl in labels:
            copies = [self.rename_label(lbl, idx + 1) for idx in range(num_copies)]
            results.append((lbl, copies))
        return results
