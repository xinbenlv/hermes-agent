#!/usr/bin/env node
//
// cpq-checks.mjs — canonical Carried Patch Queue verifier and ledger tool.
//
// Convention enforced (must match opc/skills/repo-cpq/SKILL.md):
//   - Remote naming: `upstream` = pristine upstream, `origin` = our fork.
//     Both must exist with distinct URLs. We refuse to run otherwise.
//   - Patch IDs:
//       cpq-cornerstone-N  — cornerstones, ascending N (0, 1, 2, ...)
//       patch-fix-test-pr<PR>
//       patch-fix-func-pr<PR>
//       patch-feat-pr<PR>
//       cpq-capstone-N     — capstones, descending N (..., 2, 1, 0)
//     cpq-capstone-0 is the metadata snapshot and MUST be the last commit.
//   - Commit body: YAML frontmatter (`upstream:` + `files:`) plus three
//     required Markdown sections (`## Upstream`, `## Summary`,
//     `## Drop condition`). Subject must start with the patch ID + ":".
//   - Ledger (`docs/carried-patch-ledger.yaml`) order must match the queue
//     element-by-element. cpq-capstone-0 uses `current_commit: cpq-head`.
//
// Subcommands:
//   check-remotes     — verify the OpenClaw-style remote convention
//   rebuild-ledger    — rewrite docs/carried-patch-ledger.yaml from the queue
//   rebuild-capstone  — rebuild ledger + amend/create cpq-capstone-0 + refs
//   verify            — full validity check (used by pre-push)
//   pre-commit        — warn if staged changes touch CPQ governance files
//   commit-msg <file> — validate a single commit message
//
// Adapt UPSTREAM_PR_PREFIX (line ~50) to your fork's upstream repo URL.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const LEDGER = path.join(ROOT, 'docs', 'carried-patch-ledger.yaml');

// Files whose modification implies a CPQ governance mutation. Pre-commit
// prints a warning when any are staged. Edit per repo as needed.
const CPQ_FILES = new Set([
  'AGENTS.md',
  'docs/carried-patches.md',
  'docs/carried-patch-ledger.yaml',
  'scripts/cpq-checks.mjs',
  'git-hooks/commit-msg',
  'git-hooks/pre-commit',
  'git-hooks/pre-push',
]);

// Adapt to your upstream. Used to derive upstream PR URLs from patch IDs.
const UPSTREAM_PR_PREFIX = 'https://github.com/NousResearch/hermes-agent/pull/';

const REQUIRED_SECTIONS = ['## Upstream', '## Summary', '## Drop condition'];

const CAPSTONE_HEAD_ID = 'cpq-capstone-0';
const CAPSTONE_HEAD_SUBJECT = `${CAPSTONE_HEAD_ID}: rebuild live CPQ metadata ledger`;
const CAPSTONE_HEAD_BODY = `---
upstream: null
files:
  - docs/carried-patch-ledger.yaml
---

## Upstream
- Status: fork-only
- The capstone is local-only by design; it is never an upstream PR.

## Summary
- Rebuilds \`docs/carried-patch-ledger.yaml\` from the finalized carried queue.
- Reasserts that \`cpq-head\` points to the rebuilt \`${CAPSTONE_HEAD_ID}\` metadata snapshot.

## Drop condition
- Drop only if this repo abandons the current CPQ ledger model entirely.
`;

const PATCH_ID_REGEX = /^(cpq-cornerstone-(\d+)|patch-fix-test-pr(\d+)|patch-fix-func-pr(\d+)|patch-feat-pr(\d+)|cpq-capstone-(\d+))$/;

function git(args, { check = true } = {}) {
  const proc = spawnSync('git', args, { cwd: ROOT, encoding: 'utf8' });
  if (check && proc.status !== 0) {
    throw new Error(proc.stderr?.trim() || proc.stdout?.trim() || `git ${args.join(' ')} failed`);
  }
  return (proc.stdout || '').trim();
}

