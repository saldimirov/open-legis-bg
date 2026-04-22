from open_legis.validate import Issue, LayerResult


def test_issue_creation():
    issue = Issue(severity="error", code="MISSING_FILE", message="not found")
    assert issue.severity == "error"
    assert issue.code == "MISSING_FILE"
    assert issue.path is None


def test_layer_result_error_count():
    result = LayerResult(
        name="mirror",
        issues=[
            Issue("error", "MISSING_FILE", "gone"),
            Issue("warn", "TOO_SMALL", "tiny"),
        ],
        stats={"checked": 2},
    )
    errors = [i for i in result.issues if i.severity == "error"]
    assert len(errors) == 1
