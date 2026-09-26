from railgati.db.session import SessionLocal
from railgati.services.destination import find_direct_destinations
from railgati.models.station import Station
import time

db = SessionLocal()
ndls = db.query(Station).filter(Station.code == "NDLS").first()
mas = db.query(Station).filter(Station.code == "MAS").first()
dummy = db.query(Station).filter(Station.code == "XXX").first()

if ndls:
    start = time.time()
    res = find_direct_destinations(db, 2, ndls.id)
    end = time.time()
    print(f"NDLS results: {len(res)}, Time: {end - start:.4f}s")
    
    start2 = time.time()
    res2 = find_direct_destinations(db, 2, ndls.id, max_duration_minutes=300)
    end2 = time.time()
    print(f"NDLS with max duration results: {len(res2)}, Time: {end2 - start2:.4f}s")

if mas:
    start = time.time()
    res = find_direct_destinations(db, 2, mas.id)
    end = time.time()
    print(f"MAS results: {len(res)}, Time: {end - start:.4f}s")

if dummy:
    start = time.time()
    res = find_direct_destinations(db, 2, dummy.id)
    end = time.time()
    print(f"XXX results: {len(res)}, Time: {end - start:.4f}s")
else:
    # use some non existent id
    start = time.time()
    res = find_direct_destinations(db, 2, 999999)
    end = time.time()
    print(f"NON-EXISTENT results: {len(res)}, Time: {end - start:.4f}s")

