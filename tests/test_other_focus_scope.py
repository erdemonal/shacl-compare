from shacl_compare.compare import _other_focus_rows

def test_other_focus_ignores_unrelated_source_shape():
    path = "http://example.org/firstName"
    component = "http://www.w3.org/ns/shacl#MinCountConstraintComponent"
    severity = "http://www.w3.org/ns/shacl#Violation"
    designated_shape = "http://example.org/PersonShape-firstName"
    other_shape = "http://example.org/OtherShape-firstName"
    baseline = [
        {
            "focus_key": "http://example.org/PersonA",
            "result_path": path,
            "source_shape": designated_shape,
            "source_constraint_component": component,
            "severity": severity,
        },
        {
            "focus_key": "http://example.org/PersonB",
            "result_path": path,
            "source_shape": designated_shape,
            "source_constraint_component": component,
            "severity": severity,
        },
        {
            "focus_key": "http://example.org/Alien",
            "result_path": path,
            "source_shape": other_shape,
            "source_constraint_component": component,
            "severity": severity,
        },
    ]
    after = [
        {
            "focus_key": "http://example.org/Alien",
            "result_path": path,
            "source_shape": other_shape,
            "source_constraint_component": component,
            "severity": severity,
        },
    ]
    rows = _other_focus_rows(
        baseline,
        after,
        designated_focus_key="http://example.org/PersonA",
        path=path,
        component=component,
        severity=severity,
        source_shapes={designated_shape},
    )
    keys = {r["focus_key"] for r in rows}
    assert "http://example.org/Alien" not in keys
    assert "http://example.org/PersonB" in keys
    assert next(r["result_outcome"] for r in rows if r["focus_key"].endswith("PersonB")) == "CLEAR"
