# Registre des manuels et preuves d'équipement requis — 2026

## Règles documentaires

- Le type exact du document doit être enregistré.
- Un `Operator's Manual` ou `Operation Manual` n'équivaut pas à un
  `Interface Manual`, `Communication Protocol` ou `LIS Manual`.
- Les manuels intégraux ne doivent pas être publiés dans ce dépôt sans droits
  établis. Seules les métadonnées, références de pages, décisions et courts
  extraits nécessaires peuvent être consignés.
- Les originaux fournis doivent rester inchangés et les pages doivent être
  inventoriées avant extraction.

## État par appareil

| Appareil | Disponible | À obtenir ou confirmer en priorité |
|---|---|---|
| Dymind DH36 | Identification DH36 communiquée | Plaque et firmware ; manuel opérateur ; manuel LIS/communication ; protocole configuré ; table de codes ; unités/flags ; framing ; ACK/NAK ; timeouts/retries |
| Dymind Semi-auto Chemistry Analyzer | `Operator's Manual`, modèle non visible | Plaque/modèle ; spécifications produit ; chapitres communication, RS-232, USB, Ethernet, LIS, export/PC ; méthodes, unités, calibration et CQ |
| Appareil de coagulation | Aucun manuel spécifique identifié | Photo plaque ; marque/modèle ; manuel opérateur et technique ; liste des tests ; cuvettes/réactifs ; éventuelle spécification de communication |
| Anbio / BIOSCANN CHEM 100 | `Operation Manual` v1.0 ; plaque associée à Anbio Biotechnology | Revue du manuel complet ; manuel technique/communication si absent ; paramètres RS-232 ; brochage ; rôle USB-B ; format résultats ; codes/unités/flags ; ACK/NAK/rejeu ; firmware |
| Precix / ProCheck Expert | Documentation commerciale et cinq paramètres annoncés | Plaque et nom exact ; notice constructeur ; bandelettes/lots ; unités ; plages analytiques ; limites ; CQ ; interférences ; calibration ; répétition ; protocole/pilote/format USB |
| Magnus Epiled Theia-I MLXi | Identification communiquée | Plaque ; manuel ; inventaire d'un éventuel dispositif d'imagerie distinct ; preuve de toute interface ; maintenance et qualification optique |
| ZJZD-III | `Instruction Manual` — `Oscillator` | Fabricant/plaque ; type de mouvement ; vitesse/durée ; usage réel ; maintenance, nettoyage et qualification de fonctionnement |
| Centrifugeuse 80-2 | Manuel 80-1/80-2, case 80-2 cochée | Fabricant/plaque ; vitesse maximale et tolérance ; capacité/rotor/positions ; minuterie/freinage ; équilibrage ; alimentation ; entretien ; sécurité couvercle |

## Métadonnées à relever

Pour chaque document : `document_title`, `manufacturer`, `model`,
`document_type`, `version`, langue, nombre de pages, date, présence d'une copie
physique ou numérique, présence d'une section connectivité, présence d'une
spécification de protocole, statut de revue, relecteur et date de revue.

## Procédure de numérisation contrôlée

1. Conserver l'original inchangé dans un stockage autorisé.
2. Inventorier les pages et vérifier ordre, doublons et manques.
3. Relever les métadonnées et l'empreinte de la copie de travail.
4. Extraire uniquement les informations techniques nécessaires.
5. Séparer texte exact, traduction et interprétation.
6. Faire relire toute donnée de protocole par deux personnes.
7. Ne jamais inclure dans Git un numéro de série complet, une donnée patient,
   un secret ou le manuel complet sans autorisation juridique.
