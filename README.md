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

## 🛠️ Instalación mediante Enlaces Simbólicos

La instalación recomendada de los plugins se realiza mediante **enlaces simbólicos (symlinks)** hacia la ruta de plugins de KiCad 10. De esta manera, cualquier actualización o cambio en este repositorio se refleja inmediatamente en KiCad sin necesidad de reinstalar ni duplicar archivos.

Ruta de plugins de KiCad 10:
```text
/home/emerson/.local/share/kicad/10.0/3rdparty/plugins
```
*(O de forma equivalente: `~/.local/share/kicad/10.0/3rdparty/plugins`)*

### 1. Instalación Rápida de Plugins de PCB (Script Automático)

Puedes ejecutar el script incluido [`install_symlinks.sh`](./install_symlinks.sh) desde la raíz de este repositorio:

```bash
chmod +x install_symlinks.sh
./install_symlinks.sh
```

### 2. Instalación Manual por Comandos

Si prefieres crearlos manualmente, ejecuta en tu terminal:

```bash
# 1. Crear el directorio de plugins de KiCad 10 si no existe
mkdir -p /home/emerson/.local/share/kicad/10.0/3rdparty/plugins

# 2. Crear los enlaces simbólicos de los Action Plugins
ln -sfn /home/emerson/Documentos/Plugins-Kicad/Block_Aligner /home/emerson/.local/share/kicad/10.0/3rdparty/plugins/Block_Aligner
ln -sfn /home/emerson/Documentos/Plugins-Kicad/KiCad_3D_Model_Propagator /home/emerson/.local/share/kicad/10.0/3rdparty/plugins/KiCad_3D_Model_Propagator
ln -sfn /home/emerson/Documentos/Plugins-Kicad/kicad-routing-progress-plugin /home/emerson/.local/share/kicad/10.0/3rdparty/plugins/kicad-routing-progress-plugin
```

### 3. Recargar Plugins en KiCad (Sin reiniciar)

Una vez creados los enlaces:
1. Abre **KiCad PCB Editor**.
2. Dirígete al menú: **Herramientas → Plugins externos → Refrescar plugins** (o **Actualizar plugins**).
3. Verás los iconos y opciones de los plugins listos en la barra de herramientas y menús.

---

## 🖥️ Aplicaciones de Escritorio Complementarias

Para las aplicaciones de esquemático y utilidades de escritorio (**`KiCad_BOM_LaElectronica`**, **`kiCad_Duplicar_Incrementar_Labels`** y **`Schematic_Footprint_Manager`**):

### Enlace al menú de aplicaciones de Linux (`.desktop`):
```bash
mkdir -p ~/.local/share/applications

ln -sfn /home/emerson/Documentos/Plugins-Kicad/KiCad_BOM_LaElectronica/KiCad_BOM_LaElectronica.desktop ~/.local/share/applications/
ln -sfn /home/emerson/Documentos/Plugins-Kicad/kiCad_Duplicar_Incrementar_Labels/KiCad_Block_Duplicator.desktop ~/.local/share/applications/
ln -sfn /home/emerson/Documentos/Plugins-Kicad/Schematic_Footprint_Manager/Schematic_Footprint_Manager.desktop ~/.local/share/applications/
```

### Ejecución directa desde terminal:
```bash
python3 /home/emerson/Documentos/Plugins-Kicad/KiCad_BOM_LaElectronica/main.py
python3 /home/emerson/Documentos/Plugins-Kicad/kiCad_Duplicar_Incrementar_Labels/main.py
python3 /home/emerson/Documentos/Plugins-Kicad/Schematic_Footprint_Manager/main.py
```

---

## 👤 Autor
* **Emerson Perez** ([@EmersonEE](https://github.com/EmersonEE))
