"""Cardinalité Prometheus : le label endpoint = gabarit de route, jamais le chemin brut.

Un chemin brut (`/api/v1/patients/8472`) créerait une série métrique par
ressource ET placerait des identifiants dans Prometheus (§5 : aucune donnée
patient dans les labels).
"""


def test_metrics_label_uses_route_template_not_raw_path(client) -> None:  # noqa: ANN001
    # 401 attendu (pas de jeton) — mais la route EST résolue par le routeur,
    # donc la métrique doit être enregistrée sous le gabarit.
    r = client.get("/api/v1/patients/424242")
    assert r.status_code in (401, 403)

    body = client.get("/metrics").text
    assert "/api/v1/patients/{patient_id}" in body
    assert 'endpoint="/api/v1/patients/424242"' not in body


def test_unmatched_paths_are_aggregated(client) -> None:  # noqa: ANN001
    # Un chemin inconnu ne doit pas créer de série par URL scannée (bruit,
    # scans, typos) : tout part dans le seau "unmatched".
    client.get("/api/v1/nexistepas-982137")
    body = client.get("/metrics").text
    assert 'endpoint="/api/v1/nexistepas-982137"' not in body
