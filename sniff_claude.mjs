/**
 * Claude Code 请求拦截代理
 *
 * 拦截 Claude Code 发往 Anthropic API 的请求，记录完整请求体后转发到真实 API。
 *
 * 使用方式：
 *   1. node sniff_claude.mjs
 *   2. 在 Claude Code 的 settings.json 中设置：
 *      "ANTHROPIC_BASE_URL": "http://127.0.0.1:9999"
 *   3. 重启 Claude Code
 *
 * 所有请求的完整 body（含 messages、model、tools 等）会被打印并保存到 sniff_log.jsonl
 */

import http from "node:http";
import https from "node:https";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PROXY_PORT = 9999;
const TARGET_HOST = "api.anthropic.com";
const TARGET_PORT = 443;
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const LOG_FILE = path.join(__dirname, "sniff_log.jsonl");

let reqCount = 0;

const server = http.createServer((clientReq, clientRes) => {
  reqCount++;
  const reqId = reqCount;
  const timestamp = new Date().toISOString();

  const chunks = [];
  clientReq.on("data", (c) => chunks.push(c));
  clientReq.on("end", () => {
    const body = Buffer.concat(chunks).toString("utf-8");

    // 解析请求体
    let parsed = null;
    try {
      parsed = JSON.parse(body);
    } catch {}

    // 打印到控制台
    console.log(`\n${"═".repeat(60)}`);
    console.log(`[#${reqId}] ${timestamp}`);
    console.log(`${clientReq.method} ${clientReq.url}`);
    console.log(`─`.repeat(60));

    // 打印关键 headers（脱敏）
    const headers = { ...clientReq.headers };
    for (const key of ["authorization", "x-api-key", "cookie"]) {
      if (headers[key]) headers[key] = headers[key].slice(0, 15) + "***";
    }
    console.log(`Headers:`, JSON.stringify(headers, null, 2));

    // 打印请求体
    if (parsed) {
      console.log(`\n📦 Body (${body.length} bytes):`);
      console.log(`  model: ${parsed.model || "(无)"}`);
      console.log(`  stream: ${parsed.stream}`);
      console.log(`  max_tokens: ${parsed.max_tokens}`);
      if (parsed.system) {
        const sys = typeof parsed.system === "string" ? parsed.system : JSON.stringify(parsed.system);
        console.log(`  system: ${sys.slice(0, 300)}${sys.length > 300 ? "..." : ""}`);
      }
      if (parsed.messages) {
        console.log(`  messages: ${parsed.messages.length} 条`);
        parsed.messages.forEach((m, i) => {
          const content = typeof m.content === "string"
            ? m.content
            : JSON.stringify(m.content);
          console.log(`    [${i}] ${m.role}: ${content.slice(0, 200)}${content.length > 200 ? "..." : ""}`);
        });
      }
      if (parsed.tools) {
        console.log(`  tools: ${parsed.tools.length} 个`);
        parsed.tools.forEach((t, i) => {
          console.log(`    [${i}] ${t.name}: ${t.description?.slice(0, 80) || ""}`);
        });
      }
      // 完整 body 输出
      console.log(`\n📋 完整请求体:`);
      console.log(JSON.stringify(parsed, null, 2));
    } else {
      console.log(`Body (raw): ${body.slice(0, 3000)}`);
    }
    console.log(`${"═".repeat(60)}\n`);

    // 写入日志文件
    const logEntry = JSON.stringify({
      id: reqId,
      timestamp,
      method: clientReq.method,
      url: clientReq.url,
      headers: Object.fromEntries(
        Object.entries(headers).filter(([k]) => !["authorization", "x-api-key", "cookie"].includes(k))
      ),
      body: parsed || body,
    });
    fs.appendFileSync(LOG_FILE, logEntry + "\n", "utf-8");

    // 转发到真实 Anthropic API
    const forwardHeaders = { ...clientReq.headers };
    forwardHeaders["host"] = TARGET_HOST;
    delete forwardHeaders["transfer-encoding"];

    const proxyReq = https.request(
      {
        hostname: TARGET_HOST,
        port: TARGET_PORT,
        path: clientReq.url,
        method: clientReq.method,
        headers: forwardHeaders,
      },
      (proxyRes) => {
        console.log(`[#${reqId}] 📥 响应: ${proxyRes.statusCode}`);

        // 处理 SSE stream
        const isStream = proxyRes.headers["content-type"]?.includes("text/event-stream");

        clientRes.writeHead(proxyRes.statusCode, proxyRes.headers);

        if (isStream) {
          let eventCount = 0;
          proxyRes.on("data", (chunk) => {
            eventCount++;
            const text = chunk.toString();
            // 记录 stream 事件
            const lines = text.split("\n").filter((l) => l.startsWith("data: "));
            for (const line of lines) {
              const data = line.slice(6);
              if (data === "[DONE]") continue;
              try {
                const evt = JSON.parse(data);
                if (evt.type === "content_block_delta" && evt.delta?.text) {
                  process.stdout.write(evt.delta.text);
                }
                if (evt.type === "message_stop") {
                  console.log(`\n[#${reqId}] ✅ Stream 结束 (${eventCount} 个事件)`);
                }
              } catch {}
            }
          });
        } else {
          const resChunks = [];
          proxyRes.on("data", (c) => resChunks.push(c));
          proxyRes.on("end", () => {
            const resBody = Buffer.concat(resChunks).toString("utf-8");
            console.log(`[#${reqId}] 📥 响应体 (${resBody.length} bytes)`);
            try {
              const r = JSON.parse(resBody);
              if (r.content) {
                console.log(`[#${reqId}] 回复: ${JSON.stringify(r.content).slice(0, 300)}`);
              }
              if (r.usage) {
                console.log(`[#${reqId}] tokens: in=${r.usage.input_tokens} out=${r.usage.output_tokens}`);
              }
            } catch {}
          });
        }

        proxyRes.pipe(clientRes);
      }
    );

    proxyReq.on("error", (e) => {
      console.error(`[#${reqId}] ❌ 转发失败: ${e.message}`);
      clientRes.writeHead(502);
      clientRes.end(JSON.stringify({ error: e.message }));
    });

    if (body) proxyReq.write(body);
    proxyReq.end();
  });

  clientReq.on("error", (e) => {
    console.error(`[#${reqId}] 客户端请求错误: ${e.message}`);
  });
});

server.listen(PROXY_PORT, () => {
  console.log(`
╔════════════════════════════════════════════════════════════════╗
║              🔍 Claude Code 请求拦截代理                        ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  监听端口: ${PROXY_PORT}                                                ║
║  日志文件: sniff_log.jsonl                                     ║
║                                                                ║
║  使用步骤:                                                     ║
║    1. 打开 Claude Code settings.json                           ║
║    2. 添加: "ANTHROPIC_BASE_URL": "http://127.0.0.1:${PROXY_PORT}"    ║
║    3. 重启 Claude Code                                         ║
║                                                                ║
║  所有请求的完整 body 会打印在此并保存到日志文件                  ║
║  Ctrl+C 停止                                                   ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
`);
});
