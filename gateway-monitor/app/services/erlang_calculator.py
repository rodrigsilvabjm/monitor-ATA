def erlang_b(traffic_erlangs: float, lines: int) -> float:
    if lines <= 0:
        return 1.0
    if traffic_erlangs <= 0:
        return 0.0

    blocking = 1.0
    for line_count in range(1, lines + 1):
        blocking = (traffic_erlangs * blocking) / (
            line_count + traffic_erlangs * blocking
        )
    return blocking


def recommended_lines(
    traffic_erlangs: float,
    max_blocking_probability: float,
    max_lines: int = 120,
) -> int:
    for lines in range(1, max_lines + 1):
        if erlang_b(traffic_erlangs, lines) <= max_blocking_probability:
            return lines
    return max_lines


def recommendations_by_target(
    traffic_erlangs: float,
    targets: tuple[float, ...] = (0.05, 0.02, 0.01, 0.005),
) -> dict[str, int]:
    return {
        format_target(target): recommended_lines(traffic_erlangs, target)
        for target in targets
    }


def format_target(target: float) -> str:
    percent = target * 100
    if percent.is_integer():
        return f"{int(percent)}%"
    return f"{percent:.1f}%".replace(".", ",")
