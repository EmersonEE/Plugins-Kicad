#!/usr/bin/env bash
# Script para instalar enlaces simbólicos de los plugins y apps de KiCad
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KICAD_PLUGINS_DIR="${HOME}/.local/share/kicad/10.0/3rdparty/plugins"
APPS_DIR="${HOME}/.local/share/applications"

echo "=== Instalación de Plugins KiCad 10 mediante Enlaces Simbólicos ==="
echo "Repositorio origen: $REPO_DIR"
echo "Destino plugins:    $KICAD_PLUGINS_DIR"
echo ""

# 1. Crear directorios de destino
mkdir -p "$KICAD_PLUGINS_DIR"
mkdir -p "$APPS_DIR"

# 2. Plugins de acción del PCB Editor
ACTION_PLUGINS=(
    "Block_Aligner"
    "KiCad_3D_Model_Propagator"
    "kicad-routing-progress-plugin"
)

echo "--- Enlazando Action Plugins de PCB ---"
for plugin in "${ACTION_PLUGINS[@]}"; do
    if [ -d "$REPO_DIR/$plugin" ]; then
        ln -sfn "$REPO_DIR/$plugin" "$KICAD_PLUGINS_DIR/$plugin"
        echo "[OK] Enlazado: $plugin -> $KICAD_PLUGINS_DIR/$plugin"
    else
        echo "[AVISO] No se encontró el directorio: $REPO_DIR/$plugin"
    fi
done

echo ""
echo "--- Enlazando Accesos de Aplicaciones (.desktop) ---"
DESKTOP_ENTRIES=(
    "KiCad_BOM_LaElectronica/KiCad_BOM_LaElectronica.desktop"
    "kiCad_Duplicar_Incrementar_Labels/KiCad_Block_Duplicator.desktop"
    "Schematic_Footprint_Manager/Schematic_Footprint_Manager.desktop"
)

for entry in "${DESKTOP_ENTRIES[@]}"; do
    file_path="$REPO_DIR/$entry"
    base_name="$(basename "$entry")"
    if [ -f "$file_path" ]; then
        ln -sfn "$file_path" "$APPS_DIR/$base_name"
        echo "[OK] Enlazado: $base_name -> $APPS_DIR/$base_name"
    else
        echo "[AVISO] No se encontró el archivo: $file_path"
    fi
done

echo ""
echo "=== ¡Instalación completada exitosamente! ==="
echo "Para ver los plugins en KiCad PCB Editor:"
echo "  1. Abre KiCad PCB Editor."
echo "  2. Ve a: Herramientas -> Plugins externos -> Refrescar plugins (o Actualizar plugins)."
