# KiCad Net Routing Progress Plugin (Estilo Altium Designer)

Plugin para **KiCad 10.x / 9.x** que analiza en tiempo real la conectividad y el porcentaje de ruteo pendiente por cada net individual del proyecto, replicando la funcionalidad del panel de Nets de Altium Designer.

---

## 🚀 Características Principales

- **% de Ruteo Pendiente por Net**: Muestra el progreso exacto ($100\%$ = sin rutear, $0\%$ = completamente ruteada).
- **Cálculo Topológico de Conectividad**: Utiliza la topología geométrica de `CONNECTIVITY_DATA` de KiCad para detectar islas de cobre, pistas, vías y polígonos.
- **Resumen Global del PCB**: Barra de progreso visual interactiva, total de conexiones esperadas vs pendientes y longitud total de pistas.
- **Filtros en Tiempo Real**: Búsqueda por subcadena o comodines (`GND*`, `SPI_*`), filtro por estado (Solo pendientes, Solo parciales, etc.) y opción para ocultar nets de 0 o 1 pad.
- **Resaltado en PCB con 1 Clic**: Al seleccionar cualquier fila en la tabla, la net se resalta instantáneamente en el editor de PCB de KiCad.
- **Recálculo en Vivo**: Botón `🔄 Actualizar / Recalcular` para actualizar el estado mientras ruteas sin cerrar la ventana.
- **Exportación a CSV**: Exporta el reporte completo con marcas de tiempo para control de calidad o documentación.
- **Diseño Adaptativo**: Compatible al 100% con temas oscuros (Dark Theme) y claros de GTK / Linux / Windows / macOS.

---

## 📐 Algoritmo de Cálculo

Para cualquier net con $N$ pads:
1. **Conexiones Requeridas ($E$)**: Para conectar un árbol de $N$ nodos se requieren exactamente $E = N - 1$ conexiones mínimas (si $N \le 1$, $E = 0$).
2. **Islas / Componentes Conexos ($C$)**: Se agrupan los pads que ya están físicamente interconectados por pistas, vías o planos de cobre en $C$ clusters conexos.
3. **Conexiones Pendientes ($P$)**: La cantidad de líneas aéreas (ratsnest) pendientes para unir las $C$ islas es:
   $$P = \max(0, C - 1)$$
4. **Porcentaje de Ruteo Pendiente**:
   $$\% \text{ Pendiente} = \frac{P}{E} \times 100\% = \frac{C - 1}{N - 1} \times 100\%$$
5. **Porcentaje de Ruteo Completado**:
   $$\% \text{ Ruteado} = 100\% - \% \text{ Pendiente} = \frac{N - C}{N - 1} \times 100\%$$

---

## 🛠️ Instalación mediante Enlace Simbólico

Desde la terminal en Linux:

```bash
ln -sfn /home/emerson/Documentos/Plugins-Kicad/kicad-routing-progress-plugin /home/emerson/.local/share/kicad/10.0/3rdparty/plugins/kicad-routing-progress-plugin
```

En KiCad PCB Editor:
- Menú **Herramientas** → **Plugins externos** → **Refrescar plugins** (o reiniciar KiCad).
- Aparecerá el icono **Net Routing Progress** en la barra de herramientas superior y en el menú contextual.
