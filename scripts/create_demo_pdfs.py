"""Create public synthetic PDFs for exercising the real ingestion path."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output' / 'pdf'
OUTPUT.mkdir(parents=True, exist_ok=True)


def page(c, number, heading, lines):
    w,h=A4
    c.setFillColor(HexColor('#0b1424'))
    c.rect(0,0,w,h,fill=1,stroke=0)
    c.setFillColor(HexColor('#61e2be'))
    c.setFont('Helvetica-Bold',10)
    c.drawString(48,h-55,'SOURCEMIND / EVIDENCE LAB')
    c.setFillColor(HexColor('#f0f5ff'))
    c.setFont('Helvetica-Bold',24)
    c.drawString(48,h-112,heading)
    c.setFont('Helvetica',12)
    for i,line in enumerate(lines):
        c.drawString(48,h-158-i*25,line)
    c.setFillColor(HexColor('#a8b7cf'))
    c.setFont('Helvetica',9)
    c.drawString(48,45,'Synthetic interview fixture. Not a real company or financial statement.')
    c.drawRightString(w-48,45,f'Page {number}')
    c.showPage()


for name,amount,title in [('orion-finance-report.pdf',12,'Finance report'),('orion-investor-brief.pdf',18,'Investor brief')]:
    path=OUTPUT/name
    c=canvas.Canvas(str(path),pagesize=A4)
    c.setTitle('Orion - '+title+' (synthetic fixture)')
    page(c,1,title,[
        'Orion is a fictional company created for a document research demo.',
        'This fixture exercises PDF ingestion, page citations and source comparison.',
        'The two supplied reports intentionally disagree about one measurement.',
        'Read page 2 in both reports before drawing a conclusion.',
    ])
    page(c,2,'Fiscal year 2025 facts',[
        f"Orion's audited revenue for fiscal year 2025 was ${amount} million.",
        'The report covers the entire company, in US dollars.',
        "Orion stores each user's document passages in PostgreSQL.",
        'Row-level security restricts reads and writes to the authenticated owner.',
        'Neither report states a profit figure.',
    ])
    c.save()
    print(path)
