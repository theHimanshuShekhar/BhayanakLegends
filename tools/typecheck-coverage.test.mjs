import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const targets = [
  ["playwright.config.ts", 'const __typecheckCoverageConfigError: string = 123;\n'],
  ["e2e/smoke.spec.ts", 'const __typecheckCoverageE2eError: string = 123;\n'],
];

function runTypecheck() {
  return new Promise((resolveResult, reject) => {
    const child = spawn("pnpm", ["typecheck"], { cwd: root, stdio: "inherit" });
    child.once("error", reject);
    child.once("exit", (code, signal) => resolveResult({ code, signal }));
  });
}

async function assertTypecheckFailsFor(target, declaration) {
  const path = resolve(root, target);
  const original = await readFile(path, "utf8");
  try {
    await writeFile(path, `${declaration}${original}`);
    const result = await runTypecheck();
    assert.notEqual(result.code, 0, `${target} type error was not caught`);
    assert.equal(result.signal, null, `${target} typecheck terminated by signal`);
  } finally {
    await writeFile(path, original);
  }
}

for (const [target, declaration] of targets) {
  await assertTypecheckFailsFor(target, declaration);
}

const cleanResult = await runTypecheck();
assert.equal(cleanResult.code, 0, "clean typecheck should pass");
assert.equal(cleanResult.signal, null, "clean typecheck terminated by signal");
console.log("typecheck coverage mutations were rejected and clean typecheck passed");
