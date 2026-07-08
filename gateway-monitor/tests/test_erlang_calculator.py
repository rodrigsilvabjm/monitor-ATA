from app.services.erlang_calculator import erlang_b, recommended_lines


def test_erlang_b() -> None:
    assert round(erlang_b(1.0, 4), 4) == 0.0154
    assert erlang_b(0, 4) == 0


def test_recommended_lines() -> None:
    assert recommended_lines(1.0, 0.05) == 4
    assert recommended_lines(3.0, 0.01) > 4
