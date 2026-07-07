import asyncio

from app.config import get_settings
from app.services.asterisk_ami import (
    AsteriskAmiMonitor,
    extract_extension,
    extract_fxo_line,
    extract_fxo_line_from_event,
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
    assert extract_fxo_line("SIP/3-00000001") is None
    assert extract_fxo_line("SIP/3035-00000001", {"3035": "2"}) == "2"
    assert extract_fxo_line("PJSIP/3037-00000001", {"3037": "4"}) == "4"
    assert extract_extension("PJSIP/201-00000001") == "201"


def test_extract_fxo_line_from_event_fields() -> None:
    mapping = {"3034": "1", "3035": "2", "3036": "3", "3037": "4"}

    assert extract_fxo_line_from_event({"Exten": "3035"}, mapping) == "2"
    assert extract_fxo_line_from_event({"Destination": "3037"}, mapping) == "4"
    assert (
        extract_fxo_line_from_event(
            {"Destination": "3036", "Channel": "SIP/3035-00000001"},
            mapping,
        )
        == "3"
    )


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
    assert monitor.active_fxo_line_count([1, 2, 3, 4]) == 1
    assert monitor.active_fxo_lines([1, 2, 3, 4]) == {2}


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


def test_ami_monitor_tracks_core_show_channels() -> None:
    async def scenario() -> AsteriskAmiMonitor:
        monitor = AsteriskAmiMonitor(get_settings())
        await monitor.process_event(
            {
                "Event": "CoreShowChannel",
                "Uniqueid": "core-1",
                "CallerIDNum": "1135984273389",
                "Exten": "s",
                "Channel": "DAHDI/2-1",
            }
        )
        return monitor

    monitor = asyncio.run(scenario())

    assert monitor.snapshot.simultaneous_calls == 1
    assert monitor.snapshot.active_calls[0].fxo_line == "2"
    assert monitor.active_fxo_line_count([1, 2, 3, 4]) == 1
    assert monitor.active_fxo_lines([1, 2, 3, 4]) == {2}


def test_ami_monitor_maps_sip_peer_to_fxo_line() -> None:
    async def scenario() -> AsteriskAmiMonitor:
        settings = get_settings().model_copy(
            update={"asterisk_fxo_sip_map": "3034:1,3035:2,3036:3,3037:4"}
        )
        monitor = AsteriskAmiMonitor(settings)
        await monitor.process_event(
            {
                "Event": "CoreShowChannel",
                "Uniqueid": "core-sip-1",
                "CallerIDNum": "1135984273389",
                "Exten": "s",
                "Channel": "SIP/3035-00000001",
            }
        )
        return monitor

    monitor = asyncio.run(scenario())

    assert monitor.snapshot.active_calls[0].fxo_line == "2"
    assert monitor.active_fxo_line_count([1, 2, 3, 4]) == 1
    assert monitor.active_fxo_lines([1, 2, 3, 4]) == {2}


def test_ami_monitor_maps_destination_peer_to_fxo_line() -> None:
    async def scenario() -> AsteriskAmiMonitor:
        settings = get_settings().model_copy(
            update={"asterisk_fxo_sip_map": "3034:1,3035:2,3036:3,3037:4"}
        )
        monitor = AsteriskAmiMonitor(settings)
        await monitor.process_event(
            {
                "Event": "CoreShowChannel",
                "Uniqueid": "core-destination-1",
                "CallerIDNum": "1135984273389",
                "Exten": "3035",
                "Channel": "SIP/2010-00000001",
            }
        )
        return monitor

    monitor = asyncio.run(scenario())

    assert monitor.snapshot.active_calls[0].fxo_line == "2"
    assert monitor.active_fxo_lines([1, 2, 3, 4]) == {2}


def test_ami_monitor_prefers_destination_peer_over_channel_peer() -> None:
    async def scenario() -> AsteriskAmiMonitor:
        settings = get_settings().model_copy(
            update={"asterisk_fxo_sip_map": "3034:1,3035:2,3036:3,3037:4"}
        )
        monitor = AsteriskAmiMonitor(settings)
        await monitor.process_event(
            {
                "Event": "CoreShowChannel",
                "Uniqueid": "core-destination-2",
                "CallerIDNum": "1135984273389",
                "Destination": "3036",
                "Channel": "SIP/3035-00000001",
            }
        )
        return monitor

    monitor = asyncio.run(scenario())

    assert monitor.snapshot.active_calls[0].fxo_line == "3"
    assert monitor.active_fxo_lines([1, 2, 3, 4]) == {3}


def test_ami_monitor_destination_peer_can_correct_existing_fxo_line() -> None:
    async def scenario() -> AsteriskAmiMonitor:
        settings = get_settings().model_copy(
            update={"asterisk_fxo_sip_map": "3034:1,3035:2,3036:3,3037:4"}
        )
        monitor = AsteriskAmiMonitor(settings)
        await monitor.process_event(
            {
                "Event": "Newchannel",
                "Uniqueid": "core-destination-3",
                "Channel": "SIP/3034-00000001",
            }
        )
        await monitor.process_event(
            {
                "Event": "CoreShowChannel",
                "Uniqueid": "core-destination-3",
                "CallerIDNum": "1135984273389",
                "Destination": "3037",
            }
        )
        return monitor

    monitor = asyncio.run(scenario())

    assert monitor.snapshot.active_calls[0].fxo_line == "4"
    assert monitor.active_fxo_lines([1, 2, 3, 4]) == {4}


def test_ami_monitor_merges_call_legs_by_linkedid() -> None:
    async def scenario() -> AsteriskAmiMonitor:
        settings = get_settings().model_copy(
            update={"asterisk_fxo_sip_map": "3034:1,3035:2,3036:3,3037:4"}
        )
        monitor = AsteriskAmiMonitor(settings)
        await monitor.process_event(
            {
                "Event": "CoreShowChannel",
                "Uniqueid": "leg-1",
                "Linkedid": "call-group-1",
                "CallerIDNum": "2010",
                "Destination": "08000400000",
            }
        )
        await monitor.process_event(
            {
                "Event": "CoreShowChannel",
                "Uniqueid": "leg-2",
                "Linkedid": "call-group-1",
                "CallerIDNum": "1135984273389",
                "Destination": "3037",
            }
        )
        return monitor

    monitor = asyncio.run(scenario())

    assert len(monitor.snapshot.active_calls) == 1
    assert monitor.snapshot.active_calls[0].fxo_line == "4"
    assert monitor.active_fxo_lines([1, 2, 3, 4]) == {4}


def test_ami_monitor_keeps_all_four_linked_fxo_lines() -> None:
    async def scenario() -> AsteriskAmiMonitor:
        settings = get_settings().model_copy(
            update={"asterisk_fxo_sip_map": "3034:1,3035:2,3036:3,3037:4"}
        )
        monitor = AsteriskAmiMonitor(settings)
        for line, sip_peer in enumerate(("3034", "3035", "3036", "3037"), start=1):
            await monitor.process_event(
                {
                    "Event": "CoreShowChannel",
                    "Uniqueid": f"leg-{line}-a",
                    "Linkedid": f"call-group-{line}",
                    "Destination": "08000400000",
                }
            )
            await monitor.process_event(
                {
                    "Event": "CoreShowChannel",
                    "Uniqueid": f"leg-{line}-b",
                    "Linkedid": f"call-group-{line}",
                    "Destination": sip_peer,
                }
            )
        return monitor

    monitor = asyncio.run(scenario())

    assert monitor.active_fxo_lines([1, 2, 3, 4]) == {1, 2, 3, 4}


def test_ami_monitor_infers_missing_line_from_unassigned_external_call() -> None:
    async def scenario() -> AsteriskAmiMonitor:
        settings = get_settings().model_copy(
            update={"asterisk_fxo_sip_map": "3034:1,3035:2,3036:3,3037:4"}
        )
        monitor = AsteriskAmiMonitor(settings)
        await monitor.process_event(
            {
                "Event": "CoreShowChannel",
                "Uniqueid": "external-without-fxo",
                "CallerIDNum": "1132984773794",
            }
        )
        for line, sip_peer in (("1", "3034"), ("2", "3035"), ("4", "3037")):
            await monitor.process_event(
                {
                    "Event": "CoreShowChannel",
                    "Uniqueid": f"line-{line}",
                    "CallerIDNum": "1132984923166",
                    "Destination": sip_peer,
                }
            )
        return monitor

    monitor = asyncio.run(scenario())

    assert monitor.active_fxo_lines([1, 2, 3, 4]) == {1, 2, 3, 4}