function checkRemotes() {
  const upstream = git(['remote', 'get-url', 'upstream'], { check: false });
  const origin = git(['remote', 'get-url', 'origin'], { check: false });
  const errors = [];
  if (!upstream) {
    errors.push('missing remote `upstream` — should point at the pristine upstream repo');
  }
  if (!origin) {
    errors.push('missing remote `origin` — should point at our fork');
  }
  if (upstream && origin && upstream === origin) {
    errors.push(`\`upstream\` and \`origin\` resolve to the same URL (${upstream}); they must be distinct`);
  }
  if (errors.length) {
    process.stderr.write(
      'CPQ remote convention error.\n'
      + 'This skill enforces: `upstream` = pristine upstream, `origin` = our fork.\n\n'
      + errors.map((e) => `  - ${e}`).join('\n') + '\n\n'
      + 'Fix with:\n'
      + '  git remote add upstream <upstream-url>   # if missing\n'
      + '  git remote set-url upstream <upstream-url>\n'
      + '  git remote set-url origin <our-fork-url>\n\n'
      + 'Then re-run this command.\n',
    );
    process.exit(2);
  }
}

function currentHeadSubject() {
  return git(['show', '-s', '--format=%s', 'HEAD']);
}

function updateCpqRefs() {
  const base = git(['merge-base', 'upstream/main', 'HEAD']);
  const head = git(['rev-parse', 'HEAD']);
  git(['update-ref', 'refs/cpq/base', base]);
  git(['update-ref', 'refs/cpq/head', head]);
}

function carriedCommits() {
  const base = git(['merge-base', 'upstream/main', 'HEAD']);
  const raw = git(['log', '--reverse', '--format=%H%x1f%s', `${base}..HEAD`], { check: false });
  const commits = raw
    ? raw.split('\n').filter(Boolean).map((line) => {
        const [sha, subject] = line.split('\x1f');
        const id = subject.split(':', 1)[0].trim();
        return { sha, short: sha.slice(0, 8), subject, id };
      })
    : [];
  return { base, commits };
}

function upstreamPrUrl(patchId) {
  const match = /^patch-(?:fix-test|fix-func|feat)-pr(\d+)$/.exec(patchId);
  return match ? `${UPSTREAM_PR_PREFIX}${match[1]}` : null;
}

// Sort key for the canonical queue order.
//   bucket 0: cpq-cornerstone-N   sub-key = +N (ascending)
//   bucket 1: patch-fix-test-prN  sub-key = +N
//   bucket 2: patch-fix-func-prN  sub-key = +N
//   bucket 3: patch-feat-prN      sub-key = +N
//   bucket 4: cpq-capstone-N      sub-key = -N (descending; cpq-capstone-0 last)
function patchSortKey(id) {
  let m;
  if ((m = /^cpq-cornerstone-(\d+)$/.exec(id))) return [0, Number(m[1])];
  if ((m = /^patch-fix-test-pr(\d+)$/.exec(id))) return [1, Number(m[1])];
  if ((m = /^patch-fix-func-pr(\d+)$/.exec(id))) return [2, Number(m[1])];
  if ((m = /^patch-feat-pr(\d+)$/.exec(id))) return [3, Number(m[1])];
  if ((m = /^cpq-capstone-(\d+)$/.exec(id))) return [4, -Number(m[1])];
  return [99, 0];
}

function compareKeys(a, b) {
  if (a[0] !== b[0]) return a[0] - b[0];
  return a[1] - b[1];
}

