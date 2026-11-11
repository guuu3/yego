#!/usr/bin/env node
/**
 * codex-bridge.mjs — Claude Code から ChatGPT (Codex CLI) を呼ぶための
 * 依存ゼロの MCP ブリッジ (stdio / JSON-RPC).
 *
 * 仕組み:
 *   Claude Code ──MCP(stdio)──> このブリッジ ──`codex exec`──> ChatGPTプランのCodex
 *
 * 公式 `codex mcp-server` が使える環境ではそちらが本命。このブリッジは
 * `mcp-server` サブコマンドが無い Codex ビルド (例: 0.164.0-alpha 系) でも
 * `codex exec -o <file>` だけで確実に動くためのフォールバック。
 *
 * 前提:
 *   - `codex` が PATH にあること
 *   - `codex login` (ChatGPTサインイン) が済んでいること
 *     未ログイン時はツール結果にログイン手順が返る。
 *
 * 環境変数:
 *   CODEX_BRIDGE_MODEL    既定モデル (例: "gpt-5.3-codex")。未指定なら Codex の既定。
 *   CODEX_BRIDGE_TIMEOUT_MS  1回の呼び出しの上限 (既定 600000 = 10分)
 */

import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline";

const TIMEOUT_MS = Number(process.env.CODEX_BRIDGE_TIMEOUT_MS || 600_000);
const DEFAULT_MODEL = process.env.CODEX_BRIDGE_MODEL || null;

const TOOLS = [
  {
    name: "codex_ask",
    description:
      "ChatGPT (Codex) に独立した第二意見を求める。コードレビュー、設計相談、" +
      "バグの原因推定など、Claude とは別のモデルの視点が欲しいときに使う。" +
      "Codex は読み取り専用サンドボックスでリポジトリを参照できる。",
    inputSchema: {
      type: "object",
      properties: {
        prompt: { type: "string", description: "Codex への依頼文 (具体的に)" },
        model: { type: "string", description: "任意: モデル名の上書き" },
      },
      required: ["prompt"],
    },
  },
  {
    name: "codex_review",
    description:
      "現在の git diff (未コミット変更) を ChatGPT (Codex) にレビューさせる。" +
      "変更の提出前に、別モデルの目で問題を洗い出す用途。",
    inputSchema: {
      type: "object",
      properties: {
        focus: {
          type: "string",
          description: "任意: 特に見てほしい観点 (例: セキュリティ、後方互換)",
        },
      },
    },
  },
];

function runCodex(prompt, model) {
  return new Promise((resolve) => {
    const dir = mkdtempSync(join(tmpdir(), "codex-bridge-"));
    const outFile = join(dir, "last-message.txt");
    const args = ["exec", "--sandbox", "read-only", "-o", outFile];
    const useModel = model || DEFAULT_MODEL;
    if (useModel) args.push("-m", useModel);
    args.push(prompt);

    const child = spawn("codex", args, {
      cwd: process.cwd(),
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stderr = "";
    child.stderr.on("data", (d) => (stderr += d.toString()));
    child.stdout.on("data", () => {}); // 進捗出力は捨てる (最終回答は -o ファイルから取る)

    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      cleanup();
      resolve({
        ok: false,
        text: `Codex の呼び出しがタイムアウトしました (${Math.round(TIMEOUT_MS / 1000)}秒)。依頼を短く分けて再試行してください。`,
      });
    }, TIMEOUT_MS);

    function cleanup() {
      clearTimeout(timer);
      try { rmSync(dir, { recursive: true, force: true }); } catch {}
    }

    child.on("error", (err) => {
      cleanup();
      resolve({
        ok: false,
        text: `codex コマンドを起動できませんでした: ${err.message}\nCodex CLI がインストールされ PATH にあるか確認してください。`,
      });
    });

    child.on("close", (code) => {
      let last = "";
      try { last = readFileSync(outFile, "utf8").trim(); } catch {}
      cleanup();
      if (last) return resolve({ ok: code === 0, text: last });
      // 最終メッセージが取れない場合は stderr 末尾を手がかりに返す
      const tail = stderr.trim().split("\n").slice(-8).join("\n");
      const loginHint = /not logged in|login|auth/i.test(tail)
        ? "\n\n→ まずターミナルで `codex login --device-auth` を実行し、ChatGPT にサインインしてください。"
        : "";
      resolve({
        ok: false,
        text: `Codex から回答が返りませんでした (exit=${code})。\n${tail}${loginHint}`,
      });
    });
  });
}

async function handleCall(name, args = {}) {
  if (name === "codex_ask") {
    if (!args.prompt || typeof args.prompt !== "string") {
      return { ok: false, text: "prompt が必要です。" };
    }
    return runCodex(args.prompt, args.model);
  }
  if (name === "codex_review") {
    const focus = args.focus ? `\n特に次の観点を重点的に見てください: ${args.focus}` : "";
    const prompt =
      "あなたはシニアコードレビュアーです。現在のリポジトリの git diff " +
      "(未コミットの変更) を確認し、バグ・セキュリティ・後方互換・テスト不足の観点で " +
      "具体的な問題点だけを、ファイル名と該当箇所を添えて指摘してください。" +
      "問題がなければその旨を明言してください。" + focus;
    return runCodex(prompt, args.model);
  }
  return { ok: false, text: `未知のツールです: ${name}` };
}

// ---- MCP (stdio, newline-delimited JSON-RPC) ----
const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });

function send(obj) {
  process.stdout.write(JSON.stringify(obj) + "\n");
}

rl.on("line", async (line) => {
  const trimmed = line.trim();
  if (!trimmed) return;
  let msg;
  try { msg = JSON.parse(trimmed); } catch { return; }

  const { id, method, params } = msg;
  const isNotification = id === undefined || id === null;

  try {
    switch (method) {
      case "initialize":
        send({
          jsonrpc: "2.0",
          id,
          result: {
            protocolVersion: params?.protocolVersion || "2025-03-26",
            capabilities: { tools: {} },
            serverInfo: { name: "codex-bridge", version: "1.0.0" },
          },
        });
        break;
      case "ping":
        if (!isNotification) send({ jsonrpc: "2.0", id, result: {} });
        break;
      case "tools/list":
        send({ jsonrpc: "2.0", id, result: { tools: TOOLS } });
        break;
      case "tools/call": {
        const result = await handleCall(params?.name, params?.arguments || {});
        send({
          jsonrpc: "2.0",
          id,
          result: {
            content: [{ type: "text", text: result.text }],
            isError: !result.ok,
          },
        });
        break;
      }
      default:
        if (!isNotification) {
          send({
            jsonrpc: "2.0",
            id,
            error: { code: -32601, message: `Method not found: ${method}` },
          });
        }
    }
  } catch (err) {
    if (!isNotification) {
      send({
        jsonrpc: "2.0",
        id,
        error: { code: -32603, message: String(err?.message || err) },
      });
    }
  }
});
