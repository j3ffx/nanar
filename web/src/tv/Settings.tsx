import { useEffect, useState } from 'react';

import {
  fetchOnline,
  setCheckUpdates,
  setOnline,
  type OnlineSettings,
  type State,
} from '@/lib/api';

import { BackButton } from './BackButton';
import styles from './Tv.module.css';

const LAST_ERROR: Record<string, string> = {
  bad_key: 'TMDB refuse cette clé : change-la.',
  offline: 'TMDB ne répondait pas : Nanar réessaiera à la prochaine ouverture.',
  quota_reached:
    'TMDB limite les demandes pour l’instant : Nanar réessaiera à la prochaine ouverture.',
};

/** The settings, on this machine only: what may talk to the Internet (nothing by default). */
export function Settings({
  updates,
  onBack,
  onNavigate,
}: {
  updates: State['updates'];
  onBack: () => void;
  onNavigate: (path: string) => void;
}) {
  const [online, setState] = useState<OnlineSettings | null>(null);
  const reload = () =>
    fetchOnline()
      .then(setState)
      .catch(() => {});
  useEffect(() => {
    void reload();
  }, []);

  // The buttons have only just come: the focus goes to the first, rather than "Retour". After
  // removing a key, the button that had it is gone: the same.
  useEffect(() => {
    if (!online) return;
    const active = document.activeElement;
    if (active === document.body || active?.hasAttribute('data-back')) {
      document.querySelector<HTMLElement>('main [data-nav]:not([data-back])')?.focus();
    }
  }, [online]);

  return (
    <section aria-labelledby="settings-title" className={styles.page}>
      <BackButton onBack={onBack} />
      <h2 id="settings-title" className={styles.groupTitle}>
        Réglages
      </h2>
      <p className={styles.lead}>
        Par défaut, Nanar ne parle à personne sur Internet. Chacune de ces options, désactivée au
        départ, le fait parler à un service, qui voit l’adresse Internet de ta connexion, comme tout
        site. Une clé, c’est un code gratuit que le service te donne pour reconnaître Nanar.
      </p>
      {online && (
        <>
          <Service
            title="Affiches et résumés (TMDB)"
            what="Nanar envoie à TMDB le titre et l’année lus dans le nom de chaque vidéo du dossier, vidéos personnelles comprises, sous la clé de ton compte."
            state={online.tmdb}
            problem={online.tmdb.error ? (LAST_ERROR[online.tmdb.error] ?? null) : null}
            onOpen={() => onNavigate('/reglages/tmdb')}
            onRemove={() => void setOnline({ tmdb: '' }).then(reload)}
          />
          <Service
            title="Sous-titres en ligne (OpenSubtitles)"
            what="Quand tu cherches des sous-titres depuis la télécommande, puis tout seul pour les épisodes suivants, Nanar envoie à OpenSubtitles le titre, l’année, l’épisode et une empreinte du fichier : un calcul qui dit quelle version tu as, pour trouver des sous-titres calés, sans envoyer son contenu."
            state={online.opensubtitles}
            problem={null}
            onOpen={() => onNavigate('/reglages/opensubtitles')}
            onRemove={() => void setOnline({ opensubtitles: '' }).then(reload)}
          />
        </>
      )}
      {updates && (
        <div className={styles.setting}>
          <h3 className={styles.settingTitle}>Mises à jour</h3>
          {updates.supported ? (
            <>
              <label className={styles.check}>
                <input
                  type="checkbox"
                  data-nav
                  checked={updates.enabled}
                  onChange={(event) => void setCheckUpdates(event.target.checked)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') void setCheckUpdates(!updates.enabled);
                  }}
                />
                Chercher les nouvelles versions sur GitHub (au démarrage, puis une fois par jour)
              </label>
              <p className={styles.note}>{updateNote(updates)}</p>
            </>
          ) : (
            <p className={styles.note}>
              Nanar {updates.version}. Lancé depuis les sources : <code>git pull</code> le met à
              jour.
            </p>
          )}
        </div>
      )}
      <p className={styles.note}>
        Ce produit utilise l’API TMDB mais n’est ni approuvé ni certifié par TMDB.
      </p>
    </section>
  );
}

function updateNote(updates: NonNullable<State['updates']>): string {
  const version = `Nanar ${updates.version}.`;
  if (updates.available)
    return `${version} La version ${updates.available} est sortie : la bibliothèque propose de l’installer.`;
  if (!updates.enabled) return `${version} Désactivé : Nanar ne demande rien à GitHub.`;
  if (!updates.checkedAt) return `${version} Pas encore vérifié.`;
  const day = new Date(updates.checkedAt * 1000).toLocaleDateString('fr-FR', {
    day: 'numeric',
    month: 'long',
  });
  return `${version} À jour à la dernière vérification (${day}).`;
}

function Service(props: {
  title: string;
  what: string;
  state: { set: boolean; hint: string | null };
  problem: string | null;
  onOpen: () => void;
  onRemove: () => void;
}) {
  return (
    <div className={styles.setting}>
      <h3 className={styles.settingTitle}>{props.title}</h3>
      <p className={styles.note}>{props.what}</p>
      <p className={styles.note}>
        {props.problem
          ? props.problem
          : props.state.set
            ? `Activé, avec la clé ${props.state.hint ?? ''}.`
            : 'Désactivé.'}
      </p>
      <div className={styles.settingRow}>
        <button
          type="button"
          data-nav
          className={props.state.set ? styles.backButton : styles.action}
          onClick={props.onOpen}
        >
          {props.state.set ? 'Changer la clé' : 'Activer : obtenir une clé'}
        </button>
        {props.state.set && (
          <button type="button" data-nav className={styles.backButton} onClick={props.onRemove}>
            Retirer la clé
          </button>
        )}
      </div>
    </div>
  );
}
