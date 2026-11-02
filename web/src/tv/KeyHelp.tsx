import { useState, type ReactNode } from 'react';

import { ApiError, openLink, setOnline } from '@/lib/api';

import { BackButton } from './BackButton';
import styles from './Tv.module.css';

type Service = 'tmdb' | 'opensubtitles';

const SAVED: Record<Service, string> = {
  tmdb: 'Clé enregistrée. Les affiches arrivent peu à peu dans la bibliothèque.',
  opensubtitles:
    'Clé enregistrée. Pendant une vidéo, le bouton de recherche est dans les sous-titres de la télécommande.',
};

const REFUSED: Record<Service, string> = {
  tmdb: 'TMDB refuse cette clé : vérifie que tu l’as copiée en entier.',
  opensubtitles: 'OpenSubtitles refuse cette clé : vérifie que tu l’as copiée en entier.',
};

const NO_ANSWER = 'Pas de réponse : le PC est-il connecté à Internet ?';

/** How to get a key from a service, step by step, and where to put it. */
export function KeyHelp({ service, onBack }: { service: Service; onBack: () => void }) {
  return (
    <section aria-labelledby="key-title" className={styles.page}>
      <BackButton onBack={onBack} />
      <h2 id="key-title" className={styles.groupTitle}>
        {service === 'tmdb' ? 'Une clé TMDB' : 'Une clé OpenSubtitles'}
      </h2>
      {service === 'tmdb' ? <TmdbSteps /> : <OpenSubtitlesSteps />}
      <KeyField service={service} />
    </section>
  );
}

function OpenButton({ service, children }: { service: Service; children: ReactNode }) {
  const [failed, setFailed] = useState(false);
  return (
    <>
      <button
        type="button"
        data-nav
        className={styles.backButton}
        onClick={() => void openLink(service).catch(() => setFailed(true))}
      >
        {children}
      </button>
      {failed && (
        <p className={styles.note} role="alert">
          Le navigateur ne s’est pas ouvert : tape l’adresse à la main.
        </p>
      )}
    </>
  );
}

function Copy({ label, text }: { label: string; text: string }) {
  const [done, setDone] = useState(false);
  return (
    <div className={styles.copyRow}>
      <span className={styles.copyLabel}>{label}</span>
      <code className={styles.copyText}>{text}</code>
      <button
        type="button"
        data-nav
        className={styles.backButton}
        onClick={() =>
          void navigator.clipboard.writeText(text).then(
            () => setDone(true),
            () => {},
          )
        }
      >
        {done ? 'Copié' : 'Copier'}
      </button>
    </div>
  );
}

function TmdbSteps() {
  return (
    <>
      <p className={styles.lead}>
        C’est gratuit, le formulaire est juste long : compte dix minutes, une fois pour toutes. À
        faire sur le PC, TMDB le déconseille sur téléphone.
      </p>
      <ol className={styles.howTo}>
        <li>Crée un compte sur themoviedb.org et confirme ton adresse e-mail.</li>
        <li>
          Ouvre la page des clés (<code>themoviedb.org/settings/api</code>) :{' '}
          <OpenButton service="tmdb">L’ouvrir dans le navigateur</OpenButton>
        </li>
        <li>Demande une clé, choisis un usage personnel, et accepte les conditions.</li>
        <li>
          Pour le formulaire, tu peux reprendre ceci :
          <Copy label="Nom de l’application" text="Nanar" />
          <Copy label="Adresse de l’application" text="https://github.com/j3ffx/nanar" />
          <Copy
            label="Résumé"
            text="Personal use: shows posters and summaries of my own films in Nanar, a free open source home video player."
          />
          Il demande aussi ton nom et ton adresse : ils ne vont qu’à TMDB, Nanar ne les voit jamais.
        </li>
        <li>
          TMDB affiche ensuite la clé : copie la « clé d’API » (ou le « jeton d’accès en lecture »,
          les deux marchent) et colle-la ci-dessous.
        </li>
      </ol>
    </>
  );
}

function OpenSubtitlesSteps() {
  return (
    <>
      <p className={styles.lead}>
        C’est gratuit, compte deux minutes. Limite : cinq sous-titres par jour, ceux des épisodes
        suivants compris.
      </p>
      <ol className={styles.howTo}>
        <li>Crée un compte sur opensubtitles.com et connecte-toi.</li>
        <li>
          Ouvre la page des applications (<code>opensubtitles.com/consumers</code>) :{' '}
          <OpenButton service="opensubtitles">L’ouvrir dans le navigateur</OpenButton>
        </li>
        <li>
          Crée une application :
          <Copy label="Nom" text="Nanar" />
          Laisse cochée la case « Allow anonymous downloads » si elle est là : Nanar ne se connecte
          pas à ton compte.
        </li>
        <li>Copie sa clé (« API key ») et colle-la ci-dessous.</li>
      </ol>
    </>
  );
}

function KeyField({ service }: { service: Service }) {
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const save = () => {
    const key = value.trim();
    if (!key) return;
    setBusy(true);
    setMessage(null);
    setOnline({ [service]: key })
      .then(() => {
        setValue('');
        setMessage(SAVED[service]);
      })
      .catch((e: unknown) => {
        const refused = e instanceof ApiError && e.code === 'bad_key';
        setMessage(refused ? REFUSED[service] : NO_ANSWER);
      })
      .finally(() => setBusy(false));
  };
  const id = `key-${service}`;
  return (
    <div className={styles.setting}>
      <label htmlFor={id} className={styles.settingTitle}>
        Ta clé
      </label>
      <div className={styles.settingRow}>
        <input
          id={id}
          data-nav
          className={styles.input}
          type="password"
          autoComplete="off"
          spellCheck={false}
          placeholder="Colle ta clé ici"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') save();
          }}
        />
        <button
          type="button"
          data-nav
          className={styles.action}
          disabled={busy || !value.trim()}
          onClick={save}
        >
          {busy ? 'Vérification…' : 'Enregistrer'}
        </button>
      </div>
      {message && (
        <p className={styles.note} role="status">
          {message}
        </p>
      )}
    </div>
  );
}
