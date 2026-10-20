// A small MCP client for the browser: JSON-RPC over Streamable HTTP.
// The evening screen runs entirely through these calls, the same way an
// Alexa+ add-on host would call the server.
(function () {
  const PROTOCOL = "2025-11-25";
  let nextId = 1;
  const listeners = [];

  async function rpc(method, params) {
    const id = nextId++;
    const started = performance.now();
    const res = await fetch("/mcp", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTOCOL,
      },
      body: JSON.stringify({ jsonrpc: "2.0", id, method, params }),
    });
    const text = await res.text();
    let body;
    try { body = JSON.parse(text); } catch (e) { throw new Error(`MCP ${res.status}: ${text.slice(0, 200)}`); }
    if (!res.ok && !body.jsonrpc) throw new Error(body.detail || `MCP ${res.status}`);
    const entry = { method, params, ms: Math.round(performance.now() - started), body };
    listeners.forEach((fn) => fn(entry));
    if (body.error) throw new Error(body.error.message || "MCP error");
    return body.result;
  }

  function payload(result) {
    if (result.isError) {
      const msg = (result.content || []).map((c) => c.text).join(" ");
      throw new Error(msg || "tool failed");
    }
    let sc = result.structuredContent;
    if (sc && Object.keys(sc).length === 1 && "result" in sc) sc = sc.result;
    if (sc) return sc;
    const t = (result.content || []).find((c) => c.type === "text");
    return t ? JSON.parse(t.text) : {};
  }

  window.MCP = {
    protocol: PROTOCOL,
    onCall: (fn) => listeners.push(fn),
    init: () => rpc("initialize", {
      protocolVersion: PROTOCOL,
      capabilities: {},
      clientInfo: { name: "memory-lane-echo-show", version: "1.0" },
    }),
    tools: () => rpc("tools/list", {}),
    call: async (name, args = {}) => payload(await rpc("tools/call", { name, arguments: args })),
  };
})();
