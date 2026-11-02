import { ApiError } from './api';

// What the pages say when Nanar refuses something, or doesn't answer.
const MESSAGES: Record<string, string> = {
  nothing_playing: 'Rien ne passe en ce moment.',
  no_neighbour: 'Pas d’autre épisode de ce côté.',
  bad_value: 'Ça n’a pas marché. Réessaie.',
  not_ready: 'Un instant, la vidéo se charge.',
  unknown_video: 'Cette vidéo n’est plus dans le dossier.',
  cannot_play: 'Impossible de lire cette vidéo : le fichier a peut-être été déplacé.',
  no_subtitles: 'Pas de sous-titres français trouvés pour cette vidéo.',
  quota_reached: 'Plus de sous-titres en ligne pour aujourd’hui (limite d’OpenSubtitles).',
  bad_key: 'OpenSubtitles refuse la clé (voir les réglages sur la télé).',
  offline: 'Le PC n’arrive pas à joindre le service en ligne.',
  online_off: 'Les sous-titres en ligne ne sont pas activés.',
  pairing_required: 'Ce téléphone n’est plus associé : rescanne le code de la télé.',
  not_a_folder:
    'Impossible d’ouvrir ce dossier. Vérifie qu’il existe et que le disque est branché.',
  no_window: 'Impossible d’ouvrir le choix du dossier. Réessaie.',
  bad_checksum: 'Le fichier téléchargé est abîmé : rien n’a été changé. Réessaie plus tard.',
  not_alone:
    'Le dossier de Nanar contient autre chose que Nanar : remplace-le à la main (rien n’a été changé).',
  update_failed: 'La mise à jour n’a pas pu se faire : rien n’a été changé.',
  not_supported: 'La mise à jour n’a pas pu se faire : rien n’a été changé.',
};

/** What to tell the user: silence is not the same as a refusal. */
export function sentence(error: unknown): string {
  if (error instanceof ApiError) return MESSAGES[error.code] ?? 'Ça n’a pas marché. Réessaie.';
  if (error instanceof Error && error.message === 'no answer') {
    return 'Nanar met du temps à répondre…';
  }
  return 'Nanar ne répond pas : vérifie le Wi-Fi du téléphone.';
}

/** What went wrong on its own (`notice` in the state). */
export const noticeSentence = (code: string): string =>
  MESSAGES[code] ?? 'Quelque chose n’a pas marché.';
