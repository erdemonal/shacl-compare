from shacl_compare.compare import _residuals_and_new

def test_duplicate_signatures_preserve_distinct_values():
    designated = {
        "focus_key": "http://example.org/Sensor1",
        "result_path": "http://example.org/reading",
        "source_shape": "http://example.org/SensorShape-reading",
        "source_constraint_component": (
            "http://www.w3.org/ns/shacl#MinCountConstraintComponent"
        ),
        "severity": "http://www.w3.org/ns/shacl#Violation",
    }
    baseline = [
        {**designated},
        {
            "focus_key": "http://example.org/Sensor1",
            "result_path": "http://example.org/reading",
            "source_shape": "http://example.org/SensorShape-reading",
            "source_constraint_component": (
                "http://www.w3.org/ns/shacl#DatatypeConstraintComponent"
            ),
            "severity": "http://www.w3.org/ns/shacl#Violation",
            "value": "hot",
        },
        {
            "focus_key": "http://example.org/Sensor1",
            "result_path": "http://example.org/reading",
            "source_shape": "http://example.org/SensorShape-reading",
            "source_constraint_component": (
                "http://www.w3.org/ns/shacl#DatatypeConstraintComponent"
            ),
            "severity": "http://www.w3.org/ns/shacl#Violation",
            "value": "cold",
        },
    ]
    after = [
        {
            "focus_key": "http://example.org/Sensor1",
            "result_path": "http://example.org/reading",
            "source_shape": "http://example.org/SensorShape-reading",
            "source_constraint_component": (
                "http://www.w3.org/ns/shacl#DatatypeConstraintComponent"
            ),
            "severity": "http://www.w3.org/ns/shacl#Violation",
            "value": "hot",
        },
    ]
    residual = _residuals_and_new(baseline, after, designated)
    cleared_vals = {row["signature"][-1] for row in residual["cleared"]}
    persisted_vals = {row["signature"][-1] for row in residual["persisted"]}
    assert "cold" in cleared_vals
    assert "hot" in persisted_vals
    assert residual["signature_includes_value"] is True

def test_identical_value_duplicates_use_counts():
    designated = {
        "focus_key": "http://example.org/N",
        "result_path": "http://example.org/p",
        "source_shape": "http://example.org/S",
        "source_constraint_component": (
            "http://www.w3.org/ns/shacl#HasValueConstraintComponent"
        ),
        "severity": "http://www.w3.org/ns/shacl#Violation",
    }
    row = {
        "focus_key": "http://example.org/Other",
        "result_path": "http://example.org/p",
        "source_shape": "http://example.org/S2",
        "source_constraint_component": (
            "http://www.w3.org/ns/shacl#DatatypeConstraintComponent"
        ),
        "severity": "http://www.w3.org/ns/shacl#Violation",
        "value": "x",
    }
    residual = _residuals_and_new([row, row, row], [row], designated)
    assert residual["persisted"][0]["baseline_count"] == 3
    assert residual["persisted"][0]["after_count"] == 1
    assert residual["cleared"][0]["cleared_count"] == 2
