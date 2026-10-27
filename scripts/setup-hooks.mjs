#!/usr/bin/env node
// Runs on `npm install` (prepare): enables the versioned git hooks of .githooks/.
// Silent no-op outside a git checkout (an unpacked source archive, for instance).
import { execFileSync } from 'node:child_process';

try {
  execFileSync('git', ['rev-parse', '--is-inside-work-tree'], { stdio: 'ignore' });
  execFileSync('git', ['config', 'core.hooksPath', '.githooks'], { stdio: 'ignore' });
} catch {
  // Not a git checkout: nothing to do.
}
