# Block Aligner

KiCad PCB Editor action plugin that copies the relative footprint positions and
orientations from one selected block to one or more selected destination blocks.

The current version moves footprints only. It does not modify tracks, zones, nets,
or schematic files.

## Usage

1. Select all footprints in the reference block.
2. Run **Block Aligner** from the PCB Editor action-plugin menu.
3. Click **Capturar referencia**.
4. Select one destination block and click **Añadir destino seleccionado**.
5. Repeat for each destination block.
6. Click **Alinear destinos**.

Components are matched by value, library footprint, pad count, and local order
inside the block. Future work will add connectivity-based matching for repeated
components with identical properties.

## Installation

Copy this directory to:

```text
~/.local/share/kicad/10.0/3rdparty/plugins/
```

Restart KiCad after installation.
