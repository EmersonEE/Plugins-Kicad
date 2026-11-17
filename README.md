# 🔌 Colección de Plugins y Herramientas KiCad

Repositorio consolidado (monorepo) que reúne los plugins de acción (`ActionPlugin`) y aplicaciones de escritorio complementarias para el flujo de trabajo en **KiCad** (Esquemático y Editor de PCB).

---

## 📦 Contenido del Repositorio

| Directorio | Tipo | Entorno / Uso | Descripción |
| :--- | :--- | :--- | :--- |
| **[`Block_Aligner`](./Block_Aligner)** | Action Plugin | PCB Editor | Alineación inteligente de bloques de huellas y componentes en el diseño de PCB. |
| **[`KiCad_3D_Model_Propagator`](./KiCad_3D_Model_Propagator)** | Action Plugin | PCB Editor | Propagación automática de modelos 3D (`.step`, `.wrl`) hacia todas las huellas idénticas sin modelo asignado. |
| **[`kicad-routing-progress-plugin`](./kicad-routing-progress-plugin)** | Action Plugin | PCB Editor | Medición y visualización del porcentaje de avance en el ruteo de pistas del PCB. |
| **[`KiCad_BOM_LaElectronica`](./KiCad_BOM_LaElectronica)** | Desktop App | Esquemático / Compras | Extracción de listas de materiales (BOM) desde esquemáticos y cotización en tiempo real en la tienda La Electrónica. |
| **[`kiCad_Duplicar_Incrementar_Labels`](./kiCad_Duplicar_Incrementar_Labels)** | Desktop App | Esquemático | Duplicación automatizada de bloques de circuitos esquemáticos con incremento inteligente de etiquetas (labels) y referencias. |
| **[`Schematic_Footprint_Manager`](./Schematic_Footprint_Manager)** | Desktop App | Esquemático | Gestor visual y masivo de asignación de huellas (footprints) en esquemáticos KiCad. |
| **[`3d_kicad`](./3d_kicad)** | Pruebas / Prototipo | PCB Editor | Prototipo inicial y pruebas unitarias de propagación de modelos 3D para KiCad 10. |

---

## 🛠️ Instalación y Uso

### 1. Plugins de Acción del Editor PCB (`ActionPlugin`)
Para **`Block_Aligner`**, **`KiCad_3D_Model_Propagator`** y **`kicad-routing-progress-plugin`**:

Copiar la carpeta del plugin correspondiente al directorio de scripting de KiCad según el sistema operativo:

* **Linux**: `~/.local/share/kicad/<versión>/scripting/plugins/`
* **Windows**: `%USERPROFILE%\Documents\KiCad\<versión>\scripting\plugins\`
* **macOS**: `~/Documents/KiCad/<versión>/scripting/plugins/`

En el PCB Editor:
1. Ir a **Preferencias → Preferencias → Action Plugins**.
2. Hacer clic en **Reload Plugins** (o desde la barra de herramientas: **Herramientas → External Plugins → Refresh Plugins**).

### 2. Aplicaciones de Escritorio Complementarias
Para **`KiCad_BOM_LaElectronica`**, **`kiCad_Duplicar_Incrementar_Labels`** y **`Schematic_Footprint_Manager`**:

Cada una incluye su punto de entrada principal (`main.py`) y lanzador `.desktop` para integrarse al menú de aplicaciones en Linux:

```bash
# Ejemplo de ejecución directa:
python3 KiCad_BOM_LaElectronica/main.py
python3 kiCad_Duplicar_Incrementar_Labels/main.py
python3 Schematic_Footprint_Manager/main.py
```

---

## 👤 Autor
* **Emerson Perez** ([@EmersonEE](https://github.com/EmersonEE))
