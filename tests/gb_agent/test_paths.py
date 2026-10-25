from gb_agent.paths import gb_agent_path


def test_gb_agent_dir_overrides_the_shared_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("JIMBARRETT_DATA_DIR", str(tmp_path / "shared"))
    monkeypatch.delenv("GB_AGENT_DIR", raising=False)
    assert gb_agent_path("runs") == tmp_path / "shared" / "gb_agent" / "runs"
    monkeypatch.setenv("GB_AGENT_DIR", str(tmp_path / "big_disk"))
    assert gb_agent_path("runs") == tmp_path / "big_disk" / "runs"
