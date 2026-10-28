# Nouveautés

Les changements de chaque version de Nanar, la plus récente en premier. Les numéros suivent le
[versionnage sémantique](https://semver.org/lang/fr/) : tant qu’ils commencent par 0, l’application
évolue encore beaucoup.

## 0.2.0 — 2026-10-28

Le canapé : choisir quoi regarder sans se lever.

### Nouveautés

- **À suivre**, en tête de la bibliothèque sur la télé et sur le téléphone : les vidéos laissées
  en cours, et l’épisode (ou le film de la saga) qui suit le dernier que tu as vu, la plus
  récente d’abord.
- **Chercher depuis le téléphone** : un champ de recherche (les accents et les majuscules ne
  comptent pas) et des filtres films, séries, non vus. La télé montre les mêmes résultats ;
  `Échap` sur la télé revient à toute la bibliothèque.
- **Des aperçus en glissant la barre de progression** : le téléphone montre l’image du film à
  l’endroit où tu vas sauter.
- `Nanar.exe --uninstall` retire Nanar du menu Démarrer et du clic droit sur les dossiers (voir
  « Désinstaller » dans le README).
- Les propriétés de `Nanar.exe` indiquent son nom et sa version.

### Corrections

- En mode démo, la barre de progression et les boutons ±10 s et ±1 min marchent enfin (en
  arrière, jusqu’à une trentaine de secondes).

## 0.1.1 — 2026-10-28

### Corrections

- La version Windows s’ouvre enfin quand le zip vient d’un téléchargement : Windows marquait ses
  fichiers « venus d’Internet », et la fenêtre refusait de se lancer (« Failed to resolve
  Python.Runtime.Loader.Initialize »). Nanar retire maintenant cette marque de ses propres fichiers.

## 0.1.0 — 2026-10-27

La première version : Nanar range tes films et tes séries, les affiche sur la télé et sur ton
téléphone, les lit toutes, reprend où tu t’étais arrêté et enchaîne les épisodes. Pour Windows,
un zip à décompresser (voir le README).

- Nanar s’ouvre sur ton dossier de films (`nanar D:\Films`, ou le dernier ouvert) et range la
  bibliothèque d’après les noms des fichiers : titre et année, sagas dans l’ordre, séries par
  saison et par épisode.
- L’accueil animé sur la télé : choisis au clavier (flèches, `Entrée`, `Échap`) ou à la souris.
- La lecture dans mpv, à la place exacte de la fenêtre Nanar, qui revient quand le film s’arrête.
  Plein écran avec `F` (retenu d’une fois sur l’autre), et les touches de VLC.
- VF d’abord, sinon VO avec les sous-titres français.
- Un mode démo (`nanar --demo`) avec une bibliothèque factice.
- La télécommande sur le téléphone : scanne le QR code de la télé, et c’est parti (Android et
  iPhone, rien à installer). Lecture, pause, ±10 s, ±1 min, épisode suivant ou précédent, arrêt,
  volume, pistes audio et sous-titres, décalage et taille des sous-titres, plein écran. La télé
  affiche chaque action, et combien de téléphones sont connectés.
- `nanar --new-key` change le QR code, `nanar --local` coupe la télécommande.
- Nanar s’annonce sous le nom `nanar.local` : sur les téléphones qui le trouvent, la télécommande
  et son icône restent les mêmes d’un Wi-Fi à l’autre.
- Les fenêtres de Nanar et de la lecture ont l’icône de Nanar, et leur bouton à elles dans la
  barre des tâches.
- La bibliothèque sur le téléphone : les sagas, les séries et les films, avec leurs images ; un
  film se lance d’un geste, et la télé suit ce que tu regardes sur le téléphone.
- Chaque vidéo a une image : ton affiche si tu en as posé une à côté, sinon une image du film.
- Nanar retient où tu en es : « Reprendre à 42:10 » ou « Depuis le début », et les vidéos vues
  sont cochées.
- À la fin d’un épisode, le suivant démarre après dix secondes, dans la même fenêtre.
- Sur le téléphone, la barre de progression se fait glisser : l’heure visée s’affiche en grand, et
  la vidéo y saute quand tu lâches.
- Un film qui finit de se télécharger dans ton dossier apparaît tout seul.
- Lancé sans dossier, Nanar te demande de le choisir sur la télé ; « Changer de dossier » en bas
  de l’accueil.
- Un clic droit sur un dossier → « Ouvrir avec Nanar » (si tu as accepté de l’ajouter) l’ouvre,
  même quand Nanar est déjà ouvert.
