# KiCad BOM Estimator (La Electrónica GT)

Herramienta gráfica interactiva (wxPython) para KiCad que analiza la lista de materiales (BOM) de tus esquemáticos, consulta en **tiempo real** los precios y stock en la tienda guatemalteca **La Electrónica** ([laelectronica.com.gt](https://laelectronica.com.gt/)), calcula el **Costo Total en Quetzales (Q)** del proyecto y permite exportar cotizaciones a Excel / CSV y reportes interactivos en HTML.

---

## Características Principales

- **Extracción Automática de BOM de KiCad**:
  - Lee archivos individuales `.kicad_sch` o proyectos enteros `.kicad_pro` (con soporte para sub-hojas y jerarquías).
  - Agrupa automáticamente componentes idénticos (`Cantidad × Valor`).
  - Filtra pines de alimentación (`#PWR`, `GND`, `+3V3`), componentes DNP y elementos fuera de BOM.
- **Cotización en Vivo con `laelectronica.com.gt`**:
  - Consulta los precios unitarios y la disponibilidad de inventario en tiempo real.
  - Normaliza automáticamente valores (`10k` $\rightarrow$ `Resistencia 10k`, `100nF` $\rightarrow$ `Capacitor 100nF`, `ESP32`, `LM358`, etc.).
  - Calcula automáticamente `Cantidad × Precio Unitario = Subtotal (Q)` y el **Costo Total del Proyecto**.
- **Selector de Productos Alternativos**:
  - Permite hacer doble clic en cualquier fila para elegir entre productos sugeridos o buscar manualmente en la tienda.
- **Exportación**:
  - **CSV (Excel / Calc)**: Lista completa con subtotales, stock y enlaces a la tienda.
  - **Reporte HTML Interactivo**: Visualización limpia con tarjetas de resumen, métricas y enlaces listos para abrir en el navegador.

---

## Cómo Ejecutar la Aplicación

### Desde la Terminal

Gracias al alias y comando configurado, puedes ejecutar en cualquier directorio:

```bash
# Abrir la aplicación
kbom

# O abriendo un esquemático directamente
kbom mi_esquematico.kicad_sch
```

### Desde el Menú de Hyprland (Wofi / Walker / Rofi)
Busca **"KiCad BOM"** o **"La Electronica"** en tu menú de aplicaciones y ábrelo con un clic o Enter.
