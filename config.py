"""Block Aligner configuration.

Defaults are embedded here and can be overridden by a JSON file. Candidate
locations (most specific first):

* ``<plugin_dir>/config.json``
* ``~/.config/Block_Aligner/config.json``

Only keys present in :data:`DEFAULT_CONFIG` are accepted, so unknown keys in a
user file are silently ignored rather than breaking the plugin.
"""

import copy
import json
import os

DEFAULT_CONFIG = {
    # Margen (nm) alrededor del bloque de referencia para recolectar pistas.
    "track_collect_margin_nm": 2_000_000,
    # Margen (nm) para aceptar un footprint como parte de la misma área de bloque.
    "block_area_margin_nm": 3_000_000,
    # Heurística de "red global": nº de pads extra sobre la referencia.
    "global_net_threshold_extra": 2,
    # Heurística de "red global": nº mínimo de pads para considerarla global.
    "global_net_min_pads": 4,
    # Nombres de redes de alimentación reconocidos como globales.
    "power_net_names": [
        "GND", "VCC", "VDD", "VSS", "+3V3", "+5V", "+12V", "-12V",
        "3V3", "5V", "GNDA", "AGND", "DGND", "POWER", "PWR", "ADC1", "ADC2",
    ],
    # Valores por defecto de los checkboxes de la UI.
    "replicate_tracks_default": False,
    "create_groups_default": True,
    # Directorio donde se escribe el informe de diagnóstico.
    "log_dir": "~/Block_Aligner",
    # Margen (nm) usado al detectar solapamiento entre bloques destino.
    "overlap_margin_nm": 1_000_000,
}


def default_config():
    """Return a deep copy of the built-in defaults."""
    return copy.deepcopy(DEFAULT_CONFIG)


def config_paths():
    """Return candidate config file paths, most specific first."""
    return [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"),
        os.path.expanduser("~/.config/Block_Aligner/config.json"),
    ]


def load_config():
    """Load defaults merged with the first readable JSON config file."""
    config = default_config()
    for path in config_paths():
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    for key, value in data.items():
                        if key in config:
                            config[key] = value
            except (OSError, ValueError):
                continue
    return config


def save_config(config, path=None):
    """Write the config dict as JSON. Returns True on success."""
    path = path or config_paths()[-1]
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=2, ensure_ascii=False)
        return True
    except OSError:
        return False
