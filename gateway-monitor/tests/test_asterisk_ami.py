import asyncio

from app.config import get_settings
from app.services.asterisk_ami import (
    AsteriskAmiMonitor,
    extract_extension,
    extract_fxo_line,
    parse_ami_message,
)


def test_parse_ami_message() -> None:
    message = parse_ami_message(
        [
            "Event: Newchannel",
            "Uniqueid: 123.45",
            "CallerIDNum: 5511999999999",
        ]
    )

    assert message == {
        "Event": "Newchannel",
        "Uniqueid": "123.45",
        "CallerIDNum": "5511999999999",
    }


def test_extract_channel_metadata() -> None:
    assert extract_fxo_line("DAHDI/7-1") == "7"
    assert extract_fxo_line("SIP/3-00000001") == "3"
    assert extract_extension("PJSIP/201-00000001") == "201"


async def _process_call_flow() -> AsteriskAmiMonitor:
    monitor = AsteriskAmiMonitor(get_settings())
    await monitor.process_event(
        {
            "Event": "Newchannel",
            "Uniqueid": "call-1",
            "CallerIDNum": "1001",
            "Exten": "0800123456",
            "Channel": "DAHDI/2-1",
        }
    )
    await monitor.process_event(
        {
            "Event": "BridgeEnter",
            "Uniqueid": "call-1",
            "ConnectedLineNum": "200",
        }
    )
    return monitor


def test_ami_monitor_tracks_active_call() -> None:
    monitor = asyncio.run(_process_call_flow())
    snapshot = monitor.snapshot

    assert snapshot.connected is True
    assert snapshot.simultaneous_calls == 1
    assert snapshot.active_calls[0].source_number == "1001"
    assert snapshot.active_calls[0].destination_number == "0800123456"
    assert snapshot.active_calls[0].answered_extension == "200"
    assert snapshot.active_calls[0].fxo_line == "2"


def test_ami_monitor_finishes_call() -> None:
    async def scenario() -> AsteriskAmiMonitor:
        monitor = await _process_call_flow()
        await monitor.process_event(
            {
                "Event": "Hangup",
                "Uniqueid": "call-1",
                "Duration": "42",
                "Cause-txt": "Normal Clearing",
            }
        )
        return monitor

    monitor = asyncio.run(scenario())

    assert monitor.snapshot.simultaneous_calls == 0
    assert monitor.snapshot.average_duration_seconds == 42
