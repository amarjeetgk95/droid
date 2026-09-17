/**
 * Design-system gate.
 *
 * Runs ESLint over `src/` using the normal config, but fails **only** on
 * violations of the `droid/*` rules (registered in `eslint.config.mjs` from
 * the local `eslint-rules/` plugin). Everything else is reported as advisory.
 *
 * Why: the repo carries pre-existing debt from `react-hooks/*` and
 * `@typescript-eslint/no-explicit-any` (~200 errors). Gating CI on the full
 * lint output would mean the design-system rules never actually run. This lets
 * the guardrails bite from day one while the unrelated debt is paid down
 * separately — and `npm run lint` still shows the whole picture.
 *
 * Self-check: the gate refuses to run if no `droid/*` rule is present in the
 * resolved ESLint config. Previously `droid/*` rules did not exist, so the
 * gate passed vacuously while reporting "0 violations".
 *
 * Usage: npm run lint:design
 */

import { ESLint } from "eslint";

const DESIGN_PREFIX = "droid/";
// Real file inside src/ — used only to resolve the config.
const PROBE_FILE = "src/app/layout.tsx";

const eslint = new ESLint();

// ── Self-check: fail loudly if the design rules are not wired up. ─────────
let probeConfig;
try {
  probeConfig = await eslint.calculateConfigForFile(PROBE_FILE);
} catch (error) {
  console.error(
    `Design-system gate misconfigured: could not resolve ESLint config for ${PROBE_FILE}.`,
  );
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
}

const configuredDroidRules = Object.entries(probeConfig?.rules ?? {})
  .filter(([rule]) => rule.startsWith(DESIGN_PREFIX))
  .map(([rule, severity]) => {
    const level = Array.isArray(severity) ? severity[0] : severity;
    return { rule, level };
  });

if (configuredDroidRules.length === 0) {
  console.error(
    "Design-system gate misconfigured: no `droid/*` ESLint rules are registered.\n" +
      "Expected the local plugin from `eslint-rules/` to be wired up in `eslint.config.mjs` " +
      "for `src/**/*.{ts,tsx}` (at minimum `droid/no-palette-class` and `droid/no-raw-hex`).\n" +
      "Refusing to report success vacuously.",
  );
  process.exit(1);
}

const enabled = configuredDroidRules.filter((r) => r.level === 2 || r.level === "error");
if (enabled.length === 0) {
  console.error(
    "Design-system gate misconfigured: `droid/*` rules are registered but none are enabled " +
      `as errors (${configuredDroidRules.map((r) => `${r.rule}=${r.level}`).join(", ")}).`,
  );
  process.exit(1);
}

// ── Lint ──────────────────────────────────────────────────────────────────
const results = await eslint.lintFiles(["src"]);

const designErrors = [];
let advisoryErrors = 0;
let advisoryWarnings = 0;

for (const file of results) {
  for (const message of file.messages) {
    const rule = message.ruleId ?? "";
    if (rule.startsWith(DESIGN_PREFIX)) {
      if (message.severity === 2) designErrors.push({ file, message });
      continue;
    }
    if (message.severity === 2) advisoryErrors += 1;
    else advisoryWarnings += 1;
  }
}

const formatter = await eslint.loadFormatter("stylish");

if (designErrors.length > 0) {
  const scoped = designErrors.map(({ file, message }) => ({
    filePath: file.filePath,
    messages: [message],
    errorCount: 1,
    warningCount: 0,
    fixableErrorCount: 0,
    fixableWarningCount: 0,
  }));
  console.error(await formatter.format(scoped));
  const files = new Set(designErrors.map(({ file }) => file.filePath));
  console.error(
    `\nDesign-system gate FAILED: ${designErrors.length} droid/* violation(s) across ` +
      `${files.size} file(s). Rules active: ${enabled.map((r) => r.rule).join(", ")}.`,
  );
  console.error(
    "Use a design token from globals.css, or a semantic utility " +
      "(up / down / warn / accent, each with -wash, -line, -strong).",
  );
  process.exit(1);
}

console.log(
  `Design-system gate passed — 0 droid/* violations across ${results.length} files ` +
    `(rules: ${enabled.map((r) => r.rule).join(", ")}).`,
);
if (advisoryErrors > 0 || advisoryWarnings > 0) {
  console.log(
    `Advisory (not gating): ${advisoryErrors} error(s), ${advisoryWarnings} warning(s) ` +
      "from other rules. Run `npm run lint` for detail.",
  );
}