function verifyQueueOrder(commits) {
  for (const c of commits) {
    if (!PATCH_ID_REGEX.test(c.id)) {
      throw new Error(`unrecognized carried patch ID: ${c.id} (subject: ${c.subject})`);
    }
  }
  const ids = commits.map((c) => c.id);
  const keys = commits.map((c) => patchSortKey(c.id));
  for (let i = 1; i < keys.length; i++) {
    if (compareKeys(keys[i - 1], keys[i]) > 0) {
      throw new Error(
        'invalid CPQ queue order; expected '
        + 'cornerstones (asc) -> fix-test (asc) -> fix-func (asc) -> feat (asc) -> capstones (desc, capstone-0 last)\n'
        + `actual: ${JSON.stringify(ids)}`,
      );
    }
  }

  // No-gap checks.
  const cornerstoneNs = ids
    .filter((id) => id.startsWith('cpq-cornerstone-'))
    .map((id) => Number(id.slice('cpq-cornerstone-'.length)));
  for (let i = 0; i < cornerstoneNs.length; i++) {
    if (cornerstoneNs[i] !== i) {
      throw new Error(`cornerstones must be 0..K with no gaps; got ${JSON.stringify(cornerstoneNs)}`);
    }
  }
  const capstoneNs = ids
    .filter((id) => id.startsWith('cpq-capstone-'))
    .map((id) => Number(id.slice('cpq-capstone-'.length)));
  // capstoneNs is in queue order, which is descending. Expected: K, K-1, ..., 0.
  if (capstoneNs.length) {
    const max = capstoneNs[0];
    for (let i = 0; i < capstoneNs.length; i++) {
      if (capstoneNs[i] !== max - i) {
        throw new Error(`capstones must be K..0 in descending order with no gaps; got ${JSON.stringify(capstoneNs)}`);
      }
    }
    if (capstoneNs.at(-1) !== 0) {
      throw new Error(`final capstone must be ${CAPSTONE_HEAD_ID}; got cpq-capstone-${capstoneNs.at(-1)}`);
    }
  }

  // Duplicate IDs are a hard error.
  const seen = new Set();
  for (const id of ids) {
    if (seen.has(id)) throw new Error(`duplicate patch ID in queue: ${id}`);
    seen.add(id);
  }
}

function writeLedger(filePath, { ensureCapstoneHead = false } = {}) {
  const { commits } = carriedCommits();
  const ids = new Set(commits.map((c) => c.id));
  const lines = ['patches:'];
  for (const c of commits) {
    const current = c.id === CAPSTONE_HEAD_ID ? 'cpq-head' : c.short;
    const upstream = upstreamPrUrl(c.id) ?? 'null';
    lines.push(`  - id: ${c.id}`);
    lines.push(`    current_commit: ${current}`);
    lines.push(`    upstream_pr: ${upstream}`);
    lines.push('');
  }
  // When called from rebuild-capstone, the snapshot capstone hasn't been
  // committed yet, so it isn't in the queue. Append its entry so the ledger
  // we are about to commit already describes the soon-to-exist snapshot.
  if (ensureCapstoneHead && !ids.has(CAPSTONE_HEAD_ID)) {
    lines.push(`  - id: ${CAPSTONE_HEAD_ID}`);
    lines.push(`    current_commit: cpq-head`);
    lines.push(`    upstream_pr: null`);
    lines.push('');
  }
  fs.writeFileSync(filePath, `${lines.join('\n').trimEnd()}\n`, 'utf8');
}

function rebuildCapstone() {
  checkRemotes();
  // If HEAD is already a capstone-0, exclude it before regenerating so the
  // ledger reflects the queue underneath, and we'll re-emit the capstone-0
  // entry below.
  const onCapstone = currentHeadSubject().startsWith(`${CAPSTONE_HEAD_ID}:`);
  writeLedger(LEDGER, { ensureCapstoneHead: !onCapstone });
  if (onCapstone) {
    // Regenerate underneath HEAD — the capstone is HEAD itself.
    // writeLedger already includes the capstone-0 entry from carriedCommits,
    // so no extra append needed.
  }
  git(['add', path.relative(ROOT, LEDGER)]);
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'cpq-'));
  const msgPath = path.join(tmpDir, 'msg.md');
  fs.writeFileSync(msgPath, `${CAPSTONE_HEAD_SUBJECT}\n\n${CAPSTONE_HEAD_BODY}`, 'utf8');
  try {
    if (currentHeadSubject().startsWith(`${CAPSTONE_HEAD_ID}:`)) {
      git(['commit', '--amend', '-F', msgPath]);
    } else {
      git(['commit', '-F', msgPath]);
    }
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
  updateCpqRefs();
}

