# Profil appareil — Dymind Semi-auto Chemistry Analyzer

## Identité

| Champ | État |
|---|---|
| Fabricant | Dymind |
| Type | Semi-auto Chemistry Analyzer |
| Modèle | Inconnu ; non visible sur la couverture fournie |
| Famille | Biochimie / spectrophotométrie semi-automatique |
| Document | `Operator's Manual` |

Ce profil est distinct du Dymind DH36 et de l'appareil de coagulation annoncé.
Une fusion ultérieure exige une preuve physique et documentaire.

## Connectivité

Aucun protocole, sens de transmission ou port n'est confirmé pour cet appareil.
Il ne faut pas conclure à une transmission automatique depuis sa fonction
semi-automatique.

## Logiciel RuggyLab

`app.services.analyzers.dymind_biochemistry.DymindBiochemistryParser` est un
stub : `protocol="unknown"` et parsing non implémenté. Le parseur DH36, les
codes, messages et unités d'hématologie sont interdits pour ce profil.

## À relever

Modèle, firmware, spécifications produit, communication/RS-232/USB/Ethernet/LIS,
impression/export/PC, programmation des essais, unités, calibration, CQ,
absorbance, longueurs d'onde et méthodes cinétique/end point/two point.

## Tests nécessaires

Tests synthétiques propres au protocole documenté : framing, mapping
méthodes/analytes/unités, valeurs absentes, doublons, ordre, ACK/NAK, panne,
reprise et absence d'écriture partielle.

## Statut

- appareil réel et fonction biochimie confirmés ;
- modèle exact et protocole LIS inconnus ;
- **NON QUALIFIÉ — ACTIVATION AUTOMATIQUE INTERDITE**.
