from sqlalchemy import text
from railgati.db import get_session_factory

db = get_session_factory()()

is_sqlite = db.bind.dialect.name == "sqlite"

if is_sqlite:
    time_diff_expr = """
        (strftime("%s", "1970-01-01 " || tso.departure_time) - strftime("%s", "1970-01-01 " || tso.arrival_time)) +
        CASE WHEN strftime("%s", "1970-01-01 " || tso.departure_time) < strftime("%s", "1970-01-01 " || tso.arrival_time)
             THEN 86400 ELSE 0 END
    """
else:
    time_diff_expr = """
        (EXTRACT(EPOCH FROM tso.departure_time::time) - EXTRACT(EPOCH FROM tso.arrival_time::time)) +
        CASE WHEN EXTRACT(EPOCH FROM tso.departure_time::time) < EXTRACT(EPOCH FROM tso.arrival_time::time)
             THEN 86400 ELSE 0 END
    """

query = text(f"""
    EXPLAIN QUERY PLAN
    WITH target_dwells AS (
        SELECT 
            tso.stop_sequence as target_seq,
            tso.station_id as station_id,
            s.code as station_code,
            CAST(({time_diff_expr}) / 60.0 AS FLOAT) as target_dwell
        FROM train_stop_observations tso
        JOIN stations s ON s.id = tso.station_id
        JOIN trains t ON t.id = tso.train_id
        WHERE tso.snapshot_id = 2
          AND t.number = '15905'
          AND tso.arrival_time IS NOT NULL
          AND tso.departure_time IS NOT NULL
    ),
    target_station_ids AS (
        SELECT DISTINCT station_id FROM target_dwells
    ),
    network_dwells AS (
        SELECT 
            tso.station_id,
            CAST(({time_diff_expr}) / 60.0 AS FLOAT) as dwell
        FROM train_stop_observations tso
        JOIN target_station_ids tid ON tid.station_id = tso.station_id
        WHERE tso.snapshot_id = 2
          AND tso.arrival_time IS NOT NULL
          AND tso.departure_time IS NOT NULL
    ),
    network_stats AS (
        SELECT 
            station_id,
            AVG(dwell) as avg_dwell,
            COUNT(*) as occurrence_count
        FROM network_dwells
        GROUP BY station_id
    )
    SELECT 
        td.target_seq,
        td.station_code,
        td.target_dwell,
        ns.avg_dwell,
        ns.occurrence_count,
        td.target_dwell / NULLIF(ns.avg_dwell, 0) as ratio
    FROM target_dwells td
    JOIN network_stats ns ON ns.station_id = td.station_id
    WHERE (td.target_dwell / NULLIF(ns.avg_dwell, 0)) > 1.0
    ORDER BY ratio DESC
    LIMIT 10
""")

print("--- EXPLAIN 15905 ---")
if not is_sqlite:
    query = text("EXPLAIN ANALYZE " + query.text.replace("EXPLAIN QUERY PLAN", ""))
for r in db.execute(query).fetchall():
    print(r[0])
