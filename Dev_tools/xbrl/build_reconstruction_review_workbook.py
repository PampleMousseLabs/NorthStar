import csv
from collections import defaultdict
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

runlogs = Path("Dev_tools/xbrl/runlogs")
files = sorted(runlogs.glob("reconstructed_IS_*.csv"))
if not files:
    raise SystemExit("No reconstructed income-statement CSVs found.")

companies = defaultdict(list)
for path in files:
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        continue
    ticker = rows[0].get("ticker") or path.stem.split("_")[2]
    companies[ticker].append((path, rows))

wb = Workbook()
wb.remove(wb.active)

headers = [
    "Line item", "Reported value", "XBRL concept", "Parent concept",
    "Depth", "Header", "Subtotal", "Negated"
]

for ticker, filings in sorted(companies.items()):
    ws = wb.create_sheet(ticker[:31])
    ws.freeze_panes = "A3"
    ws.sheet_view.showGridLines = False

    for path, rows in filings:
        first = rows[0]
        accession = first.get("filing_accession", "")
        period = first.get("period_end", "")

        ws.append([f"{ticker} | Period: {period} | Accession: {accession}"])
        ws.merge_cells(start_row=ws.max_row, start_column=1,
                       end_row=ws.max_row, end_column=8)
        title = ws.cell(ws.max_row, 1)
        title.font = Font(bold=True, size=12, color="FFFFFF")
        title.fill = PatternFill("solid", fgColor="26354A")

        ws.append(headers)
        for cell in ws[ws.max_row]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="53647A")

        for item in rows:
            raw = item.get("value", "")
            try:
                value = float(raw) if raw not in ("", None) else None
            except (TypeError, ValueError):
                value = raw

            depth = int(float(item.get("depth") or 0))
            ws.append([
                item.get("label", ""),
                value,
                item.get("concept", ""),
                item.get("parent_concept", ""),
                depth,
                item.get("is_header", ""),
                item.get("is_total", ""),
                item.get("negated", ""),
            ])

            r = ws.max_row
            ws.cell(r, 1).alignment = Alignment(indent=min(depth, 15))
            if str(item.get("is_header", "")).lower() == "true":
                ws.cell(r, 1).font = Font(bold=True)
            if str(item.get("is_total", "")).lower() == "true":
                for cell in ws[r]:
                    cell.font = Font(bold=True)
                    cell.border = cell.border.copy(
                        top=__import__("openpyxl").styles.Border(
                            top=__import__("openpyxl").styles.Side(style="thin")
                        ).top
                    )
            if isinstance(value, float):
                ws.cell(r, 2).number_format = '#,##0.0;[Red](#,##0.0);-'

        ws.append([])

    widths = [48, 19, 58, 48, 9, 10, 10, 10]
    for i, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = width

out = runlogs / "income_statement_reconstruction_review.xlsx"
wb.save(out)
print(f"Created {out} | {len(companies)} companies | {len(files)} filing CSVs")
