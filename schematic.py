"""Best-effort PCB/schematic synchronization checks using ``kicad-cli``.

The legacy pcbnew SWIG API cannot inspect an open schematic.  KiCad's CLI can
export the saved root schematic as a netlist, which gives us a deterministic
reference-to-pin-to-net map without modifying the project.
"""

import os
import re
import shutil
import subprocess
import tempfile


_FIELD_RE = re.compile(r'^\s*\((name|ref|pin)\s+"((?:\\.|[^"\\])*)"\)')


def parse_netlist_pin_nets(text):
    """Return ``{(reference, pin): net_name}`` from a KiCad s-expression netlist."""
    marker = "\n\t(nets\n"
    start = text.rfind(marker)
    if start < 0:
        return {}

    result = {}
    net_name = None
    node_ref = None
    for line in text[start + len(marker):].splitlines():
        stripped = line.lstrip()
        if stripped.startswith("(net"):
            net_name = None
            node_ref = None
            continue
        match = _FIELD_RE.match(line)
        if not match:
            continue
        field, value = match.groups()
        value = value.replace(r'\"', '"').replace(r'\\', '\\')
        if field == "name" and net_name is None:
            net_name = value
        elif field == "ref":
            node_ref = value
        elif field == "pin" and node_ref is not None and net_name is not None:
            result[(node_ref, value)] = net_name
            node_ref = None
    return result


def root_schematic_path(board):
    """Infer the root ``.kicad_sch`` path from the board filename."""
    try:
        board_path = str(board.GetFileName())
    except Exception:
        return None
    if not board_path:
        return None
    stem, _extension = os.path.splitext(board_path)
    candidate = stem + ".kicad_sch"
    return candidate if os.path.isfile(candidate) else None


def export_pin_nets(board, timeout=20):
    """Export the saved schematic netlist and return status plus its pin map."""
    schematic_path = root_schematic_path(board)
    if schematic_path is None:
        return {
            "available": False,
            "reason": "No se encontró el esquemático raíz junto al PCB.",
            "pin_nets": {},
        }
    executable = shutil.which("kicad-cli")
    if executable is None:
        return {
            "available": False,
            "reason": "kicad-cli no está disponible en el PATH.",
            "pin_nets": {},
        }

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".net", delete=False) as handle:
            temp_path = handle.name
        completed = subprocess.run(
            [
                executable,
                "sch",
                "export",
                "netlist",
                "-o",
                temp_path,
                schematic_path,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "Error desconocido").strip()
            return {"available": False, "reason": detail, "pin_nets": {}}
        with open(temp_path, "r", encoding="utf-8") as handle:
            pin_nets = parse_netlist_pin_nets(handle.read())
        if not pin_nets:
            return {
                "available": False,
                "reason": "La netlist exportada no contiene conexiones de pads.",
                "pin_nets": {},
            }
        return {
            "available": True,
            "reason": "",
            "pin_nets": pin_nets,
            "schematic_path": schematic_path,
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "reason": str(exc), "pin_nets": {}}
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def compare_footprint_nets(footprints, schematic_pin_nets):
    """Return pad-net differences for the supplied PCB footprints."""
    mismatches = []
    for footprint in footprints:
        reference = str(footprint.GetReference())
        for pad in footprint.Pads():
            pin = str(pad.GetNumber())
            expected = schematic_pin_nets.get((reference, pin))
            if expected is None:
                continue
            try:
                actual = str(pad.GetNetname())
            except Exception:
                actual = ""
            if actual != expected:
                mismatches.append(
                    {
                        "reference": reference,
                        "pin": pin,
                        "pcb_net": actual,
                        "schematic_net": expected,
                    }
                )
    return mismatches
