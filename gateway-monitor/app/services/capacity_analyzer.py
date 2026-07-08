import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.services.asterisk_cdr_reader import CdrRecord
from app.services.erlang_calculator import erlang_b, recommendations_by_target

DISPOSITIONS = ("ANSWERED", "BUSY", "FAILED", "NO ANSWER", "CONGESTION")


@dataclass(frozen=True)
class CapacityRecommendation:
    status: str
    message: str
    recommended_lines: int


@dataclass(frozen=True)
class CapacityAnalysis:
    started_at: datetime
    ended_at: datetime
    line_count: int
    trunk_sips: list[str]
    total_calls: int
    inbound_calls: int
    outbound_calls: int
    answered_calls: int
    unanswered_calls: int
    disposition_counts: dict[str, int]
    average_duration_seconds: int
    total_billsec: int
    busy_hour_label: str
    busy_hour_calls: int
    busy_hour_erlangs: float
    average_occupancy_percent: float
    peak_concurrent_calls: int
    all_lines_busy_count: int
    all_lines_busy_seconds: int
    longest_all_lines_busy_seconds: int
    trunk_usage: list[dict]
    extension_usage: list[dict]
    calls_by_day: list[dict]
    calls_by_hour: list[dict]
    concurrency_points: list[dict]
    erlang_blocking_with_current_lines: float
    erlang_recommended_lines: dict[str, int]
    recommendation: CapacityRecommendation


def analyze_capacity(
    records: list[CdrRecord],
    trunk_sips: list[str],
    line_count: int,
    started_at: datetime,
    ended_at: datetime,
) -> CapacityAnalysis:
    relevant_records = [
        record for record in records if find_trunk_sip(record, trunk_sips)
    ]
    relevant_records.sort(key=lambda record: record.start)
    intervals = build_call_intervals(relevant_records, trunk_sips)
    total_billsec = sum(record.billsec for record in relevant_records)
    total_period_seconds = max(int((ended_at - started_at).total_seconds()), 1)
    average_occupancy = (total_billsec / (total_period_seconds * line_count)) * 100
    busy_hour_label, busy_hour_calls, busy_hour_erlangs = calculate_busy_hour(
        relevant_records,
        started_at,
        ended_at,
    )
    concurrency = calculate_concurrency(intervals, line_count)
    erlang_recommendations = recommendations_by_target(busy_hour_erlangs)
    blocking_current = erlang_b(busy_hour_erlangs, line_count)
    recommendation = build_recommendation(
        line_count=line_count,
        blocking_probability=blocking_current,
        recommended_lines_5_percent=erlang_recommendations["5%"],
        peak_concurrent_calls=concurrency["peak"],
        all_lines_busy_seconds=concurrency["all_lines_busy_seconds"],
    )

    return CapacityAnalysis(
        started_at=started_at,
        ended_at=ended_at,
        line_count=line_count,
        trunk_sips=trunk_sips,
        total_calls=len(relevant_records),
        inbound_calls=sum(1 for record in relevant_records if classify_direction(record, trunk_sips) == "inbound"),
        outbound_calls=sum(1 for record in relevant_records if classify_direction(record, trunk_sips) == "outbound"),
        answered_calls=sum(1 for record in relevant_records if record.disposition == "ANSWERED"),
        unanswered_calls=sum(1 for record in relevant_records if record.disposition != "ANSWERED"),
        disposition_counts=count_dispositions(relevant_records),
        average_duration_seconds=int(total_billsec / len(relevant_records)) if relevant_records else 0,
        total_billsec=total_billsec,
        busy_hour_label=busy_hour_label,
        busy_hour_calls=busy_hour_calls,
        busy_hour_erlangs=round(busy_hour_erlangs, 3),
        average_occupancy_percent=round(average_occupancy, 2),
        peak_concurrent_calls=concurrency["peak"],
        all_lines_busy_count=concurrency["all_lines_busy_count"],
        all_lines_busy_seconds=concurrency["all_lines_busy_seconds"],
        longest_all_lines_busy_seconds=concurrency["longest_all_lines_busy_seconds"],
        trunk_usage=build_trunk_usage(relevant_records, trunk_sips),
        extension_usage=build_extension_usage(relevant_records, trunk_sips),
        calls_by_day=build_calls_by_day(relevant_records),
        calls_by_hour=build_calls_by_hour(relevant_records),
        concurrency_points=concurrency["points"],
        erlang_blocking_with_current_lines=round(blocking_current, 4),
        erlang_recommended_lines=erlang_recommendations,
        recommendation=recommendation,
    )


