# Root conftest — anchors pytest rootdir to the project directory.
# Always run pytest from this folder:
#   cd path/to/3-Lakes-Logistics
#   pytest tests/ -v

collect_ignore = [
    # Manual scripts — not pytest suites
    "tests/test_driver_api.py",
    "tests/test_driver_live.py",
    "tests/bond_escalate.py",
    "tests/cleanup_test_data.py",
]
