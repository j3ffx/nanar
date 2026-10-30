import { useEffect, useState } from 'react';

import {
  ApiError,
  fetchOnline,
  setCheckUpdates,
  setOnline,
  type OnlineSettings,
  type State,
} from '@/lib/api';

import { BackButton } from './BackButton';
import styles from './Tv.module.css';

const MESSAGES: Record<string, string> = {
  bad_key: 'Cette clé est refusée.',
  offline: 'Pas de réponse : le PC est-il connecté à Internet ?',
  quota_reached: 'Le service refuse pour l’instant : réessaie plus tard.',
};

type Service = 'tmdb' | 'opensubtitles';

/** The settings, on this machine only: the keys of the online services, off by default. */
export function Settings({ updates, onBack }: { updates: State['updates']; onBack: () => void }) {
  const [online, setOnlineState] = useState<OnlineSettings | null>(null);
  const reload = () =>
    fetchOnline()
      .then(setOnlineState)
      .catch(() => {});
  useEffect(() => {
    void reload();
  }, []);

  return (
    <section aria-labelledby="settings-title" className={styles.page}>
      <BackButton onBack={onBack} />
      <h2 id="settings-title" className={styles.groupTitle}>
        Réglages
      </h2>
      <p className={styles.lead}>
        Nanar ne parle à Internet que si tu lui donnes une clé ci-dessous, et seulement au service
        de cette clé. Il envoie le titre et l’année lus dans le nom du fichier (et, pour les
        sous-titres, l’empreinte de la vidéo) ; rien d’autre ne quitte le PC.
      </p>
      {online && (
        <>
          <KeyField
            service="tmdb"
            title="Affiches et résumés (TMDb)"
            help="Une clé d’API gratuite : compte sur themoviedb.org, puis Paramètres › API."
            state={online.tmdb}
            onSaved={reload}
          />
          {online.tmdb.error && (
            <p className={styles.note}>
              Dernière recherche interrompue : {MESSAGES[online.tmdb.error] ?? online.tmdb.error}
            </p>
          )}
          <KeyField
            service="opensubtitles"
            title="Sous-titres en ligne (OpenSubtitles)"
            help="Une clé gratuite : compte sur opensubtitles.com, puis « API consumers ». Cinq sous-titres par jour."
            state={online.opensubtitles}
            onSaved={reload}
          />
          <p className={styles.note}>
            Ce produit utilise l’API TMDB mais n’est ni approuvé ni certifié par TMDB.
          </p>
        </>
      )}
      {updates && (
        <div className={styles.setting}>
          <p className={styles.settingTitle}>Mises à jour</p>
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
                Chercher les nouvelles versions (une fois par jour, sur GitHub)
              </label>
              <p className={styles.note}>
                {updates.available
                  ? `Nanar ${updates.available} est sorti : la bibliothèque propose de l’installer.`
                  : updates.enabled
                    ? 'Tu es à jour.'
                    : 'Désactivé : Nanar ne demande rien à GitHub.'}
              </p>
            </>
          ) : (
            <p className={styles.note}>Lancé depuis les sources : `git pull` le met à jour.</p>
          )}
        </div>
      )}
    </section>
  );
}

function KeyField(props: {
  service: Service;
  title: string;
  help: string;
  state: { set: boolean; hint: string | null };
  onSaved: () => void;
}) {
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const save = (key: string) => {
    setBusy(true);
    setMessage(null);
    setOnline({ [props.service]: key })
      .then(() => {
        setValue('');
        setMessage(key ? 'Clé enregistrée.' : 'Clé retirée : plus rien n’est demandé.');
        props.onSaved();
      })
      .catch((e: unknown) => {
        const code = e instanceof ApiError ? e.code : 'offline';
        setMessage(MESSAGES[code] ?? MESSAGES.offline!);
      })
      .finally(() => setBusy(false));
  };
  const id = `key-${props.service}`;
  return (
    <div className={styles.setting}>
      <label htmlFor={id} className={styles.settingTitle}>
        {props.title}
      </label>
      <p className={styles.note}>
        {props.state.set ? `Activé, avec la clé ${props.state.hint ?? ''}.` : 'Désactivé.'}{' '}
        {props.help}
      </p>
      <div className={styles.settingRow}>
        <input
          id={id}
          data-nav
          className={styles.input}
          type="password"
          autoComplete="off"
          spellCheck={false}
          placeholder={props.state.set ? 'Nouvelle clé' : 'Colle ta clé ici'}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && value.trim()) save(value.trim());
          }}
        />
        <button
          type="button"
          data-nav
          className={styles.action}
          disabled={busy || !value.trim()}
          onClick={() => save(value.trim())}
        >
          {busy ? 'Vérification…' : 'Enregistrer'}
        </button>
        {props.state.set && (
          <button
            type="button"
            data-nav
            className={styles.backButton}
            disabled={busy}
            onClick={() => save('')}
          >
            Retirer
          </button>
        )}
      </div>
      {message && (
        <p className={styles.note} role="status">
          {message}
        </p>
      )}
    </div>
  );
}