function parseLedger(filePath) {
  if (!fs.existsSync(filePath)) throw new Error(`missing ledger: ${filePath}`);
  // Split a YAML "key: value" line on the FIRST colon. JS String.split with a
  // limit truncates rather than joining the tail, so we slice manually to keep
  // values like URLs (which contain ":") intact.
  const valueAfter = (line) => {
    const idx = line.indexOf(':');
    return idx === -1 ? '' : line.slice(idx + 1).trim();
  };
  const entries = [];
  let current = null;
  for (const rawLine of fs.readFileSync(filePath, 'utf8').split(/\r?\n/)) {
    const stripped = rawLine.trim();
    if (!stripped || stripped === 'patches:') continue;
    if (stripped.startsWith('- id:')) {
      if (current) entries.push(current);
      current = { id: valueAfter(stripped.replace(/^-\s*id/, 'id')) };
      continue;
    }
    if (!current) continue;
    if (stripped.startsWith('current_commit:')) {
      const value = valueAfter(stripped);
      current.current_commit = value === 'null' ? null : value;
    } else if (stripped.startsWith('upstream_pr:')) {
      const value = valueAfter(stripped);
      current.upstream_pr = value === 'null' ? null : value;
    }
  }
  if (current) entries.push(current);
  return entries;
}

function parseFrontmatter(body) {
  const lines = body.split(/\r?\n/);
  // Skip leading blank lines.
  let i = 0;
  while (i < lines.length && lines[i].trim() === '') i++;
  if (lines[i] !== '---') return { frontmatter: null, rest: body };
  const start = i + 1;
  let end = -1;
  for (let j = start; j < lines.length; j++) {
    if (lines[j].trim() === '---') { end = j; break; }
  }
  if (end === -1) return { frontmatter: null, rest: body };
  const meta = {};
  let currentKey = null;
  for (const line of lines.slice(start, end)) {
    if (!line.trim()) continue;
    if (/^\s+-\s+/.test(line) && currentKey) {
      const value = line.replace(/^\s+-\s+/, '').trim();
      if (!Array.isArray(meta[currentKey])) meta[currentKey] = [];
      meta[currentKey].push(value);
      continue;
    }
    const colon = line.indexOf(':');
    if (colon === -1) continue;
    const key = line.slice(0, colon).trim();
    const val = line.slice(colon + 1).trim();
    currentKey = key;
    meta[key] = val === '' ? [] : val;
  }
  const rest = lines.slice(end + 1).join('\n').replace(/^\n+/, '');
  return { frontmatter: meta, rest };
}

function validateCommitBody(subject, body) {
  if (!subject.startsWith('cpq-') && !subject.startsWith('patch-')) return; // not a carried commit
  const colon = subject.indexOf(':');
  if (colon === -1) throw new Error(`carried subject must be "<patch-id>: <title>": ${subject}`);
  const patchId = subject.slice(0, colon).trim();
  if (!PATCH_ID_REGEX.test(patchId)) {
    throw new Error(`unrecognized carried patch ID in subject: ${patchId}`);
  }
  if (!body.trim()) throw new Error(`carried commit ${patchId} requires a Markdown body`);

  const { frontmatter, rest } = parseFrontmatter(body);
  if (!frontmatter) {
    throw new Error(`carried commit ${patchId} requires YAML frontmatter (--- ... ---) with upstream and files`);
  }
  if (!('upstream' in frontmatter)) {
    throw new Error(`carried commit ${patchId} frontmatter missing \`upstream:\` (URL or null)`);
  }
  const upstream = frontmatter.upstream;
  if (typeof upstream === 'string' && upstream && upstream.toLowerCase() !== 'null' && !/^https?:\/\//.test(upstream)) {
    throw new Error(`carried commit ${patchId}: \`upstream:\` must be a URL or null; got "${upstream}"`);
  }
  const files = frontmatter.files;
  if (!Array.isArray(files) || !files.length) {
    throw new Error(`carried commit ${patchId} frontmatter missing non-empty \`files:\` list`);
  }

  for (const section of REQUIRED_SECTIONS) {
    if (!rest.includes(section)) {
      throw new Error(`carried commit ${patchId} missing required section: ${section}`);
    }
  }
}

function verifyCommitMessages(commits) {
  for (const c of commits) {
    const message = git(['show', '-s', '--format=%B', c.sha]);
    const lines = message.split(/\r?\n/);
    const subject = (lines[0] || '').trim();
    // Subject-prefix check: subject must start with the patch ID it was assigned in the queue.
    if (!subject.startsWith(`${c.id}:`)) {
      throw new Error(`commit ${c.short} subject must start with "${c.id}:"; got "${subject}"`);
    }
    const body = lines.slice(1).join('\n').trim();
    validateCommitBody(subject, body);
  }
}

