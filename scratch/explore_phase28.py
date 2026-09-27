import time
from railgati.db import get_session_factory
from sqlalchemy import text
db = get_session_factory()()

def test_candidate_a(station_code):
    print(f"--- CANDIDATE A: Ordinality for {station_code} ---")
    query = text('''
        WITH target_trains AS (
            SELECT train_id, stop_sequence as target_seq
            FROM train_stop_observations
            WHERE snapshot_id = 2 
              AND station_id = (SELECT id FROM stations WHERE code = :code LIMIT 1)
        ),
        train_bounds AS (
            SELECT t.train_id, target_seq, 
                   MIN(tso.stop_sequence) as min_seq, 
                   MAX(tso.stop_sequence) as max_seq
            FROM target_trains t
            JOIN train_stop_observations tso ON t.train_id = tso.train_id AND tso.snapshot_id = 2
            GROUP BY t.train_id, target_seq
        )
        SELECT 
            COUNT(*) as total_trains,
            SUM(CASE WHEN target_seq = min_seq THEN 1 ELSE 0 END) as count_origin,
            SUM(CASE WHEN target_seq = max_seq THEN 1 ELSE 0 END) as count_destination,
            SUM(CASE WHEN target_seq > min_seq AND target_seq < max_seq AND (target_seq - min_seq)::float / (max_seq - min_seq) <= 0.333 THEN 1 ELSE 0 END) as count_early,
            SUM(CASE WHEN target_seq > min_seq AND target_seq < max_seq AND (target_seq - min_seq)::float / (max_seq - min_seq) > 0.333 AND (target_seq - min_seq)::float / (max_seq - min_seq) <= 0.666 THEN 1 ELSE 0 END) as count_mid,
            SUM(CASE WHEN target_seq > min_seq AND target_seq < max_seq AND (target_seq - min_seq)::float / (max_seq - min_seq) > 0.666 THEN 1 ELSE 0 END) as count_late
        FROM train_bounds
        WHERE max_seq > min_seq
    ''')
    
    start = time.time()
    res = db.execute(query, {"code": station_code}).fetchone()
    end = time.time()
    print(f"Time: {(end-start)*1000:.2f}ms")
    print(dict(res._mapping))

def test_candidate_b(train_number):
    print(f"--- CANDIDATE B: Relative Slowness for {train_number} ---")
    query = text('''
        WITH target_train AS (
            SELECT id FROM trains WHERE number = :train_num LIMIT 1
        ),
        target_edges AS (
            SELECT 
                tso1.station_id as src_station_id,
                tso2.station_id as dst_station_id,
                s1.code as src,
                s2.code as dst,
                CAST((
                    (EXTRACT(EPOCH FROM tso2.arrival_time::time) - EXTRACT(EPOCH FROM tso1.departure_time::time)) +
                    CASE WHEN EXTRACT(EPOCH FROM tso2.arrival_time::time) < EXTRACT(EPOCH FROM tso1.departure_time::time)
                         THEN 86400 ELSE 0 END
                ) / 60.0 AS FLOAT) as target_duration
            FROM train_stop_observations tso1
            JOIN train_stop_observations tso2 
              ON tso1.snapshot_id = tso2.snapshot_id 
             AND tso1.train_id = tso2.train_id 
             AND tso1.stop_sequence + 1 = tso2.stop_sequence
            JOIN stations s1 ON s1.id = tso1.station_id
            JOIN stations s2 ON s2.id = tso2.station_id
            WHERE tso1.snapshot_id = 2
              AND tso1.train_id = (SELECT id FROM target_train)
              AND tso1.departure_time IS NOT NULL
              AND tso2.arrival_time IS NOT NULL
        ),
        network_edges AS (
            SELECT 
                tso1.station_id as src_station_id,
                tso2.station_id as dst_station_id,
                CAST((
                    (EXTRACT(EPOCH FROM tso2.arrival_time::time) - EXTRACT(EPOCH FROM tso1.departure_time::time)) +
                    CASE WHEN EXTRACT(EPOCH FROM tso2.arrival_time::time) < EXTRACT(EPOCH FROM tso1.departure_time::time)
                         THEN 86400 ELSE 0 END
                ) / 60.0 AS FLOAT) as duration
            FROM train_stop_observations tso1
            JOIN train_stop_observations tso2 
              ON tso1.snapshot_id = tso2.snapshot_id 
             AND tso1.train_id = tso2.train_id 
             AND tso1.stop_sequence + 1 = tso2.stop_sequence
            JOIN target_edges te 
              ON te.src_station_id = tso1.station_id AND te.dst_station_id = tso2.station_id
            WHERE tso1.snapshot_id = 2
              AND tso1.departure_time IS NOT NULL
              AND tso2.arrival_time IS NOT NULL
        ),
        network_stats AS (
            SELECT 
                src_station_id, 
                dst_station_id,
                AVG(duration) as avg_duration,
                COUNT(*) as edge_traffic
            FROM network_edges
            GROUP BY src_station_id, dst_station_id
        )
        SELECT 
            te.src,
            te.dst,
            te.target_duration,
            ns.avg_duration,
            ns.edge_traffic,
            te.target_duration / NULLIF(ns.avg_duration, 0) as slowness_ratio
        FROM target_edges te
        JOIN network_stats ns 
          ON te.src_station_id = ns.src_station_id AND te.dst_station_id = ns.dst_station_id
        ORDER BY slowness_ratio DESC
        LIMIT 5
    ''')
    
    start = time.time()
    res = db.execute(query, {"train_num": train_number}).fetchall()
    end = time.time()
    print(f"Time: {(end-start)*1000:.2f}ms")
    for r in res:
        print(dict(r._mapping))

test_candidate_a("NDLS")
test_candidate_a("BZA")
test_candidate_b("15905")
test_candidate_b("12004")
