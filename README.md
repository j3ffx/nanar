# Nanar

Tes films sur la télé, la télécommande dans le téléphone.

Tu branches ton PC à la télé, tu lances Nanar sur le dossier où sont tes films et tes séries, et tu
restes dans ton canapé. Nanar range ta bibliothèque tout seul (les sagas ensemble et dans l’ordre,
les épisodes par saison), affiche tout ça en grand sur la télé, et lit n’importe quelle vidéo :
mkv, HEVC, AV1, sous-titres intégrés ou à côté du fichier, VF ou VO.

> **En construction.** Nanar sait déjà ranger ta bibliothèque, l’afficher sur la télé, lire tes
> vidéos et se piloter depuis ton téléphone. Parcourir la bibliothèque depuis le téléphone arrive
> dans la prochaine étape. Ce que chaque version apporte : le
> [journal des changements](CHANGELOG.md).

## Ce que fait Nanar

- **Une bibliothèque rangée toute seule.** Nanar lit les noms des fichiers, même ceux des
  téléchargements (`Film.2023.MULTi.VFF.1080p.WEB.H264-XYZ.mkv`), pour retrouver le titre et
  l’année. Les films d’un même dossier forment une saga, dans l’ordre des années ; les épisodes
  d’une série se suivent par saison, d’un dossier à l’autre.
- **Une fenêtre, comme un lecteur vidéo.** L’accueil s’anime pendant que tu choisis ; le film
  s’ouvre à la même place, à la même taille, et Nanar revient quand il s’arrête. En fenêtre ou en
  plein écran, à toi de voir : `F`, comme dans VLC.
- **La télécommande dans ta poche.** Scanne le QR code affiché sur la télé : ton téléphone
  (Android ou iPhone, rien à installer) devient la télécommande. Lecture, pause, ±10 s, ±1 min,
  épisode suivant, volume, pistes audio et sous-titres (avec leur décalage et leur taille), plein
  écran. La télé affiche ce que tu fais. Plusieurs téléphones peuvent piloter en même temps.
- **Tout se lit.** Le moteur de [mpv](https://mpv.io/) : tous les formats courants, les pistes
  audio et les sous-titres, le HDR. Nanar choisit la VF, sinon la VO avec les sous-titres français.
- **Rien ne sort de ton PC.** Pas de compte, pas de pub, pas de statistiques, pas même une jaquette
  téléchargée : tout vient de tes fichiers.

## Essayer

Pour l’instant, Nanar se lance depuis ses sources (une version prête à installer pour Windows
viendra avec la 0.1.0). Il faut [uv](https://docs.astral.sh/uv/) et [Node.js](https://nodejs.org/)
22 :

```bash
npm ci && uv sync
uv run python scripts/get-libmpv.py
npm run build
uv run nanar D:\Films
```

`uv run nanar --demo` ouvre une bibliothèque factice, sans aucun fichier : les vidéos sont des
mires générées à la volée.

## La télécommande

1. Lance Nanar : la télé affiche un QR code en bas à droite.
2. Scanne-le avec l’appareil photo du téléphone, branché au même Wi-Fi que le PC. La page de la
   télécommande s’ouvre ; ajoute-la à l’écran d’accueil pour la retrouver d’un geste.

Nanar s’annonce sur le réseau sous le nom **`nanar.local`** : quand ton téléphone sait trouver ce
nom (les iPhone toujours, Android selon sa version), la télécommande s’ouvre à l’adresse
`http://nanar.local:8642`, qui ne change pas d’un Wi-Fi à l’autre. L’icône de l’écran d’accueil
marche alors partout, sans rescanner. Sinon, elle garde l’adresse du réseau où tu l’as ajoutée, et
il faut rescanner le QR code sur un autre Wi-Fi.

Au premier lancement, Windows demande s’il faut laisser Nanar communiquer sur le réseau : accepte
pour les **réseaux privés**. Sans cette autorisation, le téléphone ne trouve pas le PC.

Nanar ne parle qu’au réseau local, jamais à Internet. Seul un téléphone qui a scanné le code de ta
télé peut le piloter ; `nanar --new-key` change le code (les téléphones déjà appairés devront le
rescanner), et `nanar --local` coupe la télécommande.

**À l’hôtel ou chez des amis**, le Wi-Fi isole souvent les appareils les uns des autres : le
téléphone ne voit pas le PC. Active alors le partage de connexion de ton téléphone et connecte le PC
dessus ; le QR code de la télé suit le changement de réseau en quelques secondes. Les échanges ne
sont pas chiffrés : sur un Wi-Fi public partagé, quelqu’un sur le même réseau pourrait voir ce que tu
regardes.

## Les touches

Sur la bibliothèque : les flèches pour choisir, `Entrée` pour lancer ou ouvrir une saga, `Échap`
pour revenir, `F` pour le plein écran.

Pendant un film, les habitudes de VLC :

| Touche           | Action                               |
| ---------------- | ------------------------------------ |
| `Espace`         | lecture / pause                      |
| `←` `→`          | 10 secondes en arrière / en avant    |
| `Ctrl` + `←` `→` | 1 minute en arrière / en avant       |
| `↑` `↓`, molette | volume                               |
| `M`              | couper le son                        |
| `B`              | piste audio suivante                 |
| `V`              | sous-titres suivants                 |
| `G` `H`          | décaler les sous-titres              |
| `N` `P`          | épisode ou film suivant / précédent  |
| `F`, double clic | plein écran                          |
| `Échap`          | quitter le plein écran               |
| `S`, `Q`         | arrêter et revenir à la bibliothèque |

## Contribuer

Les règles du dépôt (commandes, commits, confidentialité, invariants) : [CLAUDE.md](CLAUDE.md).

## Crédits

- Lecture : [mpv](https://mpv.io/) (libmpv, GPL 2 ou plus), build Windows de
  [shinchiro](https://github.com/shinchiro/mpv-winbuild-cmake), piloté par
  [python-mpv](https://github.com/jaseg/python-mpv).
- Noms des fichiers : [guessit](https://github.com/guessit-io/guessit) (LGPL 3).
- Fenêtre : [pywebview](https://pywebview.flowrl.com/) (BSD).
- QR code : [segno](https://github.com/heuer/segno) (BSD) ; `nanar.local` :
  [python-zeroconf](https://github.com/python-zeroconf/python-zeroconf) (LGPL 2.1 ou plus).
- Police [Bricolage Grotesque](https://github.com/ateliertriay/bricolage) (SIL Open Font License).

## Licence

[GPL-3.0](LICENSE).
