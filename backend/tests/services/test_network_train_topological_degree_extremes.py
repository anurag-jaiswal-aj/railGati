import pytest
from railgati.services.network import calculate_train_sequence_topological_degree_extremes
from railgati.models.train import Train, TrainStopObservation
from railgati.models.station import Station
from railgati.models.provenance import DatasetSnapshot, DataSource

@pytest.fixture
def mock_degree_extremes_data(db_session):
    source = DataSource(name="EXTREMES_SRC", url="http://test", publisher="Test", license="Test")
    db_session.add(source)
    db_session.commit()
    
    snap = DatasetSnapshot(source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    
    # We need to construct stations such that their global degree perfectly matches:
    # We will create "dummy" stations and trains to inflate the degree of our main stations.
    # To give station S a degree of D, we can connect it to D distinct dummy stations.
    
    def create_station(code):
        s = Station(code=code)
        db_session.add(s)
        db_session.commit()
        return s
        
    def inflate_degree(s, target_degree, train_prefix):
        # Create (target_degree) distinct adjacent stations by creating 2-stop trains
        for i in range(target_degree):
            dummy = create_station(f"{s.code}_DUMMY_{i}")
            t = Train(number=f"{train_prefix}_{i}")
            db_session.add(t)
            db_session.commit()
            db_session.add(TrainStopObservation(snapshot_id=snap.id, train_id=t.id, station_id=s.id, stop_sequence=1))
            db_session.add(TrainStopObservation(snapshot_id=snap.id, train_id=t.id, station_id=dummy.id, stop_sequence=2))
        db_session.commit()

    # Create target trains
    trains = {
        "STRICT_MAX": ["S2A", "S5A", "S2B"], # 2 -> 5 -> 2
        "STRICT_MIN": ["S5B", "S2C", "S5C"], # 5 -> 2 -> 5
        "PLAT_MAX": ["S2D", "S5D", "S5E", "S2E"], # 2 -> 5 -> 5 -> 2
        "PLAT_MIN": ["S5F", "S2F", "S2G", "S5G"], # 5 -> 2 -> 2 -> 5
        "MONO": ["S1A", "S2H", "S3A", "S4A"], # 1 -> 2 -> 3 -> 4
        "SHORT_1": ["S2I"], # 1 stop
        "SHORT_2": ["S2J", "S2K"], # 2 stops
        "CYCLIC": ["S2L", "S5H", "S2L", "S3B"] # A -> B -> A -> C (2 -> 5 -> 2 -> 3)
    }
    
    degrees = {
        "S2A": 2, "S5A": 5, "S2B": 2,
        "S5B": 5, "S2C": 2, "S5C": 5,
        "S2D": 2, "S5D": 5, "S5E": 5, "S2E": 2,
        "S5F": 5, "S2F": 2, "S2G": 2, "S5G": 5,
        "S1A": 1, "S2H": 2, "S3A": 3, "S4A": 4,
        "S2I": 0,
        "S2J": 2, "S2K": 2,
        "S2L": 2, "S5H": 5, "S3B": 3
    }
    
    stations = {}
    for code, deg in degrees.items():
        stations[code] = create_station(code)
    
    # We must account for the target train's edges when inflating degrees.
    # The target train itself will add adjacent stations. 
    # To keep the test purely deterministic without complex pre-calculation,
    # let's just insert the target trains, then observe their degrees in a print/debug if needed, 
    # or just use the target trains ALONE and build exact structures.
    # Actually, building explicit graphs is safer.
    
    # For STRICT_MAX: S2A(1 adj) -> S5A(2 adj) -> S2B(1 adj). 
    # But we want 2->5->2.
    # So we need to add 1 more to S2A, 3 more to S5A, 1 more to S2B.
    
    for t_num, seq in trains.items():
        t = Train(number=t_num)
        db_session.add(t)
        db_session.commit()
        for i, code in enumerate(seq, 1):
            db_session.add(TrainStopObservation(
                snapshot_id=snap.id, train_id=t.id, station_id=stations[code].id, stop_sequence=i
            ))
    db_session.commit()

    # Now inflate degrees to exact numbers.
    # For a station, its current degree is the number of distinct adjacent stations from all target trains.
    # We can just run a query to see its current degree, and add dummy edges until it matches the target.
    current_degrees_query = """
    WITH edge_pairs AS (
        SELECT o1.station_id as s1, o2.station_id as s2
        FROM train_stop_observations o1
        JOIN train_stop_observations o2
          ON o1.train_id = o2.train_id 
         AND o1.snapshot_id = o2.snapshot_id
         AND o2.stop_sequence = o1.stop_sequence + 1
        WHERE o1.snapshot_id = :snap_id
    ),
    undirected_edges AS (
        SELECT s1 as u, s2 as v FROM edge_pairs
        UNION
        SELECT s2 as u, s1 as v FROM edge_pairs
    )
    SELECT u, count(distinct v) as deg
    FROM undirected_edges
    GROUP BY u
    """
    from sqlalchemy import text
    res = db_session.execute(text(current_degrees_query), {"snap_id": snap.id}).fetchall()
    current_deg = {r[0]: r[1] for r in res}
    
    for code, target_deg in degrees.items():
        sid = stations[code].id
        c_deg = current_deg.get(sid, 0)
        needed = target_deg - c_deg
        if needed > 0:
            inflate_degree(stations[code], needed, f"DUMMY_{code}")

    return snap.id

def test_strict_maximum(db_session, mock_degree_extremes_data):
    res = calculate_train_sequence_topological_degree_extremes(db_session, mock_degree_extremes_data, "STRICT_MAX")
    assert res["local_maxima_count"] == 1
    assert res["local_minima_count"] == 0
    assert res["transit_count"] == 0
    seq = res["sequence_classification"]
    assert seq[0]["classification_type"] == "TERMINAL"
    assert seq[1]["classification_type"] == "LOCAL_MAXIMUM"
    assert seq[1]["global_degree"] == 5
    assert seq[2]["classification_type"] == "TERMINAL"

def test_strict_minimum(db_session, mock_degree_extremes_data):
    res = calculate_train_sequence_topological_degree_extremes(db_session, mock_degree_extremes_data, "STRICT_MIN")
    assert res["local_maxima_count"] == 0
    assert res["local_minima_count"] == 1
    assert res["transit_count"] == 0
    seq = res["sequence_classification"]
    assert seq[1]["classification_type"] == "LOCAL_MINIMUM"
    assert seq[1]["global_degree"] == 2

def test_plateau_maximum(db_session, mock_degree_extremes_data):
    # 2 -> 5 -> 5 -> 2
    res = calculate_train_sequence_topological_degree_extremes(db_session, mock_degree_extremes_data, "PLAT_MAX")
    assert res["local_maxima_count"] == 0
    assert res["local_minima_count"] == 0
    assert res["transit_count"] == 2
    seq = res["sequence_classification"]
    assert seq[1]["classification_type"] == "TRANSIT"
    assert seq[2]["classification_type"] == "TRANSIT"

def test_plateau_minimum(db_session, mock_degree_extremes_data):
    # 5 -> 2 -> 2 -> 5
    res = calculate_train_sequence_topological_degree_extremes(db_session, mock_degree_extremes_data, "PLAT_MIN")
    assert res["local_maxima_count"] == 0
    assert res["local_minima_count"] == 0
    assert res["transit_count"] == 2
    seq = res["sequence_classification"]
    assert seq[1]["classification_type"] == "TRANSIT"
    assert seq[2]["classification_type"] == "TRANSIT"

def test_monotonic(db_session, mock_degree_extremes_data):
    # 1 -> 2 -> 3 -> 4
    res = calculate_train_sequence_topological_degree_extremes(db_session, mock_degree_extremes_data, "MONO")
    assert res["local_maxima_count"] == 0
    assert res["local_minima_count"] == 0
    assert res["transit_count"] == 2
    seq = res["sequence_classification"]
    assert seq[1]["classification_type"] == "TRANSIT"
    assert seq[2]["classification_type"] == "TRANSIT"

def test_short_routes(db_session, mock_degree_extremes_data):
    res1 = calculate_train_sequence_topological_degree_extremes(db_session, mock_degree_extremes_data, "SHORT_1")
    assert res1["total_stops"] == 1
    assert res1["local_maxima_count"] == 0
    assert res1["local_minima_count"] == 0
    assert res1["transit_count"] == 0
    assert res1["sequence_classification"][0]["classification_type"] == "TERMINAL"
    assert res1["sequence_classification"][0]["global_degree"] == 0

    res2 = calculate_train_sequence_topological_degree_extremes(db_session, mock_degree_extremes_data, "SHORT_2")
    assert res2["total_stops"] == 2
    assert res2["local_maxima_count"] == 0
    assert res2["local_minima_count"] == 0
    assert res2["transit_count"] == 0
    assert res2["sequence_classification"][0]["classification_type"] == "TERMINAL"
    assert res2["sequence_classification"][1]["classification_type"] == "TERMINAL"

def test_cyclic(db_session, mock_degree_extremes_data):
    # A -> B -> A -> C (2 -> 5 -> 2 -> 3)
    res = calculate_train_sequence_topological_degree_extremes(db_session, mock_degree_extremes_data, "CYCLIC")
    assert res["total_stops"] == 4
    assert res["local_maxima_count"] == 1
    assert res["local_minima_count"] == 1
    seq = res["sequence_classification"]
    assert seq[1]["classification_type"] == "LOCAL_MAXIMUM" # 5 (prev 2, next 2)
    assert seq[2]["classification_type"] == "LOCAL_MINIMUM" # 2 (prev 5, next 3)
    assert seq[1]["station_code"] == "S5H"
    assert seq[2]["station_code"] == "S2L"

def test_not_found(db_session, mock_degree_extremes_data):
    with pytest.raises(ValueError, match="not found"):
        calculate_train_sequence_topological_degree_extremes(db_session, mock_degree_extremes_data, "UNKNOWN")
