# KiCad Block Duplicator & Label Incrementor

Herramienta de productividad de alta precisión diseñada para **KiCad 10** en **Arch Linux / Hyprland (Omarchy 4)**. Permite duplicar bloques esquemáticos $N$ veces incrementando automáticamente sus etiquetas numéricas y alfanuméricas, preservando redes de alimentación (+5V, GND), generando UUIDs únicos v4 y alineando todo estrictamente a la grilla estándar de 1.27 mm (50 mil).

---

## 🏗️ Arquitectura del Proyecto

Siguiendo el diseño modular probado en tus herramientas previas ([Schematic_Footprint_Manager](file:///home/emerson/Documentos/Schematic_Footprint_Manager) y [KiCad_BOM_LaElectronica](file:///home/emerson/Documentos/KiCad_BOM_LaElectronica)), el proyecto desacopla completamente el motor lógico de la capa visual:

```
kiCad_Duplicar_Incrementar_Labels/
├── core/
│   ├── __init__.py
│   ├── sexpr.py                # Parser y serializador fiel de S-expressions para KiCad 10
│   ├── block_detector.py       # Extracción de bloques por portapapeles, referencias o bounding box
│   ├── label_renamer.py        # Detección de patrones regex, padding de ceros y filtros de alimentación
│   ├── reference_annotator.py  # Anotación de componentes (Opción B: '?' o secuencial)
│   ├── block_duplicator.py     # Motor de clonación, UUIDs únicos v4, cálculo de offsets y grilla
│   ├── hierarchical.py         # Sincronización automática de pines en hojas jerárquicas padre
│   └── project_backup.py       # Copias de seguridad automáticas y validación ERC con kicad-cli
├── ui/
│   ├── __init__.py
│   ├── main_window.py          # GUI wxPython con modos duales: Portapapeles y Archivo
│   └── config_dialog.py        # Diálogo modal para editar excepciones y paso de grilla
├── config/
│   └── default_config.json     # Configuración JSON editable
├── examples/
│   ├── relay_driver_block.kicad_sch          # Esquemático original con el driver de relé
│   └── relay_driver_duplicated_N4.kicad_sch  # Resultado generado para N=4
├── tests/
│   ├── test_sexpr.py
│   ├── test_label_renamer.py
│   ├── test_block_duplicator.py
│   ├── test_hierarchical.py
│   └── test_relay_block.py     # Test de integración con validación ERC headless
├── main.py                     # Punto de entrada dual (GUI y CLI)
├── icon.png                    # Icono de la aplicación
├── KiCad_Block_Duplicator.desktop # Acceso directo de escritorio para Linux
└── README.md
```

---

## ⚡ Modos de Operación

### 1. Modo Portapapeles (Recomendado para flujo ágil en Hyprland)
1. En KiCad Eeschema, selecciona visualmente con el ratón el bloque a duplicar (componentes, cables, etiquetas).
2. Presiona `Ctrl+C`.
3. Pulsa el atajo global de Hyprland (`Super + D`) o abre la aplicación.
4. Ajusta la cantidad $N$, la separación en mm y pulsa **"Duplicar y Copiar al Portapapeles"**.
5. Regresa a KiCad y presiona `Ctrl+V`. ¡Las $N$ copias aparecerán listas con sus nuevas etiquetas y referencias!

### 2. Modo Archivo (`.kicad_sch`)
1. Abre tu archivo esquemático desde la pestaña **"Modo Archivo"**.
2. Selecciona en la lista los componentes que forman el bloque.
3. Se generará un respaldo `.bak` automático con fecha y hora.
4. Pulsa **"Aplicar Duplicación al Archivo"**.
5. Si el bloque contenía etiquetas jerárquicas, la herramienta actualizará automáticamente el símbolo de la subhoja en el esquemático padre (`sheet pin`).
6. Valida con el botón **"Validar ERC con kicad-cli"** para comprobar que el archivo no tiene infracciones.

---

## ⚙️ Reglas de Renombrado y Excepciones

* **Etiquetas jerárquicas con número (`OUT_1`):**
  * Detecta el sufijo numérico e incrementa: `OUT_1` → `OUT_2`, `OUT_3` ... `OUT_N`.
  * Respeta ceros a la izquierda: `OUT_01` → `OUT_02` ...
* **Etiquetas globales sin número (`NC`, `COM`, `NA`):**
  * El bloque original se conserva sin cambios: `NC`, `COM`, `NA`.
  * Las copias reciben sufijo correlativo desde 2: `NC_2`, `COM_2`, `NA_2` ...
* **Excepciones de Alimentación (+5V, GND, etc.):**
  * Las redes de alimentación definidas en la lista de excepciones (configurables en `config/default_config.json` o desde la GUI) **nunca** se renombran para que todos los bloques compartan la misma alimentación y tierra.
* **Anotación de Componentes:**
  * **Opción B (Por defecto):** Las referencias clonadas reciben signo de interrogación (`R?`, `U?`, `Q?`, `K?`, `D?`, `J?`), listas para usar la herramienta nativa de anotación de KiCad (*Tools → Annotate Schematic*).
  * **Modo Secuencial:** Calcula los números correlativos libres para evitar colisiones (`R7`, `R8`, etc.).

---

## 🚀 Instalación y Atajos en Omarchy / Arch Linux

### Dependencias
En Arch Linux, la herramienta utiliza el entorno Python del sistema con `wxPython` y utilidades Wayland nativas:
```bash
sudo pacman -S python-wxpython wl-clipboard kicad
```

### Configurar Atajo de Teclado en Hyprland
Añade la siguiente línea en tu archivo de configuración de Hyprland (`~/.config/hypr/hyprland.conf` o `~/.config/hypr/bindings.conf`):

```ini
# Duplicador de bloques de KiCad con Super + D
bind = $mainMod, D, exec, python3 /home/emerson/Documentos/kiCad_Duplicar_Incrementar_Labels/main.py
```

### Modo Ultra-Rápido por CLI (Sin abrir ventana)
Si deseas un atajo que multiplique el portapapeles directamente por 4 sin abrir ventana:
```ini
bind = $mainMod SHIFT, D, exec, python3 /home/emerson/Documentos/kiCad_Duplicar_Incrementar_Labels/main.py --clipboard -n 4
```

### Instalar Acceso Directo de Escritorio
```bash
cp /home/emerson/Documentos/kiCad_Duplicar_Incrementar_Labels/KiCad_Block_Duplicator.desktop ~/.local/share/applications/
update-desktop-database ~/.local/share/applications/
```

---

## 🧪 Pruebas Automatizadas

El proyecto incluye 16 pruebas unitarias e integrales que validan la tokenización de S-expressions, el incremento de etiquetas, el aislamiento de UUIDs y la validación con `kicad-cli sch erc`:

```bash
python3 -m unittest discover tests
```

---

## ⚠️ Limitaciones Conocidas

1. **KiCad IPC en Eeschema:** KiCad 10.0.6 aún no dispone de la API IPC activa para el editor de esquemáticos (está programada para KiCad 11). Por ello, la integración ágil en pantalla se realiza mediante el portapapeles de Wayland (`wl-clipboard`) o la modificación directa del `.kicad_sch`.
2. **Subhojas Jerárquicas dentro de Subhojas:** Cuando un bloque clonado contiene a su vez otra hoja jerárquica anidada, se duplica la referencia de archivo de la hoja, pero para mantener coherencia en KiCad se recomienda asignar un nombre de subhoja único si cada canal requiere esquemáticos diferenciados.
