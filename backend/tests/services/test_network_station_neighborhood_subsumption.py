import pytest
from railgati.services.network import calculate_station_neighborhood_subsumption
from railgati.models.train import Train, TrainStopObservation, TrainObservation
from railgati.models.station import Station, StationObservation
from railgati.models.provenance import DatasetSnapshot, DataSource

@pytest.fixture
def mock_subsumption_data(db_session):
    source = DataSource(name="SUB_SRC", url="http://test", publisher="Test", license="Test")
    db_session.add(source)
    db_session.commit()
    
    snap = DatasetSnapshot(source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.commit()
    
    # Active snapshot requires a TrainObservation to be returned by get_active_timetable_snapshot_id
    
    def create_station(code):
        s = Station(code=code)
        db_session.add(s)
        db_session.commit()
        db_session.add(StationObservation(snapshot_id=snap.id, station_id=s.id, name=code))
        db_session.commit()
        return s

    def add_train(number, seq):
        t = Train(number=number)
        db_session.add(t)
        db_session.commit()
        
        db_session.add(TrainObservation(snapshot_id=snap.id, train_id=t.id, name=number))
        
        for i, code in enumerate(seq, 1):
            s = db_session.query(Station).filter_by(code=code).first()
            if not s:
                s = create_station(code)
            db_session.add(TrainStopObservation(
                snapshot_id=snap.id, train_id=t.id, station_id=s.id, stop_sequence=i
            ))
        db_session.commit()

    # Case 1: Strict subsumption
    # S has {H, A}, H has {S, A, B} -> H subsumes S
    add_train("T1_1", ["A1", "S1", "H1", "B1"])
    add_train("T1_2", ["H1", "A1"])
    
    # Case 2: No subsumption due to missing neighbor
    # S has {H, A}, H has {S, B}
    add_train("T2", ["A2", "S2", "H2", "B2"])
    
    # Case 3: No subsumption due to equal reduced neighborhoods
    # S has {H, A}, H has {S, A}
    add_train("T3", ["S3", "A3", "H3", "S3"])
    
    # Case 4: Leaf case
    add_train("T4", ["S4", "H4"])
    
    # Case 5: Proper chain A - B - C
    add_train("T5", ["A5", "B5", "C5"])
    
    # Case 6: Repeated edges
    add_train("T6_1", ["A6", "S6", "H6", "B6"])
    add_train("T6_2", ["A6", "S6", "H6", "B6"])
    add_train("T6_3", ["H6", "A6"])
    
    # Case 7: Snapshot isolation
    snap2 = DatasetSnapshot(source_id=source.id)
    db_session.add(snap2)
    db_session.commit()
    t7 = Train(number="T7")
    db_session.add(t7)
    db_session.commit()
    # In snap2, H1 has neighbor Z1. But in snap1 it doesn't.
    s_z1 = create_station("Z1")
    s_h1 = db_session.query(Station).filter_by(code="H1").first()
    db_session.add(TrainStopObservation(snapshot_id=snap2.id, train_id=t7.id, station_id=s_h1.id, stop_sequence=1))
    db_session.add(TrainStopObservation(snapshot_id=snap2.id, train_id=t7.id, station_id=s_z1.id, stop_sequence=2))
    db_session.commit()
    
    # Note: snapshot 1 is still the active one returned by the logic because it has the most observations or we can force it.
    # We added many trains to snap1 so it will be the active one.

def test_strict_subsumption(db_session, mock_subsumption_data):
    res = calculate_station_neighborhood_subsumption(db_session, "S1")
    assert res["total_neighbors"] == 2
    assert len(res["subsuming_neighbors"]) == 1
    assert res["subsuming_neighbors"][0]["station_code"] == "H1"
    assert res["subsuming_neighbors"][0]["neighbor_degree"] == 3

def test_no_subsumption_missing_neighbor(db_session, mock_subsumption_data):
    res = calculate_station_neighborhood_subsumption(db_session, "S2")
    assert res["total_neighbors"] == 2
    assert len(res["subsuming_neighbors"]) == 0

def test_no_subsumption_equal_neighborhoods(db_session, mock_subsumption_data):
    res = calculate_station_neighborhood_subsumption(db_session, "S3")
    assert res["total_neighbors"] == 2
    assert len(res["subsuming_neighbors"]) == 0
    
    res_h = calculate_station_neighborhood_subsumption(db_session, "H3")
    assert len(res_h["subsuming_neighbors"]) == 0

def test_leaf_case(db_session, mock_subsumption_data):
    res = calculate_station_neighborhood_subsumption(db_session, "S4")
    assert res["total_neighbors"] == 1
    assert len(res["subsuming_neighbors"]) == 0

def test_proper_chain(db_session, mock_subsumption_data):
    res_a = calculate_station_neighborhood_subsumption(db_session, "A5")
    assert len(res_a["subsuming_neighbors"]) == 1
    assert res_a["subsuming_neighbors"][0]["station_code"] == "B5"
    
    res_c = calculate_station_neighborhood_subsumption(db_session, "C5")
    assert len(res_c["subsuming_neighbors"]) == 1
    assert res_c["subsuming_neighbors"][0]["station_code"] == "B5"

def test_repeated_edges(db_session, mock_subsumption_data):
    res = calculate_station_neighborhood_subsumption(db_session, "S6")
    assert res["total_neighbors"] == 2
    assert len(res["subsuming_neighbors"]) == 1
    assert res["subsuming_neighbors"][0]["station_code"] == "H6"

def test_snapshot_isolation(db_session, mock_subsumption_data):
    # Z1 is only in snap2, so it shouldn't affect H1's degree in snap1
    res = calculate_station_neighborhood_subsumption(db_session, "S1")
    assert res["subsuming_neighbors"][0]["neighbor_degree"] == 3
