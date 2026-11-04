def pytest_report_collectionfinish(config, items):
    """List node ids even at `-q -q` so the criterion K2 can count tests with grep '::'."""
    if config.option.collectonly:
        return [i.nodeid for i in items if i.nodeid.startswith("tests/agent/")]
    return []
