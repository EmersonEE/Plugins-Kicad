"""Export BOM and live pricing estimates to CSV and HTML formats."""

import csv
import os
from typing import List
from core.bom_extractor import BOMItem


class BOMExporter:
    """Exports priced BOM data to CSV and HTML files."""

    @staticmethod
    def export_csv(file_path: str, items: List[BOMItem]) -> bool:
        """Export BOM items with prices to CSV format."""
        try:
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "#",
                    "Cantidad",
                    "Referencias",
                    "Valor",
                    "Huella (Footprint)",
                    "Producto en La Electronica GT",
                    "Precio Unitario (GTQ)",
                    "Subtotal (GTQ)",
                    "Stock",
                    "Enlace a Tienda",
                ])

                total_qty = 0
                total_cost = 0.0

                for idx, itm in enumerate(items, 1):
                    if itm.ignored:
                        continue
                    prod_title = itm.matched_product.title if itm.matched_product else "(No encontrado)"
                    unit_p = f"Q{itm.unit_price:.2f}" if itm.is_matched else "-"
                    sub_p = f"Q{itm.subtotal:.2f}" if itm.is_matched else "-"
                    stock = "Disponible" if itm.is_available else ("Agotado" if itm.is_matched else "-")
                    url = itm.matched_product.full_url if itm.matched_product else ""

                    writer.writerow([
                        idx,
                        itm.quantity,
                        itm.references_str,
                        itm.value,
                        itm.footprint,
                        prod_title,
                        unit_p,
                        sub_p,
                        stock,
                        url,
                    ])

                    total_qty += itm.quantity
                    total_cost += itm.subtotal

                # Summary Row
                writer.writerow([])
                writer.writerow([
                    "TOTALES",
                    total_qty,
                    f"{len(items)} líneas",
                    "",
                    "",
                    "",
                    "",
                    f"Q{total_cost:.2f}",
                    "",
                    "",
                ])
            return True
        except Exception:
            return False

    @staticmethod
    def export_html(file_path: str, project_name: str, items: List[BOMItem]) -> bool:
        """Export BOM items to a modern, interactive HTML report."""
        try:
            total_qty = sum(itm.quantity for itm in items if not itm.ignored)
            total_cost = sum(itm.subtotal for itm in items if not itm.ignored)
            matched_count = sum(1 for itm in items if itm.is_matched and not itm.ignored)
            active_items = [itm for itm in items if not itm.ignored]

            rows_html = []
            for idx, itm in enumerate(active_items, 1):
                if itm.is_matched:
                    prod_link = f'<a href="{itm.matched_product.full_url}" target="_blank" class="prod-link">{itm.matched_product.title}</a>'
                    unit_p = f"Q {itm.unit_price:.2f}"
                    sub_p = f"Q {itm.subtotal:.2f}"
                    stock_badge = '<span class="badge stock-ok">En Stock</span>' if itm.is_available else '<span class="badge stock-out">Agotado</span>'
                    row_class = ""
                else:
                    prod_link = '<span class="text-muted">(Sin coincidencia en tienda)</span>'
                    unit_p = "-"
                    sub_p = "-"
                    stock_badge = '<span class="badge stock-unknown">No cotizado</span>'
                    row_class = "row-unmatched"

                rows_html.append(f"""
                <tr class="{row_class}">
                    <td class="text-center">{idx}</td>
                    <td class="text-center"><strong>{itm.quantity}</strong></td>
                    <td><code>{itm.references_str}</code></td>
                    <td><strong>{itm.value}</strong></td>
                    <td class="text-small">{itm.footprint}</td>
                    <td>{prod_link}</td>
                    <td class="text-right">{unit_p}</td>
                    <td class="text-right font-bold">{sub_p}</td>
                    <td class="text-center">{stock_badge}</td>
                </tr>
                """)

            html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cotización BOM - {project_name} | La Electrónica GT</title>
    <style>
        :root {{
            --primary: #0066cc;
            --primary-dark: #004c99;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --border: #e2e8f0;
            --text: #1e293b;
            --text-muted: #64748b;
            --success: #16a34a;
            --danger: #dc2626;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 24px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .header {{
            background: var(--card-bg);
            padding: 24px;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
        }}
        .title h1 {{
            margin: 0 0 6px 0;
            font-size: 24px;
            color: var(--primary-dark);
        }}
        .title p {{
            margin: 0;
            color: var(--text-muted);
            font-size: 14px;
        }}
        .summary-card {{
            background: #eff6ff;
            border: 1px solid #bfdbfe;
            padding: 16px 24px;
            border-radius: 10px;
            text-align: right;
        }}
        .summary-card .label {{
            font-size: 13px;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .summary-card .price {{
            font-size: 32px;
            font-weight: 700;
            color: var(--primary-dark);
            margin-top: 4px;
        }}
        .stats-row {{
            display: flex;
            gap: 16px;
            margin-bottom: 20px;
        }}
        .stat-box {{
            flex: 1;
            background: var(--card-bg);
            padding: 14px;
            border-radius: 8px;
            border: 1px solid var(--border);
            text-align: center;
        }}
        .stat-box .val {{
            font-size: 20px;
            font-weight: 700;
            color: var(--text);
        }}
        .stat-box .desc {{
            font-size: 12px;
            color: var(--text-muted);
            margin-top: 2px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--card-bg);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        th, td {{
            padding: 12px 14px;
            border-bottom: 1px solid var(--border);
            font-size: 14px;
            text-align: left;
        }}
        th {{
            background: #f1f5f9;
            font-weight: 600;
            color: var(--text-muted);
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        tr:hover {{
            background-color: #f8fafc;
        }}
        .row-unmatched {{
            background-color: #fffbeb;
        }}
        .text-center {{ text-align: center; }}
        .text-right {{ text-align: right; }}
        .font-bold {{ font-weight: 700; }}
        .text-small {{ font-size: 12px; color: var(--text-muted); }}
        .text-muted {{ color: var(--text-muted); }}
        code {{
            background: #f1f5f9;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 12px;
            font-family: monospace;
        }}
        .prod-link {{
            color: var(--primary);
            text-decoration: none;
            font-weight: 500;
        }}
        .prod-link:hover {{
            text-decoration: underline;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 600;
        }}
        .stock-ok {{ background: #dcfce7; color: #15803d; }}
        .stock-out {{ background: #fee2e2; color: #b91c1c; }}
        .stock-unknown {{ background: #f1f5f9; color: #64748b; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="title">
                <h1>📋 Cotización de Lista de Materiales (BOM)</h1>
                <p>Proyecto: <strong>{project_name}</strong> | Precios en tiempo real de <strong>laelectronica.com.gt</strong> (Guatemala)</p>
            </div>
            <div class="summary-card">
                <div class="label">Costo Total Estimado</div>
                <div class="price">Q {total_cost:.2f}</div>
            </div>
        </div>

        <div class="stats-row">
            <div class="stat-box">
                <div class="val">{total_qty}</div>
                <div class="desc">Total de Componentes</div>
            </div>
            <div class="stat-box">
                <div class="val">{len(active_items)}</div>
                <div class="desc">Líneas de BOM Únicas</div>
            </div>
            <div class="stat-box">
                <div class="val">{matched_count} / {len(active_items)}</div>
                <div class="desc">Productos Encontrados</div>
            </div>
        </div>

        <table>
            <thead>
                <tr>
                    <th class="text-center">#</th>
                    <th class="text-center">Cant.</th>
                    <th>Referencias</th>
                    <th>Valor</th>
                    <th>Huella</th>
                    <th>Producto en La Electrónica</th>
                    <th class="text-right">Precio Unit.</th>
                    <th class="text-right">Subtotal</th>
                    <th class="text-center">Stock</th>
                </tr>
            </thead>
            <tbody>
                {"".join(rows_html)}
            </tbody>
        </table>
    </div>
</body>
</html>"""
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            return True
        except Exception:
            return False
