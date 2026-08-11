"""项目损益（P&L）报表 PDF 生成（A4 横向），供 /app/projects/{id}/finance.pdf 使用。

复用 budget.py 的 fpdf + Arial Unicode 字体方案，保证离线可用、中文不乱码。
"""

import os

from fpdf import FPDF

_FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"


def build_finance_pdf(project: dict, pnl: dict, curve: list, studio: dict) -> bytes:
    """生成 A4 横向损益报表 PDF 字节流。"""
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    if os.path.exists(_FONT):
        pdf.add_font("UF", "", _FONT, uni=True)
        ff = "UF"
    else:
        ff = "Helvetica"

    studio_name = (studio or {}).get("name") or "Studio OS"
    proj_name = project.get("name", "")
    proj_code = project.get("code", "")

    pdf.set_font(ff, "", 16)
    pdf.cell(0, 10, studio_name, ln=True)
    pdf.set_font(ff, "", 12)
    pdf.cell(0, 8, f"项目损益报表 (P&L) · {proj_name} · {proj_code}", ln=True)
    pdf.ln(2)

    rev = pnl.get("revenue") or 0.0
    cost = pnl.get("cost") or 0.0
    profit = pnl.get("profit")
    margin = pnl.get("margin_pct")

    pdf.set_font(ff, "", 11)
    pdf.cell(0, 7, f"收入 Revenue：¥{rev:,.2f}", ln=True)
    pdf.cell(0, 7, f"成本 Cost：¥{cost:,.2f}", ln=True)
    pdf.cell(0, 7, f"利润 Profit：¥{(profit if profit is not None else 0):,.2f}", ln=True)
    pdf.cell(
        0,
        7,
        f"毛利率 Margin：{(f'{margin:.2f}%' if margin is not None else '—')}",
        ln=True,
    )
    pdf.ln(3)

    if curve:
        pdf.set_font(ff, "", 10)
        cols = [
            ("里程碑", 70),
            ("到期", 32),
            ("累计收入", 46),
            ("累计成本", 46),
            ("毛利率", 30),
        ]

        def _header():
            pdf.set_fill_color(59, 51, 42)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font(ff, "", 9)
            for name, w in cols:
                pdf.cell(w, 8, name, border=1, align="C", fill=True)
            pdf.ln()
            pdf.set_text_color(0, 0, 0)

        _header()
        pdf.set_font(ff, "", 9)
        fill = False
        for p in curve:
            if fill:
                pdf.set_fill_color(245, 240, 232)
            else:
                pdf.set_fill_color(255, 255, 255)
            vals = [
                str(p.get("name", "")),
                str(p.get("date") or "—"),
                f"¥{p['cum_revenue']:,.0f}",
                f"¥{p['cum_cost']:,.0f}",
                (f"{p['margin_pct']:.1f}%" if p.get("margin_pct") is not None else "—"),
            ]
            for (name, w), v in zip(cols, vals):
                align = "L" if name == "里程碑" else "C"
                pdf.cell(w, 7, v, border=1, align=align, fill=fill)
            pdf.ln()
            fill = not fill

    out = pdf.output()
    if isinstance(out, str):
        return out.encode("latin-1")
    return bytes(out)
