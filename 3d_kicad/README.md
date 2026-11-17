# Propagar modelos 3D para KiCad 10

ActionPlugin para **KiCad 10.0.5** que toma los modelos 3D de una huella y los
copia únicamente a las instancias vacías con el mismo identificador completo de
biblioteca (FPID, por ejemplo `Resistor_SMD:R_0805_2012Metric`).
El plugin rechaza otras versiones mayores para evitar mutaciones con una API
`pcbnew` incompatible.

## Criterio y garantías

- Dos huellas se consideran iguales solo cuando `GetFPIDAsString()` coincide y
  no está vacío. El nombre aislado no basta, por lo que no se mezclan librerías.
- Una huella que ya tenga una o más entradas en `Models()` nunca se sobrescribe.
- Se copian todas las entradas 3D del origen. De cada una se preservan sin
  normalizar la ruta, además de offset, rotación, escala, opacidad y visibilidad.
- El plugin solo modifica la colección de modelos 3D. No cambia posición, capa,
  valor, referencia, pads ni ninguna otra propiedad de la huella.

## Archivos

```text
propagate_3d_models/
├── __init__.py   # registro del ActionPlugin
├── action.py     # flujo dentro del PCB Editor y manejo de errores
├── dialogs.py    # interfaz wxPython
└── logic.py      # comparación, detección y copia de modelos
tests/
└── test_logic.py # pruebas contra los bindings pcbnew instalados
```

## Instalación manual en KiCad 10

1. Guarde y cierre cualquier edición importante del board.
2. Copie la carpeta completa `propagate_3d_models` a la carpeta de plugins:

   - Linux: `~/.local/share/kicad/10.0/scripting/plugins/`
   - macOS: `~/Documents/KiCad/10.0/scripting/plugins/`
   - Windows: `%USERPROFILE%\Documents\KiCad\10.0\scripting\plugins\`

   El resultado debe contener
   `.../scripting/plugins/propagate_3d_models/__init__.py`.

3. En el PCB Editor abra **Preferencias → Preferencias → Action Plugins** y use
   el botón **Reload Plugins**. También puede ejecutar **Tools → External
   Plugins → Refresh Plugins**. No es necesario reiniciar KiCad.
4. Ejecute **Tools → External Plugins → Propagar modelos 3D**.

## Flujo de uso

1. Abra un board ya guardado.
2. Seleccione una sola huella que tenga el modelo correcto. Si no selecciona
   ninguna, el plugin muestra una lista; si selecciona varias, permite elegir
   una de ellas.
3. Si la referencia está vacía, seleccione un `.wrl`, `.step` o `.stp`. El
   modelo se añadirá con transformación neutra cuando pulse **Aplicar**.
4. Revise el FPID, las rutas de los modelos y la tabla de candidatos con
   referencia y coordenadas X/Y.
5. Elija **Todos** o **Selección manual**. En modo manual use los checkboxes y
   los botones **Marcar todos** / **Desmarcar todos**.
6. Pulse **Aplicar**, compruebe el resultado en el visor 3D y guarde con Ctrl+S.
   Si pulsa **Cancelar**, el board no se modifica.

## Errores controlados

- No hay board, el board no se ha guardado o no contiene huellas.
- No hay una referencia válida o su FPID está vacío.
- La referencia no tiene modelo y se cancela la selección del archivo.
- Una ruta existente no puede resolverse a un archivo real.
- No quedan candidatos con el mismo FPID y `Models()` vacío.
- Una huella recibió un modelo mientras el diálogo estaba abierto: se omite en
  la comprobación final y nunca se sobrescribe.

## Pruebas

Con KiCad 10 y sus bindings de Python instalados:

```bash
python3 -m unittest discover -s tests -v
```

Las pruebas comprueban el FPID completo, el filtrado de huellas ocupadas, el
orden natural de referencias y la copia fiel de todas las propiedades 3D.

## Mejoras posibles

- Migración futura a la API IPC: los bindings SWIG `pcbnew` están obsoletos
  desde KiCad 9 y está previsto retirarlos en KiCad 11.
- Icono claro/oscuro y publicación mediante Plugin and Content Manager.
- Vista previa del modelo y filtros por referencia antes de aplicar.
- Conversión opcional de rutas absolutas a `${KIPRJMOD}` solicitada de forma
  explícita por el usuario (el comportamiento actual siempre preserva la ruta).
