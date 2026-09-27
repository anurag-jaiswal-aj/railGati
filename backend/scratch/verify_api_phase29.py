import requests


def test_train(train_number, expected):
    res = requests.get(
        f"http://127.0.0.1:8000/api/v1/network/trains/{train_number}/relative-station-dwell"
    )

    if res.status_code != 200:
        print(f"FAILED {train_number}: Status {res.status_code}")
        print(res.text)
        return

    data = res.json()
    snapshot = data["timetable_snapshot_id"]
    print(f"SUCCESS {train_number} Snapshot: {snapshot}")

    dwells = data.get("relative_dwells", [])
    dwell_map = {d["station_code"]: d for d in dwells}

    for exp in expected:
        if exp["station"] not in dwell_map:
            print(f"  FAILED: Missing {exp['station']} in result.")
        else:
            halt = dwell_map[exp["station"]]
            ok = True
            if abs(halt["target_dwell_minutes"] - exp["target_dwell"]) > 0.1:
                print(
                    f"  FAILED: {exp['station']} target_dwell expected {exp['target_dwell']} got {halt['target_dwell_minutes']}"
                )
                ok = False
            if abs(halt["network_average_minutes"] - exp["network_average"]) > 0.1:
                print(
                    f"  FAILED: {exp['station']} network_average expected {exp['network_average']} got {halt['network_average_minutes']}"
                )
                ok = False
            if abs(halt["network_occurrence_count"] - exp["occurrences"]) > 5:
                print(
                    f"  FAILED: {exp['station']} occurrences expected {exp['occurrences']} got {halt['network_occurrence_count']}"
                )
                ok = False
            if abs(halt["slowness_ratio"] - exp["ratio"]) > 0.1:
                print(
                    f"  FAILED: {exp['station']} ratio expected {exp['ratio']} got {halt['slowness_ratio']}"
                )
                ok = False

            if ok:
                print(f"  OK: {exp['station']}")


test_train(
    "15905",
    [
        {
            "station": "DGR",
            "target_dwell": 40.0,
            "network_average": 4.03,
            "occurrences": 159,
            "ratio": 9.92,
        },
        {
            "station": "HIJ",
            "target_dwell": 5.0,
            "network_average": 0.15,
            "occurrences": 113,
            "ratio": 33.23,
        },
    ],
)

test_train(
    "12004",
    [
        {
            "station": "ETW",
            "target_dwell": 2.0,
            "network_average": 0.56,
            "occurrences": 185,
            "ratio": 3.55,
        },
    ],
)
