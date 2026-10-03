#!/usr/bin/env python3
"""KiCad Block Duplicator & Label Incrementor.

Herramienta de productividad para KiCad 10 en Arch Linux / Hyprland.
Permite duplicar bloques esquemáticos incrementando automáticamente sus etiquetas.

Autor: Emerson / Asistente DeepMind
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

# Agregar directorio raíz al PYTHONPATH
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def run_cli_clipboard(n: int, direction: str, pitch: float, question_mark: bool) -> int:
    """Procesa el portapapeles en modo directo sin GUI."""
    from core.block_detector import BlockDetector
    from core.block_duplicator import BlockDuplicator, DuplicationConfig
    from core.reference_annotator import ReferenceAnnotationMode
    from core.sexpr import SExprParser, SExprSerializer

    raw_text = BlockDetector.read_system_clipboard()
    if not raw_text or not raw_text.strip().startswith("("):
        print("Error: El portapapeles no contiene datos S-expression de KiCad.", file=sys.stderr)
        return 1

    block = BlockDetector.from_clipboard_text(raw_text)
    if not block:
        print("Error: No se pudieron extraer elementos del portapapeles.", file=sys.stderr)
        return 1

    ann_mode = (
        ReferenceAnnotationMode.RESET_TO_QUESTION_MARK
        if question_mark
        else ReferenceAnnotationMode.AUTO_SEQUENTIAL
    )

    cfg = DuplicationConfig(
        num_copies=n,
        direction=direction,
        pitch_y_mm=pitch if direction != "horizontal" else 0.0,
        pitch_x_mm=pitch if direction != "vertical" else 0.0,
        annotation_mode=ann_mode
    )

    duplicator = BlockDuplicator(cfg)
    report = duplicator.duplicate_block(block)

    nodes_orig = SExprParser.parse_many(raw_text)
    if len(nodes_orig) == 1 and nodes_orig[0].tag == "kicad_sch":
        root = nodes_orig[0].clone()
        for item in report.new_items:
            root.add_child(item)
        output_sexpr = SExprSerializer.serialize(root)
    else:
        all_elements = list(block.items) + report.new_items
        output_sexpr = SExprSerializer.serialize(all_elements)

    p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE, text=True)
    p.communicate(input=output_sexpr)
    if p.returncode == 0:
        print(f"✓ Bloque duplicado exitosamente x{n} en el portapapeles ({report.symbols_created} símbolos, {len(report.labels_renamed)} etiquetas).")
        return 0
    else:
        print("Error al escribir en wl-copy.", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="KiCad Block Duplicator & Label Incrementor"
    )
    parser.add_argument("file", nargs="?", help="Ruta al archivo .kicad_sch a abrir")
    parser.add_argument("-c", "--clipboard", action="store_true", help="Modo CLI directo sobre portapapeles (wl-paste -> wl-copy)")
    parser.add_argument("-n", "--copies", type=int, default=4, help="Número total de copias (por defecto 4)")
    parser.add_argument("-d", "--direction", choices=["vertical", "horizontal", "matrix"], default="vertical", help="Dirección del clonado")
    parser.add_argument("-p", "--pitch", type=float, default=50.8, help="Separación en mm (por defecto 50.8 mm / 2000 mil)")
    parser.add_argument("--sequential", action="store_true", help="Usar referencias secuenciales (R7, R8) en vez de '?'")

    args = parser.parse_args()

    # Si se pide procesar por CLI directo de portapapeles
    if args.clipboard:
        return run_cli_clipboard(
            n=args.copies,
            direction=args.direction,
            pitch=args.pitch,
            question_mark=not args.sequential
        )

    # Modo GUI con wxPython
    try:
        import wx
        from ui.main_window import MainWindow

        app = wx.App()
        frame = MainWindow(initial_path=args.file)

        icon_path = os.path.join(ROOT_DIR, "icon.png")
        if os.path.isfile(icon_path):
            try:
                icon = wx.Icon(icon_path, wx.BITMAP_TYPE_PNG)
                frame.SetIcon(icon)
            except Exception:
                pass

        frame.Show()
        app.MainLoop()
        return 0
    except ImportError as e:
        print(f"Error: Se requiere wxPython para la interfaz gráfica: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
