# RuggyLab OS - suite operationnelle

Ce document garde une trace simple de ce qui reste a verrouiller pour passer
de la version fonctionnelle actuelle a une exploitation terrain plus robuste.

## Priorites immediates

1. Pousser les commits locaux et verifier la CI GitHub.
2. Relancer `.\scripts\validate.ps1` apres chaque lot fonctionnel.
3. Refaire une passe UAT visuelle sur cockpit, Resultats, Vue Paillasse et Stocks
   des que Playwright est disponible dans l'environnement local.
4. Activer `scripts/process_report_delivery_outbox.py` comme tache planifiee ou
   service Windows pour traiter la diffusion des comptes-rendus.
5. Completer le catalogue d'examens avec les procedures locales validees par le
   laboratoire: tube, delai, motif de rejet, controles qualite, paillasse.

## Comptes-rendus

- La validation biologique reste non bloquante par defaut pour tenir compte de
  l'effectif reel: le document sort en statut provisoire.
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
