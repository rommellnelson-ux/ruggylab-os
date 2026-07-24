# Fiche de commissioning — Dymind Semi-auto Chemistry Analyzer

## 1. Identité confirmée

- Fabricant : Dymind.
- Type communiqué : `Semi-auto Chemistry Analyzer`.
- Fonction : biochimie ou spectrophotométrie semi-automatique.
- Ce profil est distinct du DH36 et de l'appareil de coagulation.

## 2. Informations inconnues

- modèle exact, plaque, identifiant d'actif, série expurgée et firmware ;
- configuration, révision et accessoires ;
- connectivité ou capacité d'export ;
- méthodes, longueurs d'onde, unités, réactifs, calibration et CQ.

## 3. Documents disponibles

Un `Operator's Manual` Dymind a été observé ; le modèle n'est pas visible sur la
couverture communiquée.

## 4. Documents manquants

- plaque et modèle exact ;
- spécifications produit et manuel applicable ;
- chapitres communication, RS-232, USB, Ethernet, LIS, export ou PC ;
- méthodes cinétique/end point/two point, unités et longueurs d'onde ;
- calibration, contrôle qualité et maintenance.

## 5. Connecteurs observés

Aucun connecteur n'est attribué avec certitude à cet appareil.

## 6. Protocole confirmé ou inconnu

**Inconnu.** La fonction semi-automatique ne démontre aucune transmission.

## 7. Driver RuggyLab

`DymindBiochemistryParser` est un stub avec protocole inconnu. Le parseur, les
codes et les unités du DH36 sont interdits pour ce profil.

## 8. État du registre Equipment

Aucun appareil réel n'est enregistré. Le modèle exact doit être confirmé avant
toute identité ou interface, qui resterait désactivée.

## 9. Qualification technique

Impossible avant identification du modèle et obtention de la documentation
applicable.

## 10. Qualification clinique

Non commencée. Aucune méthode, longueur d'onde, unité, réactif, calibration ou
CQ n'est approuvé.

## 11. Tests synthétiques requis

Après documentation : framing/export, mapping analytes-méthodes-unités, valeur
absente, code inconnu, doublon, ordre, ACK/NAK éventuel, panne, reprise et
absence d'écriture partielle.

## 12. Tests réels requis

Après autorisation : identité, méthodes, calibration, CQ, répétabilité,
corrélation, export éventuel et vérification qu'aucun profil DH36 n'est
réutilisé.

## 13. Statut final

**NON IDENTIFIÉ**

Le modèle exact reste inconnu ; toute activation ou réutilisation du profil DH36
est interdite.
