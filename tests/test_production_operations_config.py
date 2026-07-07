from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_prometheus_scrapes_actual_metrics_port_and_loads_rules():
    config = yaml.safe_load((ROOT / "monitoring/prometheus.yml").read_text(encoding="utf-8"))
    app_job = next(job for job in config["scrape_configs"] if job["job_name"] == "ruggylab-os")

    assert app_job["static_configs"][0]["targets"] == ["app:8001"]
    assert app_job["metrics_path"] == "/metrics"
    assert "/etc/prometheus/rules/*.yml" in config["rule_files"]


def test_compose_does_not_publish_datastores_or_admin_ports_publicly():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert "ports" not in services["postgres"]
    assert "ports" not in services["redis"]
    for service, port in (("app", 8000), ("prometheus", 9090), ("grafana", 3000)):
        assert services[service]["ports"] == [f"127.0.0.1:{port}:{port}"]

    assert compose["networks"]["database"]["internal"] is True
    assert services["postgres"]["networks"] == ["database"]
    assert services["redis"]["networks"] == ["database"]


def test_restore_script_rejects_unsafe_database_names_and_restore_errors():
    script = (ROOT / "scripts/pg_restore_verify.ps1").read_text(encoding="utf-8")

    assert "^[a-zA-Z_][a-zA-Z0-9_]{0,62}$" in script
    assert "--exit-on-error" in script
    assert "sidecar obligatoire introuvable" in script
