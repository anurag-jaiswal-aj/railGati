import pytest
from sqlalchemy import text

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_station_reachability_expansion


@pytest.fixture
def expansion_fixtures(db_session):
    db_session.execute(text("DELETE FROM train_stop_observations"))
    db_session.execute(text("DELETE FROM station_observations"))
    db_session.execute(text("DELETE FROM train_observations"))
    db_session.execute(text("DELETE FROM trains"))
    db_session.execute(text("DELETE FROM stations"))
    db_session.execute(text("DELETE FROM dataset_snapshots"))
    db_session.execute(text("DELETE FROM data_sources"))
    db_session.commit()

    source = DataSource(
        name="Test Source 35", publisher="Test", url="http://test.com", license="Test"
    )
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    station_snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add_all([snap, station_snap])
    db_session.commit()

    snap_id = snap.id
    station_snap_id = station_snap.id

    def create_station(code):
        st = Station(code=code)
        db_session.add(st)
        db_session.commit()
        db_session.refresh(st)
        obs = StationObservation(
            station_id=st.id,
            snapshot_id=station_snap_id,
            name=f"Stn {code}",
            latitude=0.0,
            longitude=0.0,
        )
        db_session.add(obs)
        db_session.commit()
        return st

    stations = {
        c: create_station(c)
        for c in [
            "S1",
            "S2",
            "S3",
            "S4",
            "S5",
            "S6",
            "S7",
            "S8",
            "S9",
            "S10",
            "S11",
            "S12",
            "S13",
            "S14",
        ]
    }

    t_id_counter = [1]

    def create_train(route):
        tr = Train(number=f"T{t_id_counter[0]}")
        db_session.add(tr)
        db_session.commit()
        db_session.refresh(tr)
        t_id_counter[0] += 1

        db_session.add(
            TrainObservation(snapshot_id=snap_id, train_id=tr.id, name=tr.number, type="EXP")
        )
        for idx, s_code in enumerate(route):
            db_session.add(
                TrainStopObservation(
                    snapshot_id=snap_id,
                    train_id=tr.id,
                    station_id=stations[s_code].id,
                    stop_sequence=idx + 1,
                )
            )
        db_session.commit()

    # S1 linear
    create_train(["S1", "S2", "S3"])

    # S4 branching
    create_train(["S4", "S5", "S7"])
    create_train(["S4", "S6", "S8"])

    # S10 loop
    create_train(["S10", "S11", "S10"])

    # S12 internal overlap
    create_train(["S12", "S13", "S14"])
    create_train(["S12", "S14"])

    return {"snapshot_id": snap_id, "stations": stations}


def test_linear_expansion(db_session, expansion_fixtures):
    res = calculate_station_reachability_expansion(
        db_session, expansion_fixtures["snapshot_id"], "S1"
    )
    assert res["n1_count"] == 1
    assert res["n2_count"] == 1
    assert res["expansion_ratio"] == 1.0


def test_branching_expansion(db_session, expansion_fixtures):
    res = calculate_station_reachability_expansion(
        db_session, expansion_fixtures["snapshot_id"], "S4"
    )
    assert res["n1_count"] == 2
    assert res["n2_count"] == 2
    assert res["expansion_ratio"] == 1.0


def test_terminal_station_raises(db_session, expansion_fixtures):
    import pytest

    with pytest.raises(ValueError, match="n1_count == 0"):
        calculate_station_reachability_expansion(
            db_session, expansion_fixtures["snapshot_id"], "S9"
        )


def test_loop_exclusion(db_session, expansion_fixtures):
    res = calculate_station_reachability_expansion(
        db_session, expansion_fixtures["snapshot_id"], "S10"
    )
    assert res["n1_count"] == 1
    assert res["n2_count"] == 0
    assert res["expansion_ratio"] == 0.0


def test_n1_exclusion_from_n2(db_session, expansion_fixtures):
    res = calculate_station_reachability_expansion(
        db_session, expansion_fixtures["snapshot_id"], "S12"
    )
    assert res["n1_count"] == 2
    assert res["n2_count"] == 0
    assert res["expansion_ratio"] == 0.0


def test_unknown_station(db_session, expansion_fixtures):
    import pytest

    with pytest.raises(ValueError, match="not found"):
        calculate_station_reachability_expansion(
            db_session, expansion_fixtures["snapshot_id"], "UNKNOWN"
        )