def find_trunk_sip(record: CdrRecord, trunk_sips: list[str]) -> str | None:
    searchable = " ".join(
        [
            record.src,
            record.dst,
            record.channel,
            record.dstchannel,
            record.lastdata,
            record.userfield,
        ]
    )
    for sip in trunk_sips:
        if re.search(rf"(?<!\d){re.escape(sip)}(?!\d)", searchable):
            return sip
    return None


def classify_direction(record: CdrRecord, trunk_sips: list[str]) -> str:
    if record.dst in trunk_sips:
        return "inbound"
    if find_sip_in_text(record.channel, trunk_sips) and is_external_number(record.src):
        return "inbound"
    return "outbound"


def find_sip_in_text(value: str, trunk_sips: list[str]) -> str | None:
    for sip in trunk_sips:
        if re.search(rf"(?:SIP|PJSIP)/{re.escape(sip)}(?:[-/]|$)", value, re.IGNORECASE):
            return sip
    return None


def is_external_number(value: str) -> bool:
    digits = re.sub(r"\D", "", value or "")
    return len(digits) >= 8


def count_dispositions(records: list[CdrRecord]) -> dict[str, int]:
    counter = Counter(record.disposition or "UNKNOWN" for record in records)
    return {disposition: counter.get(disposition, 0) for disposition in DISPOSITIONS}


def build_call_intervals(
    records: list[CdrRecord],
    trunk_sips: list[str],
) -> list[tuple[datetime, datetime, str | None]]:
    intervals = []
    for record in records:
        end = record.end if record.end > record.start else record.start + timedelta(seconds=max(record.duration, 1))
        intervals.append((record.start, end, find_trunk_sip(record, trunk_sips)))
    return intervals


def calculate_busy_hour(
    records: list[CdrRecord],
    started_at: datetime,
    ended_at: datetime,
) -> tuple[str, int, float]:
    buckets = build_hour_buckets(started_at, ended_at)
    calls_by_hour: dict[datetime, int] = {bucket: 0 for bucket in buckets}
    billsec_by_hour: dict[datetime, int] = {bucket: 0 for bucket in buckets}

    for record in records:
        bucket = record.start.replace(minute=0, second=0, microsecond=0)
        if bucket in calls_by_hour:
            calls_by_hour[bucket] += 1
            billsec_by_hour[bucket] += seconds_overlapping_hour(record, bucket)

    if not calls_by_hour:
        return "--", 0, 0.0

    busy_hour = max(calls_by_hour, key=lambda hour: (calls_by_hour[hour], billsec_by_hour[hour]))
    return (
        busy_hour.strftime("%d/%m/%Y %H:00"),
        calls_by_hour[busy_hour],
        billsec_by_hour[busy_hour] / 3600,
    )


def build_hour_buckets(started_at: datetime, ended_at: datetime) -> list[datetime]:
    current = started_at.replace(minute=0, second=0, microsecond=0)
    buckets = []
    while current <= ended_at:
        buckets.append(current)
        current += timedelta(hours=1)
    return buckets


def seconds_overlapping_hour(record: CdrRecord, bucket: datetime) -> int:
    hour_end = bucket + timedelta(hours=1)
    start = max(record.start, bucket)
    end = min(record.end, hour_end)
    return max(int((end - start).total_seconds()), 0)


def calculate_concurrency(
    intervals: list[tuple[datetime, datetime, str | None]],
    line_count: int,
) -> dict:
    events = []
    for start, end, _trunk in intervals:
        events.append((start, 1))
        events.append((end, -1))
    events.sort(key=lambda item: (item[0], item[1]))

    active = 0
    peak = 0
    all_lines_busy_count = 0
    all_lines_busy_seconds = 0
    longest_all_lines_busy_seconds = 0
    all_lines_busy_started_at: datetime | None = None
    previous_at: datetime | None = None
    points: list[dict] = []

    for event_time, delta in events:
        if previous_at and active >= line_count:
            all_lines_busy_seconds += max(int((event_time - previous_at).total_seconds()), 0)

        was_all_busy = active >= line_count
        active += delta
        active = max(active, 0)
        peak = max(peak, active)
        is_all_busy = active >= line_count

        if not was_all_busy and is_all_busy:
            all_lines_busy_count += 1
            all_lines_busy_started_at = event_time
        if was_all_busy and not is_all_busy and all_lines_busy_started_at:
            longest_all_lines_busy_seconds = max(
                longest_all_lines_busy_seconds,
                int((event_time - all_lines_busy_started_at).total_seconds()),
            )
            all_lines_busy_started_at = None

        points.append({"time": event_time.isoformat(), "active": active})
        previous_at = event_time

    return {
        "peak": peak,
        "all_lines_busy_count": all_lines_busy_count,
        "all_lines_busy_seconds": all_lines_busy_seconds,
        "longest_all_lines_busy_seconds": longest_all_lines_busy_seconds,
        "points": points[-240:],
    }


