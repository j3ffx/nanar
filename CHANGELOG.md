# Nouveautés

Les changements de chaque version de Nanar, la plus récente en premier. Les numéros suivent le
[versionnage sémantique](https://semver.org/lang/fr/) : tant qu’ils commencent par 0, l’application
évolue encore beaucoup.

## 0.5.1 — à venir

**Si tu es en 0.5.0 :** sa mise à jour en un clic ne marche pas (elle ferme Nanar et s’arrête là).
Remplace le dossier à la main une dernière fois.

### Corrections

- **« Nanar ne répond pas » en pleine lecture** : les commandes passent maintenant par la connexion
  déjà ouverte, et `nanar.local` n’annonce plus une adresse que le téléphone ne peut pas joindre.
- **La télécommande ne se retrouve plus « pas encore associée »** quand elle repasse de
  `nanar.local` à l’adresse du PC : elle s’y associe toute seule, et revient au nom dès qu’il répond.
- « Connecté » ne s’affiche plus sur un Nanar disparu : la télécommande remarque le silence et
  repart d’elle-même.
- **La mise à jour en un clic marche**, et l’ancienne version revient si la nouvelle ne répond pas.
- Sécurité : une adresse piégée pouvait faire se connecter le PC à une autre machine, sans clé ; un
  programme posé dans un dossier de films pouvait être lancé à la place de PowerShell. Les deux
  sont corrigés.
- En passant à l’épisode suivant, la position de l’ancien ne peut plus être enregistrée sur le
  nouveau, et le son coupé ou le décalage des sous-titres restent justes sur le téléphone.
- Reculer pendant le compte à rebours reste sur la vidéo ; « Chapitre suivant » sur le dernier ne
  revient plus au début.
- Une vidéo illisible le dit, sur la télé et le téléphone. La télé ne s’assombrit plus pendant qu’on
  la pilote du téléphone, et une grande bibliothèque ne fige plus la télécommande.
- Le mode hôtel suit l’état réel du Wi-Fi, que Windows peut fermer tout seul.

### Nouveautés

- **Une page pour obtenir chaque clé** (TMDB, OpenSubtitles) : les étapes, un bouton pour ouvrir la
  page, de quoi copier les réponses du formulaire. La clé ne s’affiche plus en grand une fois
  enregistrée.
- **« Téléphone » et « Réglages » en haut de la télé**, plus au bout de la bibliothèque. « Téléphone »
  dit quoi vérifier quand rien ne s’ouvre, et mène au mode hôtel.
- Une série s’ouvre sur l’épisode où tu en es, avec « Reprendre » sur le téléphone. Le téléphone
  explique comment se mettre sur l’écran d’accueil.
- « Mode nuit » devient « Son de nuit », et d’autres textes plus clairs. Le bandeau de la télé et les
  indications restent visibles, et les textes sont plus grands.

## 0.5.0 — 2026-10-30

### Nouveautés

- **La mise à jour en un clic** : dans les réglages de la télé, coche « Chercher les nouvelles
  versions ». Nanar demande alors à GitHub, une fois par jour, s’il y a du nouveau (rien d’autre
  n’est envoyé), et la bibliothèque propose d’installer la version suivante : Nanar la
  télécharge, vérifie son SHA-256, remplace son dossier et redémarre. Décochée par défaut.

## 0.4.0 — 2026-10-30

L’hôtel et les jaquettes.

### Nouveautés

- **Mode hôtel**, en bas de la bibliothèque sur la télé : quand le Wi-Fi isole le téléphone du PC
  (souvent à l’hôtel), Nanar ouvre le point d’accès sans fil de Windows, qui partage la connexion
  du PC, et affiche un QR code pour le rejoindre, puis celui de la télécommande. Il le referme en
  partant.
- **Réglages**, sur la télé : de quoi activer, avec ta propre clé gratuite, deux services en
  ligne. Sans clé, Nanar ne demande toujours rien à Internet.
  - **Affiches et résumés** (TMDb) pour les films et les séries ; tes propres affiches restent
    prioritaires. Nanar envoie le titre et l’année lus dans le nom du fichier.
  - **Sous-titres français en ligne** (OpenSubtitles), depuis les sous-titres de la
    télécommande ; ils reviennent tout seuls pour les épisodes suivants. Nanar envoie le titre,
    l’année, l’épisode et l’empreinte de la vidéo.

## 0.3.0 — 2026-10-30

La soirée : ce qui se passe pendant le film.

### Nouveautés

- **Les pistes retenues** : si tu choisis la VO et les sous-titres pour un épisode, depuis le
  téléphone ou avec `B` et `V`, les épisodes suivants de la série (ou les films de la saga) les
  gardent.
- **Le mode nuit**, sur la télécommande : les explosions plus douces, les dialogues plus
  audibles. Il reste actif pour les vidéos suivantes, jusqu’à la fermeture de Nanar.
- **La minuterie** : arrêter la lecture à la fin de l’épisode (sans enchaîner le suivant), ou dans
  15 min, 30 min, 1 h ou 1 h 30. La télé prévient une minute avant.
- **Les chapitres** : chapitre précédent ou suivant depuis le téléphone, quand la vidéo en a.
- **Vu, pas vu** : depuis le téléphone, marquer une vidéo comme vue ou non vue, et retirer de « À
  suivre » le film que tu as abandonné (il revient si tu le relances).
- **Récemment ajoutés**, sur la télé et le téléphone : ce qui est arrivé dans le dossier ce
  mois-ci.
- Sur la télé, un bouton « ← Retour » au-dessus d’une saga et des résultats de recherche, pour la
  souris comme pour les flèches.

### Corrections

- Si l’entrée « Ouvrir avec Nanar » du clic droit a disparu après un « Oui », la télé la propose
  de nouveau.

## 0.2.1 — 2026-10-29

### Corrections

- Le plein écran demandé depuis le téléphone recouvre enfin la barre des tâches, même quand Nanar
  n’était pas la fenêtre active ; un film lancé depuis le téléphone s’ouvre aussi au premier plan.
- La télécommande ne décroche plus pour de bon quand le Wi-Fi du PC se coupe et revient (un Wi-Fi
  d’hôtel, par exemple) : Nanar vérifie que `nanar.local` répond encore et se réannonce sinon, et
  la télécommande repasse en attendant par l’adresse IP du PC. Garde la page ouverte : la
  recharger pendant la coupure affiche « site inaccessible ».

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
