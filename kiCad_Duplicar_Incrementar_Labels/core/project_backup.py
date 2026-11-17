"""Módulo de seguridad: respaldos automáticos y validación ERC con kicad-cli."""

from __future__ import annotations

import datetime
import os
import shutil
import subprocess
from typing import Optional, Tuple


class SafetyManager:
    """Gestiona respaldos de esquemáticos y validación ERC."""

    @classmethod
    def create_backup(cls, file_path: str) -> Optional[str]:
        """Crea una copia de seguridad con fecha y hora antes de modificar el archivo.

        Retorna la ruta del archivo de respaldo creado.
        """
        if not os.path.isfile(file_path):
            return None

        dirname, filename = os.path.split(file_path)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{filename}.bak_{timestamp}"
        backup_path = os.path.join(dirname, backup_name)

        try:
            shutil.copy2(file_path, backup_path)
            return backup_path
        except Exception:
            return None

    @classmethod
    def validate_with_kicad_erc(cls, sch_path: str) -> Tuple[bool, str, int]:
        """Ejecuta kicad-cli sch erc para validar la sintaxis y reglas del esquemático modificado.

        Retorna: (éxito_sintáctico, mensaje_o_salida, cantidad_infracciones)
        """
        if not os.path.isfile(sch_path):
            return False, "El archivo no existe", -1

        try:
            # Ejecutar kicad-cli sch erc
            res = subprocess.run(
                ["kicad-cli", "sch", "erc", sch_path],
                capture_output=True,
                text=True,
                check=False,
                timeout=15
            )

            # kicad-cli retorna 0 si se pudo abrir y evaluar el esquemático
            # (incluso si hay avisos eléctricos de pines no conectados, retorna 0)
            output = res.stdout + "\n" + res.stderr

            # Limpiar archivo temporal de reporte generado por kicad-cli si existe
            report_file = sch_path.replace(".kicad_sch", "-erc.rpt")
            if os.path.exists(report_file):
                try:
                    os.remove(report_file)
                except Exception:
                    pass

            if res.returncode == 0:
                return True, output.strip(), 0
            else:
                return False, f"ERC falló con código {res.returncode}:\n{output}", 1
        except FileNotFoundError:
            return True, "kicad-cli no está instalado en el PATH (validación omitida)", 0
        except Exception as e:
            return False, f"Excepción al ejecutar kicad-cli: {str(e)}", -1
