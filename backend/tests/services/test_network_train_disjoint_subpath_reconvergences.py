import pytest
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_train_sequence_disjoint_subpath_reconvergences

@pytest.fixture
def mock_disjoint_reconvergences_data(db_session):
    source = DataSource(name="Phase57Source", publisher="test", url="test", license="test")
    db_session.add(source)
    db_session.commit()
    
    snap = DatasetSnapshot(
        source_id=source.id,
        status="ACTIVE"
    )
    db_session.add(snap)
    db_session.commit()

    # Stations
    s_a = Station(code="STN_A")
    s_b = Station(code="STN_B")
    s_c = Station(code="STN_C")
    s_x = Station(code="STN_X")
    s_y = Station(code="STN_Y")
    s_z = Station(code="STN_Z")
    s_w = Station(code="STN_W")

    db_session.add_all([s_a, s_b, s_c, s_x, s_y, s_z, s_w])
    db_session.commit()

    # Target Train: A -> X -> Y -> B
    t_target = Train(number="TARGET")
    db_session.add(t_target)
    db_session.commit()

    o_target = TrainObservation(snapshot_id=snap.id, train_id=t_target.id, name="Target")
    db_session.add(o_target)
    db_session.commit()

    obs = [
        TrainStopObservation(snapshot_id=snap.id, train_id=t_target.id, station_id=s_a.id, stop_sequence=1),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_target.id, station_id=s_x.id, stop_sequence=2),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_target.id, station_id=s_y.id, stop_sequence=3),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_target.id, station_id=s_b.id, stop_sequence=4)
    ]

    # Candidate 1 (Disjoint): A -> Z -> W -> B (qualifies)
    t_cand1 = Train(number="CAND1")
    db_session.add(t_cand1)
    db_session.commit()
    o_cand1 = TrainObservation(snapshot_id=snap.id, train_id=t_cand1.id, name="CAND1")
    db_session.add(o_cand1)
    db_session.commit()
    obs.extend([
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cand1.id, station_id=s_a.id, stop_sequence=1),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cand1.id, station_id=s_z.id, stop_sequence=2),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cand1.id, station_id=s_w.id, stop_sequence=3),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cand1.id, station_id=s_b.id, stop_sequence=4)
    ])

    # Candidate 2 (Shared interior): A -> X -> Z -> B (does not qualify because shares X)
    t_cand2 = Train(number="CAND2")
    db_session.add(t_cand2)
    db_session.commit()
    o_cand2 = TrainObservation(snapshot_id=snap.id, train_id=t_cand2.id, name="CAND2")
    db_session.add(o_cand2)
    db_session.commit()
    obs.extend([
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cand2.id, station_id=s_a.id, stop_sequence=1),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cand2.id, station_id=s_x.id, stop_sequence=2),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cand2.id, station_id=s_z.id, stop_sequence=3),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cand2.id, station_id=s_b.id, stop_sequence=4)
    ])

    # Candidate 3 (Different order): B -> Z -> A (does not qualify because sequence(A) > sequence(B))
    t_cand3 = Train(number="CAND3")
    db_session.add(t_cand3)
    db_session.commit()
    o_cand3 = TrainObservation(snapshot_id=snap.id, train_id=t_cand3.id, name="CAND3")
    db_session.add(o_cand3)
    db_session.commit()
    obs.extend([
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cand3.id, station_id=s_b.id, stop_sequence=1),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cand3.id, station_id=s_z.id, stop_sequence=2),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cand3.id, station_id=s_a.id, stop_sequence=3)
    ])

    # Candidate 4 (Direct path): A -> B (does not qualify because 0 interior stops)
    t_cand4 = Train(number="CAND4")
    db_session.add(t_cand4)
    db_session.commit()
    o_cand4 = TrainObservation(snapshot_id=snap.id, train_id=t_cand4.id, name="CAND4")
    db_session.add(o_cand4)
    db_session.commit()
    obs.extend([
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cand4.id, station_id=s_a.id, stop_sequence=1),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cand4.id, station_id=s_b.id, stop_sequence=2)
    ])

    # Target 2 (Cyclic): C_A -> C_X -> C_B -> C_A -> C_Y -> C_B
    c_a = Station(code="C_A")
    c_b = Station(code="C_B")
    c_x = Station(code="C_X")
    c_y = Station(code="C_Y")
    c_z = Station(code="C_Z")
    db_session.add_all([c_a, c_b, c_x, c_y, c_z])
    db_session.commit()

    t_cyclic = Train(number="CYCLIC")
    db_session.add(t_cyclic)
    db_session.commit()
    o_cyclic = TrainObservation(snapshot_id=snap.id, train_id=t_cyclic.id, name="Cyclic")
    db_session.add(o_cyclic)
    db_session.commit()
    obs.extend([
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cyclic.id, station_id=c_a.id, stop_sequence=1),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cyclic.id, station_id=c_x.id, stop_sequence=2),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cyclic.id, station_id=c_b.id, stop_sequence=3),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cyclic.id, station_id=c_a.id, stop_sequence=4),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cyclic.id, station_id=c_y.id, stop_sequence=5),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cyclic.id, station_id=c_b.id, stop_sequence=6)
    ])

    # For cyclic target, Candidate 5: C_A -> C_Z -> C_B
    t_cand5 = Train(number="CAND5")
    db_session.add(t_cand5)
    db_session.commit()
    o_cand5 = TrainObservation(snapshot_id=snap.id, train_id=t_cand5.id, name="CAND5")
    db_session.add(o_cand5)
    db_session.commit()
    obs.extend([
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cand5.id, station_id=c_a.id, stop_sequence=1),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cand5.id, station_id=c_z.id, stop_sequence=2),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cand5.id, station_id=c_b.id, stop_sequence=3)
    ])

    # Target 3 (Repeated interior station): R_A -> R_Z -> R_Z -> R_B
    r_a = Station(code="R_A")
    r_b = Station(code="R_B")
    r_z = Station(code="R_Z")
    r_w = Station(code="R_W")
    db_session.add_all([r_a, r_b, r_z, r_w])
    db_session.commit()

    t_rep = Train(number="REPEAT")
    db_session.add(t_rep)
    db_session.commit()
    o_rep = TrainObservation(snapshot_id=snap.id, train_id=t_rep.id, name="Repeat")
    db_session.add(o_rep)
    db_session.commit()
    obs.extend([
        TrainStopObservation(snapshot_id=snap.id, train_id=t_rep.id, station_id=r_a.id, stop_sequence=1),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_rep.id, station_id=r_z.id, stop_sequence=2),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_rep.id, station_id=r_z.id, stop_sequence=3),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_rep.id, station_id=r_b.id, stop_sequence=4)
    ])

    # Candidate 6 for Target 3: R_A -> R_W -> R_B
    t_cand6 = Train(number="CAND6")
    db_session.add(t_cand6)
    db_session.commit()
    o_cand6 = TrainObservation(snapshot_id=snap.id, train_id=t_cand6.id, name="CAND6")
    db_session.add(o_cand6)
    db_session.commit()
    obs.extend([
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cand6.id, station_id=r_a.id, stop_sequence=1),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cand6.id, station_id=r_w.id, stop_sequence=2),
        TrainStopObservation(snapshot_id=snap.id, train_id=t_cand6.id, station_id=r_b.id, stop_sequence=3)
    ])

    db_session.add_all(obs)
    db_session.commit()

    return snap.id

