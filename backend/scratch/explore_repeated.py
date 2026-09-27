from sqlalchemy import text

from railgati.db import get_session_factory

db = get_session_factory()()

query = text("""
    SELECT t.number, tso1.station_id, tso2.station_id, COUNT(*) as repeats
    FROM train_stop_observations tso1
    JOIN train_stop_observations tso2
      ON tso1.snapshot_id = tso2.snapshot_id
     AND tso1.train_id = tso2.train_id
     AND tso1.stop_sequence + 1 = tso2.stop_sequence
    JOIN trains t ON t.id = tso1.train_id
    WHERE tso1.snapshot_id = 2
      AND tso1.departure_time IS NOT NULL
      AND tso2.arrival_time IS NOT NULL
    GROUP BY t.number, tso1.station_id, tso2.station_id
    HAVING COUNT(*) > 1
    LIMIT 5;
""")

res = db.execute(query).fetchall()
print("Repeated Adjacent Station-Pairs:")
for r in res:
    print(dict(r._mapping))
