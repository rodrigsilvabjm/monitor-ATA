from datetime import datetime

from app.services.asterisk_cdr_reader import CdrRecord
from app.services.capacity_analyzer import analyze_capacity, find_trunk_sip


def _cdr(
    src: str,
    dst: str,
    channel: str,
    dstchannel: str,
    start: datetime,
    end: datetime,
    disposition: str = "ANSWERED",
) -> CdrRecord:
    return CdrRecord(
        src=src,
        dst=dst,
        channel=channel,
        dstchannel=dstchannel,
        lastapp="Dial",
        lastdata=dstchannel,
        start=start,
        answer=start,
        end=end,
        duration=int((end - start).total_seconds()),
        billsec=int((end - start).total_seconds()),
        disposition=disposition,
        uniqueid=f"{src}-{dst}-{start.timestamp()}",
    )


def test_find_trunk_sip_only_monitored_sips() -> None:
    record = _cdr(
        "2010",
        "0800",
        "SIP/2010-1",
        "SIP/3034-2",
        datetime(2026, 7, 7, 9, 0, 0),
        datetime(2026, 7, 7, 9, 1, 0),
    )

    assert find_trunk_sip(record, ["3034", "3035", "3036", "3037"]) == "3034"
    assert find_trunk_sip(record, ["9999"]) is None


def test_analyze_capacity() -> None:
    started_at = datetime(2026, 7, 7, 9, 0, 0)
    ended_at = datetime(2026, 7, 7, 11, 0, 0)
    records = [
        _cdr("2010", "0800", "SIP/2010-1", "SIP/3034-1", started_at, datetime(2026, 7, 7, 9, 30, 0)),
        _cdr("2011", "0800", "SIP/2011-1", "SIP/3035-1", started_at, datetime(2026, 7, 7, 9, 20, 0)),
        _cdr("2012", "0800", "SIP/2012-1", "SIP/3036-1", started_at, datetime(2026, 7, 7, 9, 10, 0)),
        _cdr("2013", "0800", "SIP/2013-1", "SIP/3037-1", started_at, datetime(2026, 7, 7, 9, 5, 0)),
        _cdr("2014", "0800", "SIP/2014-1", "SIP/9999-1", started_at, datetime(2026, 7, 7, 9, 5, 0)),
        _cdr("1132984779952", "3035", "SIP/3035-1", "", datetime(2026, 7, 7, 10, 0, 0), datetime(2026, 7, 7, 10, 3, 0), "NO ANSWER"),
    ]

    analysis = analyze_capacity(
        records=records,
        trunk_sips=["3034", "3035", "3036", "3037"],
        line_count=4,
        started_at=started_at,
        ended_at=ended_at,
    )

    assert analysis.total_calls == 5
    assert analysis.outbound_calls == 4
    assert analysis.inbound_calls == 1
    assert analysis.disposition_counts["NO ANSWER"] == 1
    assert analysis.peak_concurrent_calls == 4
    assert analysis.all_lines_busy_count == 1
    assert analysis.all_lines_busy_seconds == 300
    assert analysis.trunk_usage[0]["trunk"] == "3035"