def test_service_basic_reconvergence(db_session, mock_disjoint_reconvergences_data):
    snap_id = mock_disjoint_reconvergences_data
    res = calculate_train_sequence_disjoint_subpath_reconvergences(db_session, snap_id, "TARGET")

    assert res["train_number"] == "TARGET"
    assert res["total_reconvergence_count"] == 2
    
    # Check CAND1
    c1 = next(r for r in res["reconvergences"] if r["candidate_train_number"] == "CAND1")
    assert c1["anchor_from_station_code"] == "STN_A"
    assert c1["anchor_to_station_code"] == "STN_B"
    assert c1["target_from_sequence"] == 1
    assert c1["target_to_sequence"] == 4
    assert c1["target_interior_station_count"] == 2
    assert c1["candidate_interior_station_count"] == 2
    assert c1["shared_interior_station_count"] == 0
    assert c1["target_interior_station_codes"] == ["STN_X", "STN_Y"]
    assert c1["candidate_interior_station_codes"] == ["STN_Z", "STN_W"]

    # Check CAND2 (X -> B disjoint reconvergence)
    c2 = next(r for r in res["reconvergences"] if r["candidate_train_number"] == "CAND2")
    assert c2["anchor_from_station_code"] == "STN_X"
    assert c2["anchor_to_station_code"] == "STN_B"
    assert c2["target_interior_station_codes"] == ["STN_Y"]
    assert c2["candidate_interior_station_codes"] == ["STN_Z"]

def test_service_cyclic_target(db_session, mock_disjoint_reconvergences_data):
    snap_id = mock_disjoint_reconvergences_data
    res = calculate_train_sequence_disjoint_subpath_reconvergences(db_session, snap_id, "CYCLIC")
    
    # CYCLIC has A(1) -> X(2) -> B(3) and A(4) -> Y(5) -> B(6)
    # CAND5 has A(1) -> Z(2) -> B(3)
    # Both targets should match CAND5 since neither X nor Y intersect with Z.
    # Also A(1) -> B(6) matches CAND5.
    assert res["total_reconvergence_count"] == 3
    
    # Verify the two separate target anchor pairs are evaluated independently
    target_bounds = [(r["target_from_sequence"], r["target_to_sequence"]) for r in res["reconvergences"]]
    assert (1, 3) in target_bounds
    assert (4, 6) in target_bounds

def test_service_repeated_interior(db_session, mock_disjoint_reconvergences_data):
    snap_id = mock_disjoint_reconvergences_data
    res = calculate_train_sequence_disjoint_subpath_reconvergences(db_session, snap_id, "REPEAT")
    
    # REPEAT has A(1) -> Z(2) -> Z(3) -> B(4)
    # CAND6 has A(1) -> W(2) -> B(3)
    # They share 0 stations.
    assert res["total_reconvergence_count"] == 1
    r = res["reconvergences"][0]
    assert r["candidate_train_number"] == "CAND6"
    assert r["target_interior_station_codes"] == ["R_Z", "R_Z"]

def test_service_empty_result(db_session, mock_disjoint_reconvergences_data):
    snap_id = mock_disjoint_reconvergences_data
    # CAND1 has A -> Z -> W -> B. No other train diverges and reconverges completely disjointly from it.
    # WAIT! TARGET goes A -> X -> Y -> B which is disjoint from CAND1!
    # So CAND1 will have 1 reconvergence (with TARGET).
    # CAND2 goes A -> X -> Z -> B. 
    # CAND1 shares Z with CAND2. TARGET shares X with CAND2.
    # What about CAND4? A -> B directly. No interior stops.
    res = calculate_train_sequence_disjoint_subpath_reconvergences(db_session, snap_id, "CAND4")
    assert res["total_reconvergence_count"] == 0
    assert res["reconvergences"] == []
