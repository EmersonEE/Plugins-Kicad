# Block Aligner

KiCad PCB Editor action plugin that copies the relative footprint positions and
orientations from one selected block to one or more selected destination blocks.

The current version moves footprints only. It does not modify tracks, zones, nets,
or schematic files.

Before moving anything, the plugin validates every destination and asks for
confirmation. Invalid destinations are rejected without changing the board.

## Usage

1. Select all footprints in the reference block.
2. Run **Block Aligner** from the PCB Editor action-plugin menu.
3. Click **Capturar referencia**.
4. Select one destination block and click **Añadir destino**.
5. Repeat for each destination block.
6. To remove an incorrect destination, select it in the list and click
   **Eliminar destino**.
7. Click **Alinear destinos**.

Components are matched by value, library footprint, pad count, and their
connectivity to other components inside the block. Net names and net codes are
ignored, so equivalent blocks can use different nets. If two components still
have exactly the same circuit role, their local position is used as a fallback.

## Installation

Copy this directory to:

```text
~/.local/share/kicad/10.0/3rdparty/plugins/
```

Restart KiCad after installation.
