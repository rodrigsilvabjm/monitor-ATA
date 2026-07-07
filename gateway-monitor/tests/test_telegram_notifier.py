from datetime import UTC, datetime

from app.services.telegram_notifier import (
    build_congestion_ended_message,
    build_congestion_started_message,
    format_duration_pt_br,
)


def test_build_congestion_started_message() -> None:
    message = build_congestion_started_message(
        datetime(2026, 7, 6, 12, 32, 41, tzinfo=UTC),
        "America/Sao_Paulo",
    )

    assert message == (
        "\U0001F6A8 Gateway Monitor\n\n"
        "Todas as linhas est\u00e3o ocupadas.\n\n"
        "Data:\n"
        "06/07/2026\n\n"
        "Hora:\n"
        "09:32:41"
    )


def test_build_congestion_ended_message() -> None:
    assert build_congestion_ended_message(192) == (
        "\u2705 Congestionamento encerrado\n\n"
        "Dura\u00e7\u00e3o\n\n"
        "3 minutos e 12 segundos"
    )


def test_format_duration_pt_br() -> None:
    assert format_duration_pt_br(0) == "0 segundos"
    assert format_duration_pt_br(1) == "1 segundo"
    assert format_duration_pt_br(61) == "1 minuto e 1 segundo"
    assert format_duration_pt_br(3661) == "1 hora e 1 minuto e 1 segundo"
