from io import BytesIO

from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.models.gateway_event import GatewayEvent


def build_events_pdf(events: list[GatewayEvent]) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 48

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(48, y, "Gateway Monitor - Historico")
    y -= 32
    pdf.setFont("Helvetica", 9)

    for event in events:
        if y < 72:
            pdf.showPage()
            pdf.setFont("Helvetica", 9)
            y = height - 48
        line = (
            f"{event.created_at:%d/%m/%Y %H:%M:%S} | {event.event_type} | "
            f"Ocupadas: {event.busy_lines} | Livres: {event.idle_lines} | "
            f"Duracao: {event.duration}s"
        )
        pdf.drawString(48, y, line[:115])
        y -= 14
        pdf.drawString(64, y, event.message[:110])
        y -= 20

    pdf.save()
    return buffer.getvalue()


def build_events_excel(events: list[GatewayEvent]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Historico"
    sheet.append(
        [
            "ID",
            "Criado em",
            "Evento",
            "Ocupadas",
            "Livres",
            "Duracao",
            "Mensagem",
        ]
    )

    for event in events:
        sheet.append(
            [
                event.id,
                event.created_at.strftime("%d/%m/%Y %H:%M:%S"),
                event.event_type,
                event.busy_lines,
                event.idle_lines,
                event.duration,
                event.message,
            ]
        )

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