def build_trunk_usage(records: list[CdrRecord], trunk_sips: list[str]) -> list[dict]:
    usage: dict[str, dict] = {
        sip: {"trunk": sip, "calls": 0, "billsec": 0} for sip in trunk_sips
    }
    for record in records:
        trunk = find_trunk_sip(record, trunk_sips)
        if not trunk:
            continue
        usage[trunk]["calls"] += 1
        usage[trunk]["billsec"] += record.billsec
    return sorted(usage.values(), key=lambda item: (-item["calls"], item["trunk"]))


def build_extension_usage(records: list[CdrRecord], trunk_sips: list[str]) -> list[dict]:
    counter: dict[str, dict] = defaultdict(lambda: {"extension": "", "calls": 0, "billsec": 0})
    for record in records:
        extension = find_extension(record, trunk_sips)
        if not extension:
            continue
        counter[extension]["extension"] = extension
        counter[extension]["calls"] += 1
        counter[extension]["billsec"] += record.billsec
    return sorted(counter.values(), key=lambda item: (-item["calls"], item["extension"]))[:15]


def find_extension(record: CdrRecord, trunk_sips: list[str]) -> str | None:
    for value in (record.src, record.dst):
        digits = re.sub(r"\D", "", value or "")
        if 2 <= len(digits) <= 6 and digits not in trunk_sips:
            return digits
    return None


def build_calls_by_day(records: list[CdrRecord]) -> list[dict]:
    by_day: dict[str, Counter] = defaultdict(Counter)
    for record in records:
        key = record.start.strftime("%d/%m/%Y")
        by_day[key]["total"] += 1
        by_day[key][classify_simple_direction(record)] += 1
        by_day[key][record.disposition or "UNKNOWN"] += 1
    return [
        {
            "day": day,
            "total": values["total"],
            "inbound": values["inbound"],
            "outbound": values["outbound"],
            "answered": values["ANSWERED"],
            "unanswered": values["total"] - values["ANSWERED"],
        }
        for day, values in sorted(by_day.items())
    ]


def classify_simple_direction(record: CdrRecord) -> str:
    return "inbound" if is_external_number(record.src) else "outbound"


def build_calls_by_hour(records: list[CdrRecord]) -> list[dict]:
    by_hour: dict[str, int] = defaultdict(int)
    for record in records:
        by_hour[record.start.strftime("%H:00")] += 1
    return [{"hour": hour, "calls": calls} for hour, calls in sorted(by_hour.items())]


def build_recommendation(
    line_count: int,
    blocking_probability: float,
    recommended_lines_5_percent: int,
    peak_concurrent_calls: int,
    all_lines_busy_seconds: int,
) -> CapacityRecommendation:
    recommended_lines = max(line_count, recommended_lines_5_percent, peak_concurrent_calls)
    if blocking_probability <= 0.02 and all_lines_busy_seconds == 0:
        return CapacityRecommendation(
            status="Capacidade Adequada",
            message=f"Recomendação de manter as {line_count} linhas.",
            recommended_lines=line_count,
        )
    if blocking_probability <= 0.05 and all_lines_busy_seconds < 300:
        return CapacityRecommendation(
            status="Capacidade em Atenção",
            message=(
                f"Manter {line_count} linhas por enquanto, mas acompanhar a hora de maior movimento."
            ),
            recommended_lines=max(line_count, recommended_lines),
        )
    return CapacityRecommendation(
        status="Capacidade Crítica",
        message=f"Recomendação de ampliar para {recommended_lines} linhas.",
        recommended_lines=recommended_lines,
    )
