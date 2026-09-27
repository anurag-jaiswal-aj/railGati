from sqlalchemy import text
from railgati.db import get_session_factory

db = get_session_factory()()
is_sqlite = db.bind.dialect.name == "sqlite"

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
        s.code as station_code,
        CAST(st.max_outbound AS FLOAT) / st.total_outbound as dominance_ratio,
        st.max_outbound as max_outbound_occurrences,
        st.total_outbound as total_outbound_occurrences
    FROM station_totals st
    JOIN stations s ON s.id = st.from_id
    WHERE st.total_outbound > 0
    ORDER BY dominance_ratio ASC, st.total_outbound DESC
    LIMIT 10
""")

print("--- EXPLAIN ---")
if not is_sqlite:
    query = text("EXPLAIN ANALYZE " + q5.text)
else:
    query = text("EXPLAIN QUERY PLAN " + q5.text)

for r in db.execute(query).fetchall():
    print(r[0])
