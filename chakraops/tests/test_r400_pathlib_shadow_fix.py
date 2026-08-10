# R40 remediation: pathlib Path must not be shadowed by FastAPI Path
from app.api.ui_routes import _repo_root, ui_backtest_r40_last

def test_repo_root_is_filesystem_path():
    root = _repo_root()
    assert root.exists()
    assert (root / 'app').is_dir() or (root / 'tests').is_dir()

def test_r40_last_returns_absent_without_crash():
    data = ui_backtest_r40_last(x_ui_key=None)
    assert data['status'] == 'OK'
    assert data['simulation'] is True
    assert data['manual_only'] is True
    assert data.get('present') is False
