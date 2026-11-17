# KiCad 3D Model Propagator

Plugin de Acción (`ActionPlugin`) para el Editor de PCB de **KiCad 10.0.5+** que detecta y propaga automáticamente modelos 3D (`.step`, `.stp`, `.wrl`) desde un footprint de referencia hacia todos los demás footprints idénticos del proyecto.

## 🚀 Características
- **Captura rápida**: Selecciona un footprint en el PCB Editor o elígelo desde el menú desplegable.
- **Asignación en el acto**: Si el footprint de referencia no tiene modelo 3D, puedes asignárselo directamente desde la ventana (.step, .wrl).
- **Detección inteligente**:
  - Coincidencia exacta por identificador de librería completo (`FPID`).
  - Opción de coincidencia flexible por nombre de huella (ignorando librería).
  - Opción para sobrescribir o respetar footprints que ya tengan modelos 3D existentes.
- **Preservación total de transformaciones**: Replica con exactitud el archivo de modelo (incluyendo variables como `${KICAD8_3DMODEL_DIR}` o `${KIPRJMOD}`), offset en X/Y/Z, rotación, escala, opacidad y visibilidad.
- **Dos modos de propagación**:
  1. **Modo Selección Manual**: Marca/desmarca individualmente en la tabla interactiva de candidatos.
  2. **Modo 1-Clic**: Botón para propagar directamente a todos los componentes iguales de la placa.
- **Refresco instantáneo**: Actualiza el visor 3D (`Alt + 3`) y el PCB sin necesidad de reiniciar KiCad.

## 📁 Estructura del Plugin
```text
KiCad_3D_Model_Propagator/
├── __init__.py                # Registro del ActionPlugin en KiCad
├── plugin.py                  # Definición de ModelPropagatorPlugin (ActionPlugin)
├── core/
│   ├── __init__.py
│   └── model_propagator.py    # Lógica de escaneo, filtrado y clonación de FP_3DMODEL
├── ui/
│   ├── __init__.py
│   └── main_dialog.py         # Interfaz gráfica wxPython interactiva
├── tests/
│   ├── __init__.py
│   └── test_propagator.py     # Suite de pruebas unitarias
├── icon.png                   # Icono de barra de herramientas
└── README.md
```

## 🛠️ Instalación en KiCad
El plugin se instala mediante enlace simbólico a tu directorio de plugins de KiCad 10:
```bash
ln -sfn /home/emerson/Documentos/Plugins-Kicad/KiCad_3D_Model_Propagator ~/.local/share/kicad/10.0/3rdparty/plugins/KiCad_3D_Model_Propagator
```

Para recargar plugins en KiCad sin reiniciar:
> En **KiCad PCB Editor** ve a: **Herramientas $\rightarrow$ Plugins externos $\rightarrow$ Actualizar plugins**.
