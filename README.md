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

La instalación se realiza mediante **enlaces simbólicos (symlinks)** hacia la ruta oficial de plugins de KiCad 10:

```text
/home/emerson/.local/share/kicad/10.0/3rdparty/plugins
```
*(Equivalente a: `~/.local/share/kicad/10.0/3rdparty/plugins`)*

De este modo, cualquier cambio o actualización en este repositorio se refleja inmediatamente en KiCad sin necesidad de reinstalar ni copiar archivos manualmente.

### Estructura de Enlaces Simbólicos Creados
```text
/home/emerson/.local/share/kicad/10.0/3rdparty/plugins/
├── Block_Aligner -> /home/emerson/Documentos/Plugins-Kicad/Block_Aligner
├── KiCad_3D_Model_Propagator -> /home/emerson/Documentos/Plugins-Kicad/KiCad_3D_Model_Propagator
└── kicad-routing-progress-plugin -> /home/emerson/Documentos/Plugins-Kicad/kicad-routing-progress-plugin
```

---

## 🔄 Restauración en un Nuevo Sistema (después de formatear)

Cuando formatees tu equipo o instales en una nueva máquina, sigue estos sencillos pasos:

### Paso 1: Clonar el repositorio
```bash
cd ~/Documentos
git clone https://github.com/EmersonEE/Plugins-Kicad.git
cd Plugins-Kicad
```

### Paso 2: Instalación Automática (Recomendado)
Ejecuta el script incluido [`install_symlinks.sh`](./install_symlinks.sh):
```bash
chmod +x install_symlinks.sh
./install_symlinks.sh
```

El script se encargará automáticamente de:
1. Crear el directorio `/home/emerson/.local/share/kicad/10.0/3rdparty/plugins`.
2. Crear los enlaces simbólicos de los Action Plugins de PCB.
3. Crear los enlaces simbólicos de los accesos directos `.desktop` en `~/.local/share/applications`.

### Opción Alternativa: Instalación Manual por Comandos
Si prefieres crearlos paso a paso en la terminal:

```bash
# 1. Crear el directorio de plugins de KiCad 10
mkdir -p /home/emerson/.local/share/kicad/10.0/3rdparty/plugins

# 2. Enlazar los Action Plugins de PCB
ln -sfn /home/emerson/Documentos/Plugins-Kicad/Block_Aligner /home/emerson/.local/share/kicad/10.0/3rdparty/plugins/Block_Aligner
ln -sfn /home/emerson/Documentos/Plugins-Kicad/KiCad_3D_Model_Propagator /home/emerson/.local/share/kicad/10.0/3rdparty/plugins/KiCad_3D_Model_Propagator
ln -sfn /home/emerson/Documentos/Plugins-Kicad/kicad-routing-progress-plugin /home/emerson/.local/share/kicad/10.0/3rdparty/plugins/kicad-routing-progress-plugin
```

### Paso 3: Recargar Plugins en KiCad (Sin reiniciar)
Una vez creados los enlaces:
1. Abre **KiCad PCB Editor**.
2. Ve al menú superior: **Herramientas → Plugins externos → Refrescar plugins** (o **Actualizar plugins**).
3. Los botones y herramientas aparecerán listos en la barra superior y menús contextuales.

---

## 🖥️ Aplicaciones de Escritorio Complementarias

Para las herramientas de esquemático (**`KiCad_BOM_LaElectronica`**, **`kiCad_Duplicar_Incrementar_Labels`** y **`Schematic_Footprint_Manager`**):

### Enlazar al menú de aplicaciones de Linux (`.desktop`):
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
