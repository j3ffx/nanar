import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { Route, Switch } from 'wouter';

import '@/styles/global.css';
import { Remote } from '@/remote/Remote';
import { Tv } from '@/tv/Tv';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Switch>
      <Route path="/tv" nest>
        <Tv />
      </Route>
      <Route>
        <Remote />
      </Route>
    </Switch>
  </StrictMode>,
);
