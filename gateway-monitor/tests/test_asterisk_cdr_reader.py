from datetime import datetime

from app.services.asterisk_cdr_reader import cdr_from_csv_row, cdr_from_mapping


def test_cdr_from_master_csv_row() -> None:
    row = [
        "",
        "2010",
        "08000400000",
        "from-internal",
        '"2010" <2010>',
        "SIP/2010-00000001",
        "SIP/3034-00000002",
        "Dial",
        "SIP/3034/08000400000",
        "2026-07-07 09:00:00",
        "2026-07-07 09:00:05",
        "2026-07-07 09:02:00",
        "120",
        "115",
        "ANSWERED",
        "3",
        "abc.1",
        "",
    ]

    record = cdr_from_csv_row(row)

    assert record is not None
    assert record.src == "2010"
    assert record.dst == "08000400000"
    assert record.billsec == 115
    assert record.disposition == "ANSWERED"


def test_cdr_from_mapping() -> None:
    record = cdr_from_mapping(
        {
            "src": "1132984779952",
            "dst": "3035",
            "channel": "SIP/3035-00000001",
            "start": datetime(2026, 7, 7, 10, 0, 0),
            "end": datetime(2026, 7, 7, 10, 1, 0),
            "duration": 60,
            "billsec": 55,
            "disposition": "ANSWERED",
            "uniqueid": "abc.2",
        }
    )

    assert record is not None
    assert record.dst == "3035"
    assert record.duration == 60
