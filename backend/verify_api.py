import httpx


def test_train(train_number, expected):
    with httpx.Client() as client:
        res = client.get(
            f"http://127.0.0.1:8000/api/v1/network/trains/{train_number}/relative-edge-slowness"
        )
        if res.status_code != 200:
            print(f"FAILED {train_number}: {res.status_code} {res.text}")
            return
        data = res.json()
        print(f"SUCCESS {train_number} Snapshot: {data['timetable_snapshot_id']}")
        for exp in expected:
            halt = next(
                (
                    h
                    for h in data["slow_edges"]
                    if h["source_station_code"] == exp["src"]
                    and h["destination_station_code"] == exp["dst"]
                ),
                None,
            )
            if not halt:
                print(f"  FAILED: Missing {exp['src']} -> {exp['dst']}")
            else:
                if halt["target_duration_minutes"] != exp["target_duration"]:
                    print(
                        f"  FAILED: {exp['src']}->{exp['dst']} target_duration expected {exp['target_duration']} got {halt['target_duration_minutes']}"
                    )
                if abs(halt["network_average_minutes"] - exp["network_average"]) > 0.1:
                    print(
                        f"  FAILED: {exp['src']}->{exp['dst']} network_average expected {exp['network_average']} got {halt['network_average_minutes']}"
                    )
                if halt["network_occurrence_count"] != exp["occurrences"]:
                    print(
                        f"  FAILED: {exp['src']}->{exp['dst']} occurrences expected {exp['occurrences']} got {halt['network_occurrence_count']}"
                    )
                if abs(halt["slowness_ratio"] - exp["ratio"]) > 0.1:
                    print(
                        f"  FAILED: {exp['src']}->{exp['dst']} ratio expected {exp['ratio']} got {halt['slowness_ratio']}"
                    )
                else:
                    print(f"  OK: {exp['src']} -> {exp['dst']}")


test_train(
    "15905",
    [
        {
            "src": "MZA",
            "dst": "NZR",
            "target_duration": 12.0,
            "network_average": 6.16,
            "occurrences": 19,
            "ratio": 1.95,
        },
        {
            "src": "PGZ",
            "dst": "CRY",
            "target_duration": 7.0,
            "network_average": 3.63,
            "occurrences": 51,
            "ratio": 1.93,
        },
    ],
)
test_train(
    "12004",
    [
        {
            "src": "ULD",
            "dst": "PATA",
            "target_duration": 4.0,
            "network_average": 3.54,
            "occurrences": 93,
            "ratio": 1.13,
        },
    ],
)
