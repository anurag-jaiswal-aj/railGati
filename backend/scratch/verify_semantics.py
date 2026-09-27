from sqlalchemy import text

from railgati.db import get_session_factory

db = get_session_factory()()


def test_relative_slowness(train_number):
    print(f"--- Relative Slowness for {train_number} ---")
    query = text("""
        EXPLAIN ANALYZE
        WITH target_train AS (
            SELECT id FROM trains WHERE number = :train_num LIMIT 1
        ),
        target_edges AS (
            SELECT 
                tso1.stop_sequence as target_seq,
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
                COUNT(*) as occurrence_count
            FROM network_edges
            GROUP BY src_station_id, dst_station_id
        )
        SELECT 
            te.target_seq,
            te.src,
            te.dst,
            te.target_duration,
            ns.avg_duration,
            ns.occurrence_count,
            te.target_duration / NULLIF(ns.avg_duration, 0) as slowness_ratio
        FROM target_edges te
        JOIN network_stats ns 
          ON te.src_station_id = ns.src_station_id AND te.dst_station_id = ns.dst_station_id
        ORDER BY slowness_ratio DESC, te.target_seq ASC
        LIMIT 10
    """)
    for r in db.execute(query, {"train_num": train_number}).fetchall():
        print(r[0])

    print("\nResults:")
    query_results = text(str(query).replace("EXPLAIN ANALYZE\n", ""))
    for r in db.execute(query_results, {"train_num": train_number}).fetchall():
        print(dict(r._mapping))


test_relative_slowness("15905")
test_relative_slowness("12004")
