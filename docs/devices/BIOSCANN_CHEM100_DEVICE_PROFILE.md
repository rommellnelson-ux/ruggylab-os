# Profil appareil — Anbio / BIOSCANN CHEM 100

## Identité

| Champ | État |
|---|---|
| Manufacturer provisoire | Anbio Biotechnology, d'après la plaque communiquée |
| Marque visible sur le manuel | BIOSCANN |
| Modèle | CHEM 100 |
| Famille | Immunofluorescence Analyzer |
| Série | Non consignée dans Git |

La relation juridique fabricant/marque reste à confirmer.

## Documents et connecteurs

- `Operation Manual`, version 1.0 : disponible sous forme photographiée.
- Manuel LIS/communication : non fourni.
- Connecteurs observés : RS-232, USB type B, alimentation DC 12 V.

La fonction des ports, les paramètres de communication et le format des
résultats ne sont pas confirmés.

## Logiciel RuggyLab

`app.services.analyzers.anbio_immuno.AnbioImmunoParser` est un stub :
`protocol="unknown"` et parsing non implémenté. L'interface est désactivée par
défaut.

## À relever

- firmware ;
- rôle et brochage RS-232 ;
- baud rate, data bits, parity, stop bits, flow control ;
- rôle du port USB-B et éventuel pilote ;
- format, framing, encodage, codes, unités, flags, ACK/NAK et rejeu ;
- examens, réactifs, plages analytiques, calibration et contrôle qualité.

## Tests nécessaires

Simulateur à partir de la spécification constructeur, messages valides et
invalides, message partiel, doublon, identifiant/code/unité inconnus,
ACK/NAK/timeout/retry, déconnexion, panne de persistance et quarantaine.

## Statut

**NON QUALIFIÉ POUR INTERFAÇAGE CLINIQUE — NON ACTIVABLE EN CLINIQUE.**
