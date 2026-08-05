import json
from typing import Any

from app.database import db_session


def calculate_quote_totals(
    json_detail: dict[str, Any],
    design_fee_pct: float,
    management_fee_pct: float,
    tax_pct: float,
    margin_pct: float,
) -> dict[str, float]:
    direct_cost = 0.0
    for group in json_detail.get("groups", []):
        for item in group.get("items", []):
            qty = float(item.get("quantity", 0) or 0)
            unit_price = float(item.get("unit_price", 0) or 0)
            line_total = qty * unit_price
            item["line_total"] = line_total
            direct_cost += line_total

    design_fee = direct_cost * design_fee_pct / 100
    subtotal = direct_cost + design_fee
    management_fee = subtotal * management_fee_pct / 100
    before_tax = subtotal + management_fee
    tax = before_tax * tax_pct / 100
    before_margin = before_tax + tax
    margin = before_margin * margin_pct / 100
    total = before_margin + margin

    return {
        "direct_cost": round(direct_cost, 2),
        "design_fee": round(design_fee, 2),
        "management_fee": round(management_fee, 2),
        "tax": round(tax, 2),
        "margin": round(margin, 2),
        "total": round(total, 2),
    }


def merge_template_with_quantities(template_structure: dict, quantities: dict[str, float]) -> dict:
    """Merge BOQ template with user-entered quantities keyed by 'group_idx-item_idx'."""
    result = {"groups": []}
    for gi, group in enumerate(template_structure.get("groups", [])):
        new_group = {"name": group["name"], "items": []}
        for ii, item in enumerate(group.get("items", [])):
            key = f"{gi}-{ii}"
            qty = quantities.get(key, 0)
            new_item = dict(item)
            new_item["quantity"] = float(qty or 0)
            new_group["items"].append(new_item)
        result["groups"].append(new_group)
    return result


def get_studio_defaults() -> dict[str, float]:
    with db_session() as conn:
        row = conn.execute("SELECT * FROM studio_profile WHERE id = 1").fetchone()
        if not row:
            return {
                "design_fee_pct": 15,
                "management_fee_pct": 8,
                "tax_pct": 6,
                "margin_pct": 25,
            }
        return {
            "design_fee_pct": row["default_design_fee_pct"],
            "management_fee_pct": row["default_management_fee_pct"],
            "tax_pct": row["default_tax_pct"],
            "margin_pct": row["default_margin_pct"],
        }


def export_quote_pdf(quote: dict, project: dict, studio: dict) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.add_font("Helvetica", "", "Helvetica")

    pdf.set_font("Helvetica", size=16)
    pdf.cell(0, 10, studio.get("name", "Studio OS") or "Studio OS", ln=True)
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 8, f"Project: {project.get('name', '')}", ln=True)
    pdf.cell(0, 8, f"Quote v{quote.get('version', 1)} | Status: {quote.get('status', 'draft')}", ln=True)
    pdf.ln(5)

    detail = json.loads(quote["json_detail"]) if isinstance(quote["json_detail"], str) else quote["json_detail"]
    pdf.set_font("Helvetica", size=10)
    for group in detail.get("groups", []):
        pdf.set_font("Helvetica", size=11)
        pdf.cell(0, 8, group.get("name", ""), ln=True)
        pdf.set_font("Helvetica", size=10)
        for item in group.get("items", []):
            qty = item.get("quantity", 0)
            unit_price = item.get("unit_price", 0)
            line = item.get("line_total", qty * unit_price)
            line_text = (
                f"  {item.get('name', '')} | {qty} {item.get('unit', '')} "
                f"x {unit_price:.2f} = {line:.2f}"
            )
            pdf.cell(0, 6, line_text, ln=True)
        pdf.ln(2)

    pdf.ln(5)
    pdf.cell(0, 8, f"Direct Cost: {quote.get('direct_cost', 0):,.2f}", ln=True)
    pdf.cell(0, 8, f"Design Fee ({quote.get('design_fee_pct')}%): included", ln=True)
    pdf.cell(0, 8, f"Management ({quote.get('management_fee_pct')}%): included", ln=True)
    pdf.cell(0, 8, f"Tax ({quote.get('tax_pct')}%): included", ln=True)
    pdf.cell(0, 8, f"Margin ({quote.get('margin_pct')}%): included", ln=True)
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, f"TOTAL: {quote.get('total', 0):,.2f} CNY", ln=True)

    return pdf.output()
