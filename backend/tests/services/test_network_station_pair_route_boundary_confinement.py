import typing

from sqlalchemy.orm import Session

from railgati.services.network import calculate_station_pair_route_boundary_confinement


def test_calculate_station_pair_route_boundary_confinement_success(
    db_session: Session, route_diversity_fixtures: typing.Any
) -> None:
    res = calculate_station_pair_route_boundary_confinement(db_session, "A", "D")

    assert res["from_station_code"] == "A"
    assert res["to_station_code"] == "D"
    assert res["total_traversal_count"] == 6

    assert res["strictly_bounded_count"] == 5
    assert res["destination_bounded_count"] == 1
    assert res["origin_bounded_count"] == 0
    assert res["unbounded_embedded_count"] == 0

    assert (
        res["strictly_bounded_count"]
        + res["origin_bounded_count"]
        + res["destination_bounded_count"]
        + res["unbounded_embedded_count"]
        == res["total_traversal_count"]
    )


def test_calculate_station_pair_route_boundary_confinement_empty(
    db_session: Session, route_diversity_fixtures: typing.Any
) -> None:
    res = calculate_station_pair_route_boundary_confinement(db_session, "D", "A")
    assert res["total_traversal_count"] == 0
    assert res["strictly_bounded_count"] == 0
    assert res["origin_bounded_count"] == 0
    assert res["destination_bounded_count"] == 0
    assert res["unbounded_embedded_count"] == 0


def test_calculate_station_pair_route_boundary_confinement_embedded(
    db_session: Session, route_diversity_fixtures: typing.Any
) -> None:
    res = calculate_station_pair_route_boundary_confinement(db_session, "B", "C")
    # T1: A->B->C->D. B is 2, C is 3. Min=1, Max=4 -> UNBOUNDED_EMBEDDED
    # T2: A->B->C->D. B is 2, C is 3. Min=1, Max=4 -> UNBOUNDED_EMBEDDED
    assert res["total_traversal_count"] == 2
    assert res["unbounded_embedded_count"] == 2
    assert res["strictly_bounded_count"] == 0
    assert res["origin_bounded_count"] == 0
    assert res["destination_bounded_count"] == 0
