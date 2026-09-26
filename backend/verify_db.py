from railgati.db import get_session_factory
from sqlalchemy import text
db = get_session_factory()()

print("--- Duplicate canonical trains ---")
res = db.execute(text("SELECT number, COUNT(*) FROM trains GROUP BY number HAVING COUNT(*) > 1")).fetchall()
print("Count:", len(res))

print("--- Duplicate train observations ---")
res = db.execute(text("SELECT snapshot_id, train_id, COUNT(*) FROM train_observations GROUP BY snapshot_id, train_id HAVING COUNT(*) > 1")).fetchall()
print("Count:", len(res))

print("--- Duplicate stop sequences ---")
res = db.execute(text("SELECT snapshot_id, train_id, stop_sequence, COUNT(*) FROM train_stop_observations GROUP BY snapshot_id, train_id, stop_sequence HAVING COUNT(*) > 1")).fetchall()
print("Count:", len(res))

print("--- Orphan train observations ---")
res = db.execute(text("SELECT * FROM train_observations LEFT JOIN trains ON train_observations.train_id = trains.id WHERE trains.id IS NULL")).fetchall()
print("Count:", len(res))

print("--- Orphan train-stop observations ---")
res = db.execute(text("SELECT * FROM train_stop_observations LEFT JOIN train_observations ON train_stop_observations.train_id = train_observations.train_id AND train_stop_observations.snapshot_id = train_observations.snapshot_id WHERE train_observations.train_id IS NULL")).fetchall()
print("Count:", len(res))

print("--- Unknown station references ---")
res = db.execute(text("SELECT * FROM train_stop_observations LEFT JOIN stations ON train_stop_observations.station_id = stations.id WHERE stations.id IS NULL")).fetchall()
print("Count:", len(res))

print("--- Stop sequence verification (Train 12101) ---")
res = db.execute(text("SELECT stop_sequence, stations.code, arrival_time, departure_time, source_day FROM train_stop_observations JOIN stations ON stations.id = station_id JOIN trains ON trains.id = train_id WHERE trains.number = '12101' ORDER BY stop_sequence LIMIT 5")).fetchall()
for r in res:
    print(r)
