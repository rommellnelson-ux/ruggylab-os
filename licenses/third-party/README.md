# Textes de licence des composants tiers

Ces fichiers sont **copiés depuis les paquets et images réellement distribués**,
jamais retéléchargés depuis une source non officielle : c'est le texte livré qui
fait foi, pas une copie trouvée ailleurs.

## Contenu versionné

`python/<paquet>/` — les textes des **20 dépendances directes** de
`requirements.txt`. Ils sont versionnés pour deux raisons :

1. le `Dockerfile` les copie dans l'image ; le build doit fonctionner sans avoir
   à exécuter l'inventaire au préalable ;
2. ils constituent la preuve minimale conservée dans l'historique du dépôt.

## Contenu généré en intégration continue

L'ensemble **complet**, incluant la fermeture transitive installée depuis
`requirements.txt` dans un **environnement propre**, est régénéré par le job
`License and distribution compliance` et publié en artefact CI
`third-party-evidence`, avec l'inventaire JSON et les deux SBOM.

> L'environnement propre n'est pas un détail. Exécuté sur un poste de
> développement, l'inventaire remonte des outils absents de `requirements.txt`
> — dont plusieurs sous GPL — et ferait apparaître un risque copyleft qui
> n'existe pas dans l'image distribuée.

## Régénérer localement

```bash
python scripts/inventory_python_licenses.py --copy-licenses --json artifacts/python-licenses.json --fail-on-unknown
```

## Ce qui n'est pas ici

Les licences des **images Docker** (PostgreSQL, Caddy, Redis, Prometheus,
Grafana) résident dans les images elles-mêmes. La CI les extrait et les joint
aux artefacts ; elles ne sont pas dupliquées dans le dépôt.

Voir [`../../THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md) pour
l'inventaire commenté, les obligations et les points non résolus.
