#!/usr/bin/env node
'use strict';

/**
 * sprout-toolkit npm wrapper: spawns `python3 -m sprout` with a strict
 * version pin — this wrapper's version MUST equal the installed CLI's
 * version (see §6.3 in plan-especies.md: wrapper nuevo nunca corre con
 * CLI viejo).
 *
 * Environment:
 *   SPROUT_PYTHON  interpreter to use (default: python3)
 */
const { spawnSync } = require('child_process');
const pkg = require('../package.json');

const PYTHON = process.env.SPROUT_PYTHON || 'python3';

function fail(message) {
  console.error(`sprout: ${message}`);
  process.exit(1);
}

function installHint() {
  return `Install the pinned CLI for ${PYTHON}:\n` +
    `    ${PYTHON} -m pip install "sprout-toolkit==${pkg.version}"`;
}

// 1) Python present?
const probe = spawnSync(PYTHON, ['-c', 'import sys'], { stdio: 'ignore' });
if (probe.error && probe.error.code === 'ENOENT') {
  fail(`'${PYTHON}' not found — install Python 3.10+ and retry ` +
       `(or point SPROUT_PYTHON at your interpreter).`);
}
if (probe.status !== 0) {
  fail(`'${PYTHON}' is not working (exit ${probe.status}).`);
}

// 2) CLI installed + pinned?
const version = spawnSync(PYTHON, ['-m', 'sprout', '--version'], {
  encoding: 'utf8',
});
if (version.status !== 0) {
  fail(`sprout CLI is not available to ${PYTHON}.\n  ${installHint()}`);
}
const got = (version.stdout || '').trim().replace(/^sprout\s+/, '');
if (got !== pkg.version) {
  fail(`CLI ${got || '(unknown)'} does not match this wrapper ` +
       `(${pkg.version}).\n  ${installHint()}`);
}

// 3) Run the command (exit code passthrough).
const run = spawnSync(PYTHON, ['-m', 'sprout', ...process.argv.slice(2)], {
  stdio: 'inherit',
});
if (run.error) {
  fail(String(run.error.message));
}
process.exit(run.status === null ? 1 : run.status);
