from sqlalchemy import text
from railgati.db import get_session_factory

db = get_session_factory()()

# Candidate 2: Network Edge Travel Time Spread Analytics
q2 = text("""
    WITH edge_durations AS (
        SELECT 
            tso1.station_id as from_id,
            tso2.station_id as to_id,
            CAST(
                (EXTRACT(EPOCH FROM tso2.arrival_time::time) - EXTRACT(EPOCH FROM tso1.departure_time::time)) +
                CASE WHEN EXTRACT(EPOCH FROM tso2.arrival_time::time) < EXTRACT(EPOCH FROM tso1.departure_time::time)
                     THEN 86400 ELSE 0 END
            AS FLOAT) / 60.0 as duration
        FROM train_stop_observations tso1
        JOIN train_stop_observations tso2 
          ON tso1.train_id = tso2.train_id 
          AND tso1.snapshot_id = tso2.snapshot_id
          AND tso1.stop_sequence + 1 = tso2.stop_sequence
        WHERE tso1.snapshot_id = 2
          AND tso1.departure_time IS NOT NULL
          AND tso2.arrival_time IS NOT NULL
    )
    SELECT 
        s1.code as from_code,
        s2.code as to_code,
        MAX(duration) - MIN(duration) as spread,
        MAX(duration) as max_dur,
        MIN(duration) as min_dur,
        COUNT(*) as occurrence_count
    FROM edge_durations ed
    JOIN stations s1 ON s1.id = ed.from_id
    JOIN stations s2 ON s2.id = ed.to_id
    GROUP BY from_code, to_code
    HAVING COUNT(*) > 5
    ORDER BY spread DESC
    LIMIT 5
""")

print("--- Edge Travel Time Spread ---")
for r in db.execute(q2).fetchall():
    print(r._mapping)

# Candidate 3: Network Station Dwell Spread Analytics
q3 = text("""
    WITH station_dwells AS (
        SELECT 
            tso.station_id,
            CAST(
                (EXTRACT(EPOCH FROM tso.departure_time::time) - EXTRACT(EPOCH FROM tso.arrival_time::time)) +
                CASE WHEN EXTRACT(EPOCH FROM tso.departure_time::time) < EXTRACT(EPOCH FROM tso.arrival_time::time)
                     THEN 86400 ELSE 0 END
            AS FLOAT) / 60.0 as dwell
        FROM train_stop_observations tso
        WHERE tso.snapshot_id = 2
          AND tso.arrival_time IS NOT NULL
          AND tso.departure_time IS NOT NULL
    )
    SELECT 
        s.code as station_code,
        MAX(dwell) - MIN(dwell) as spread,
        MAX(dwell) as max_dwell,
        MIN(dwell) as min_dwell,
        COUNT(*) as occurrence_count
    FROM station_dwells sd
    JOIN stations s ON s.id = sd.station_id
    GROUP BY station_code
    HAVING COUNT(*) > 5
    ORDER BY spread DESC
    LIMIT 5
""")

print("\n--- Station Dwell Spread ---")
for r in db.execute(q3).fetchall():
    print(r._mapping)

# Candidate 5: Station Outbound Edge Dominance
q5 = text("""
    WITH outbound_edges AS (
        SELECT 
            tso1.station_id as from_id,
            tso2.station_id as to_id,
            COUNT(*) as occurrences
        FROM train_stop_observations tso1
        JOIN train_stop_observations tso2 
          ON tso1.train_id = tso2.train_id 
          AND tso1.snapshot_id = tso2.snapshot_id
          AND tso1.stop_sequence + 1 = tso2.stop_sequence
        WHERE tso1.snapshot_id = 2
        GROUP BY tso1.station_id, tso2.station_id
    ),
    station_totals AS (
        SELECT 
            from_id,
            SUM(occurrences) as total_outbound,
            MAX(occurrences) as max_outbound
        FROM outbound_edges
        GROUP BY from_id
    )
    SELECT 
        s.code,
        CAST(max_outbound AS FLOAT) / total_outbound as dominance,
        max_outbound,
        total_outbound
    FROM station_totals st
    JOIN stations s ON s.id = st.from_id
    WHERE total_outbound > 10
    ORDER BY dominance ASC
    LIMIT 5
""")

print("\n--- Outbound Edge Dominance ---")
for r in db.execute(q5).fetchall():
    print(r._mapping)
