# RuggyLab OS - suite operationnelle

Ce document garde une trace simple de ce qui reste a verrouiller pour passer
de la version fonctionnelle actuelle a une exploitation terrain plus robuste.

## Etat au 28 juin 2026

- Le depot `main` est synchronise et la passe UAT metier ephemere reussit 15/15.
- Le worker de diffusion dispose d'un precontrole de base, d'un journal
  persistant et d'un installateur de tache Windows renforce. La tache locale
  `RuggyLab Report Delivery Outbox Worker` est installee, revient a l'etat
  `Ready` et son dernier passage controle s'est termine avec le code 0.
- Les 23 fiches du catalogue sont explicitement marquees
  `needs_local_validation`. Aucune procedure locale n'est declaree validee sans
  reference documentaire, validateur et date.
- Les scripts PostgreSQL valident desormais l'archive et son SHA-256, isolent la
  base scratch et arretent la restauration a la premiere erreur.
- Docker Compose cloisonne application, donnees et supervision. Prometheus
  cible le port metriques reel et charge les regles d'alerte RuggyLab.
- La validation visuelle Playwright reste a refaire sur cet hote : le paquet
  Node est present, mais le binaire Chromium Playwright n'y est pas installe.

## Priorites immediates

1. Reproduire l'installation validee du worker sur le serveur Windows cible
   avec un compte de service et superviser son journal.
2. Faire valider les 23 fiches par le biologiste responsable selon
   `docs/VALIDATION_CATALOGUE_EXAMENS.md`.
3. Installer Chromium Playwright sur le poste UAT autorise puis refaire la passe
   cockpit, Resultats, Vue Paillasse et Stocks.
4. Executer la sauvegarde/restauration PostgreSQL sur l'infrastructure cible et
   conserver le verdict ainsi que le hash de l'archive.
5. Valider sur l'infrastructure cible TLS, pare-feu/VLAN, Alertmanager,
   gestionnaire de secrets et sauvegarde hors site.
6. Executer `check_deploy_readiness`, les migrations, la CI et le plan de
   rollback sur la preproduction avant le go-live.

## Comptes-rendus

- Selon la politique d'effectif reduit actuelle, les resultats produits selon
  les procedures et controles techniques en vigueur sortent immediatement en
  statut valide et peuvent etre remis au patient.
- La revue biologique est une verification interne differee, sans effet
  bloquant sur le document patient. Une file priorisee et une action groupee
  permettent a l'officier ou a l'administrateur de la solder ulterieurement.
- Une valeur critique non prise en charge reste bloquante avant publication.
- Chaque publication cree un snapshot versionne et une entree outbox.
- Canaux actifs:
  - `internal`: compte-rendu disponible dans RuggyLab;
  - `patient_portal` / `filesystem`: depot PDF local dans `REPORT_DELIVERY_OUTPUT_DIR`;
  - `fhir`: export JSON DiagnosticReport dans `REPORT_DELIVERY_FHIR_DIR`;
  - `email` / `prescriber`: envoi SMTP reel avec PDF joint si destinataire configure.
- Aucun email n'est marque comme envoye sans destinataire SMTP explicite.
- Installation Windows du worker:
  `.\scripts\install_report_delivery_worker_task.ps1`
- Desinstallation:
  `.\scripts\uninstall_report_delivery_worker_task.ps1`

## Paillasse et cockpit

- La file de travail doit rester orientee action: urgence clinique, retard TAT,
  blocage qualite, puis routine.
- La Vue Paillasse doit rester epuree: critiques, TAT < 15 minutes, routine a
  valider.
- Les fiches techniques doivent etre accessibles en contexte, idealement via un
  tiroir ou une modale depuis l'examen ou l'echantillon.

## Production

- Verifier sauvegarde et restauration sur une base de test.
- Forcer secrets longs en production et separer `.env` de tout depot Git.
- Servir l'application derriere HTTPS/reverse proxy.
- Cloisonner les automates et le serveur FastAPI par VLAN/firewall lorsque c'est
  possible, meme s'ils partagent le meme reseau local.
- Pour les automates ASTM, deployer le middleware avec SQLite WAL, retry local,
  HMAC/API key, journalisation et installation comme service.

## Formation courte agents

- Valeur critique: appeler, tracer la prise en charge, puis seulement publier.
- TAT: traiter d'abord les echeances proches et les retards.
- Echantillon non conforme: documenter le motif et ne pas masquer l'action.
- Rendu provisoire: utilisable mais a finaliser biologiquement des que possible.
