# KiCad Schematic Footprint Manager

Herramienta gráfica nativa (wxPython) para la **asignación y edición masiva de huellas (*footprints*) en lote** para esquemáticos de KiCad (`.kicad_sch` y `.kicad_pro`).

Permite seleccionar múltiples componentes de forma visual, aplicar filtros inteligentes (por valor, huella, prefijo `R*`, `C*`, `U*`, etc.), buscar en todas las librerías oficiales y de usuario de KiCad, y actualizar los esquemáticos de forma segura con copia de respaldo automática (`.bak`).

---

## Características

- **Soporte Completo de Esquemáticos KiCad (v6, v7, v8, v9, v10)**:
  - Carga archivos individuales `.kicad_sch` o proyectos `.kicad_pro`.
  - Explora y actualiza automáticamente todas las **hojas jerárquicas / sub-sheets**.
  - Actualización limpia de `(property "Footprint" "...")` preservando coordenadas, UUIDs, instancias y formato S-expression.
- **Selección Múltiple y Filtros Inteligentes**:
  - Casillas de selección por fila con soporte para `Ctrl` / `Shift` / doble clic.
  - **Mismo Valor**: Selecciona con un solo clic todos los componentes que compartan el mismo valor (ej. todas las resistencias de `10k`).
  - **Misma Huella**: Selecciona todos los componentes que tengan la misma huella actual (ej. cambiar todos los `0603` a `0805`).
  - **Filtro por Prefijo**: `R` (Resistencias), `C` (Capacitores), `U/IC` (Integrados), `D` (Diodos/LEDs), `Q` (Transistores), `J` (Conectores), `SW/K` (Switches/Relés).
  - Búsqueda en tiempo real por cualquier texto.
- **Explorador y Buscador de Huellas Integrado**:
  - Indexa más de 15,000 huellas oficiales (`/usr/share/kicad/footprints/*.pretty`) y librerías de usuario.
  - Búsqueda rápida con autocompletado en milisegundos.
  - Desplegable de huellas ya utilizadas en el esquemático para reutilizarlas al instante.
- **Previsualización de Cambios y Seguridad**:
  - Resaltado visual en verde de los componentes modificados antes de escribir en disco.
  - Generación automática de copias de seguridad (`.bak`).
  - Botón de Deshacer / Revertir cambios antes de guardar.

---

## Requisitos

- Python 3.8+
- `wxPython` (incluido por defecto en sistemas con KiCad instalado)

---

## Uso

### Desde Terminal

```bash
# Lanzar la interfaz gráfica
python3 /home/emerson/Documentos/Schematic_Footprint_Manager/main.py

# O abriendo directamente un esquemático
python3 /home/emerson/Documentos/Schematic_Footprint_Manager/main.py /ruta/a/mi_proyecto.kicad_sch
```

### Flujo de Trabajo en la Interfaz

1. Haz clic en **Abrir Esquemático / Proyecto** y selecciona tu archivo `.kicad_sch` o `.kicad_pro`.
2. Filtra los componentes que deseas modificar o usa los botones rápidos (**Mismo Valor**, **Misma Huella**, **Marcar todos**).
3. En la sección inferior, escribe la nueva huella o pulsa **Explorar Librerías...** para buscarla.
4. Pulsa **⚡ Asignar a Seleccionados** (verás las filas modificadas resaltadas en verde con una flecha `➜`).
5. Pulsa **💾 Guardar Cambios en Esquemático**.