function verify() {
  checkRemotes();
  const { base, commits } = carriedCommits();
  if (!commits.length) throw new Error('no carried commits found');
  if (commits.at(-1).id !== CAPSTONE_HEAD_ID) {
    throw new Error(`last carried commit must be ${CAPSTONE_HEAD_ID}; got ${commits.at(-1).id}`);
  }
  verifyQueueOrder(commits);
  verifyCommitMessages(commits);

  const entries = parseLedger(LEDGER);
  const expectedIds = commits.map((c) => c.id);
  const actualIds = entries.map((e) => e.id);
  if (JSON.stringify(expectedIds) !== JSON.stringify(actualIds)) {
    throw new Error(`ledger patch IDs do not match queue\nexpected: ${JSON.stringify(expectedIds)}\nactual:   ${JSON.stringify(actualIds)}`);
  }
  commits.forEach((c, i) => {
    const e = entries[i];
    const expectedUrl = upstreamPrUrl(c.id);
    if (c.id === CAPSTONE_HEAD_ID) {
      if (e.current_commit !== 'cpq-head') {
        throw new Error(`${CAPSTONE_HEAD_ID} ledger entry must use current_commit: cpq-head`);
      }
    } else if (e.current_commit !== c.short) {
      throw new Error(`ledger hash mismatch for ${c.id}: expected ${c.short}, got ${e.current_commit}`);
    }
    if ((e.upstream_pr ?? null) !== expectedUrl) {
      throw new Error(`ledger upstream PR mismatch for ${c.id}: expected ${expectedUrl}, got ${e.upstream_pr}`);
    }
  });

  if (!currentHeadSubject().startsWith(`${CAPSTONE_HEAD_ID}:`)) {
    throw new Error(`HEAD is not ${CAPSTONE_HEAD_ID}`);
  }
  const cpqHead = git(['rev-parse', '--verify', 'refs/cpq/head'], { check: false });
  if (cpqHead && cpqHead !== commits.at(-1).sha) {
    throw new Error('refs/cpq/head is stale; run `cpq-checks.mjs rebuild-capstone`');
  }
  const cpqBase = git(['rev-parse', '--verify', 'refs/cpq/base'], { check: false });
  if (cpqBase && cpqBase !== base) {
    throw new Error('refs/cpq/base is stale; run `cpq-checks.mjs rebuild-capstone`');
  }
  console.log('CPQ verification OK');
}

function validateCommitMsgFile(messagePath) {
  const text = fs.readFileSync(messagePath, 'utf8');
  const lines = text.split(/\r?\n/);
  const subject = (lines[0] || '').trim();
  const body = lines.slice(1).join('\n').trim();
  validateCommitBody(subject, body);
}

function preCommit() {
  const staged = git(['diff', '--cached', '--name-only'], { check: false })
    .split('\n').map((l) => l.trim()).filter(Boolean);
  const touched = staged.filter((f) => CPQ_FILES.has(f));
  if (touched.length) {
    process.stderr.write(
      `[cpq] staged CPQ governance changes detected:\n${touched.map((f) => `  - ${f}`).join('\n')}\n`
      + `[cpq] if this mutates the queue, rebuild ${CAPSTONE_HEAD_ID} last before push.\n`,
    );
  }
}

function main(argv) {
  const [cmd, arg] = argv.slice(2);
  try {
    switch (cmd) {
      case 'check-remotes': checkRemotes(); console.log('CPQ remotes OK'); break;
      case 'rebuild-ledger': checkRemotes(); writeLedger(LEDGER); break;
      case 'rebuild-capstone': rebuildCapstone(); break;
      case 'verify': verify(); break;
      case 'pre-commit': preCommit(); break;
      case 'commit-msg':
        if (!arg) throw new Error('commit-msg requires path to commit message file');
        validateCommitMsgFile(arg);
        break;
      default:
        throw new Error(
          'usage: cpq-checks.mjs <check-remotes|rebuild-ledger|rebuild-capstone|verify|pre-commit|commit-msg <file>>',
        );
    }
  } catch (err) {
    console.error(err instanceof Error ? err.message : String(err));
    process.exit(1);
  }
}

main(process.argv);
