import typing

from sqlalchemy.orm import Session

from railgati.services.network import calculate_station_pair_route_diversity


def test_calculate_station_pair_route_diversity_success(
    db_session: Session, route_diversity_fixtures: typing.Any
) -> None:
    res = calculate_station_pair_route_diversity(db_session, "A", "D")

    assert res["from_station_code"] == "A"
    assert res["to_station_code"] == "D"
    assert res["distinct_path_count"] == 4

    paths = res["paths"]
    assert len(paths) == 4

    # Should be sorted by traversal_count DESC, path_length DESC
    assert paths[0]["station_sequence"] == ["A", "B", "C", "D"]
    assert paths[0]["path_length"] == 4
    assert paths[0]["traversal_count"] == 2

    # Path 1 is A->D
    assert paths[1]["station_sequence"] == ["A", "D"]
    assert paths[1]["path_length"] == 2
    assert paths[1]["traversal_count"] == 2

    # Path 2 is A->B->A->D
    assert paths[2]["station_sequence"] == ["A", "B", "A", "D"]
    assert paths[2]["path_length"] == 4
    assert paths[2]["traversal_count"] == 1

    # Path 3 is A->X->Y->D
    assert paths[3]["station_sequence"] == ["A", "X", "Y", "D"]
    assert paths[3]["path_length"] == 4
    assert paths[3]["traversal_count"] == 1
