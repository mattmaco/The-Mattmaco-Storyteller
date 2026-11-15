// Thin fetch wrappers for the Storyteller server. Network failures reject with
// {offline: true}; HTTP errors reject with {status, error, message}.

async function request(url, options) {
  let res;
  try {
    res = await fetch(url, options);
  } catch (e) {
    throw { offline: true };
  }
  if (!res.ok) {
    let body = {};
    try {
      body = await res.json();
    } catch (e) {
      /* non-JSON error body */
    }
    const detail = typeof body.detail === "string" ? body.detail : "";
    throw {
      status: res.status,
      error: body.error || "http_error",
      message: body.message || detail || `Request failed (${res.status})`,
    };
  }
  if (res.status === 204) return null;
  try {
    return await res.json();
  } catch (e) {
    throw { offline: true }; // connection dropped (or garbage) while reading the body
  }
}

function sendJson(method, url, body, extra) {
  return request(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    ...extra,
  });
}

const pack = (id) => `/api/packs/${encodeURIComponent(id)}`;

export const listPacks = () => request("/api/packs");

export function uploadPdf(file) {
  const form = new FormData();
  form.append("file", file, file.name);
  return request("/api/packs", { method: "POST", body: form });
}

export const getScript = (id) => request(`${pack(id)}/script`);
export const getClip = (id, sid) => request(`${pack(id)}/clip/${encodeURIComponent(sid)}`);
export const focus = (id, sid) => sendJson("POST", `${pack(id)}/focus`, { sentence_id: sid });
/** `keepalive: true` lets the save finish while the page unloads. */
export const savePosition = (id, sid, { keepalive = false } = {}) =>
  sendJson("PUT", `${pack(id)}/position`, { sentence_id: sid }, keepalive ? { keepalive: true } : undefined);
export const getSettings = () => request("/api/settings");
export const putSettings = (partial) => sendJson("PUT", "/api/settings", partial);
export const getStatus = () => request("/api/status");
export const pdfUrl = (id) => `${pack(id)}/pdf`;
