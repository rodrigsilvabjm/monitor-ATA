from datetime import datetime

from app.config import get_settings
from app.services.asterisk_cdr_reader import (
    AsteriskCdrReader,
    cdr_from_csv_line,
    cdr_from_csv_row,
    cdr_from_mapping,
    iter_file_lines_reverse,
)


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


def test_cdr_from_csv_line() -> None:
    record = cdr_from_csv_line(
        '"","3035","2","from-pstn","""3035"" <3035>",'
        '"SIP/3035-0000063a","","Queue","cobranca,c",'
        '"2026-07-08 00:13:16","2026-07-08 00:13:16",'
        '"2026-07-08 00:14:38",82,82,"ANSWERED","DOCUMENTATION",'
        '"1783469596.2321",""'
    )

    assert record is not None
    assert record.src == "3035"
    assert record.billsec == 82


def test_cdr_from_csv_line_rejects_malformed_numeric_fields() -> None:
    record = cdr_from_csv_line(
        '"","3035","2","from-pstn","""3035"" <3035>",'
        '"SIP/3035-0000063a","","Queue","cobranca,c",'
        '"2026-07-08 00:13:16","2026-07-08 00:13:16",'
        '"2026-07-08 00:14:38",82,"from-fxo-gw","ANSWERED",'
        '"DOCUMENTATION","1783469596.2321",""'
    )

    assert record is None


def test_iter_file_lines_reverse(tmp_path) -> None:
    cdr_path = tmp_path / "Master.csv"
    cdr_path.write_text("linha 1\nlinha 2\nlinha 3\n", encoding="utf-8")

    assert list(iter_file_lines_reverse(cdr_path)) == ["linha 3", "linha 2", "linha 1"]


def test_csv_reader_stops_at_requested_window(tmp_path) -> None:
    cdr_path = tmp_path / "Master.csv"
    cdr_path.write_text(
        "\n".join(
            [
                '"","2010","0800","from-internal","""2010"" <2010>",'
                '"SIP/2010-1","SIP/3034-1","Dial","SIP/3034/0800",'
                '"2026-07-05 09:00:00","2026-07-05 09:00:02",'
                '"2026-07-05 09:01:00",60,58,"ANSWERED","DOCUMENTATION","old",""',
                '"","2010","0800","from-internal","""2010"" <2010>",'
                '"SIP/2010-2","SIP/3035-2","Dial","SIP/3035/0800",'
                '"2026-07-08 10:00:00","2026-07-08 10:00:02",'
                '"2026-07-08 10:01:00",60,58,"ANSWERED","DOCUMENTATION","new",""',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    settings = get_settings().model_copy(
        update={
            "asterisk_cdr_source": "csv",
            "asterisk_cdr_csv_path": cdr_path,
        }
    )

    records = AsteriskCdrReader(settings).read_records(
        datetime(2026, 7, 8, 0, 0, 0),
        datetime(2026, 7, 8, 23, 59, 59),
    )

    assert [record.uniqueid for record in records] == ["new"]
