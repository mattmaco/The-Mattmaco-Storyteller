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
  return res.status === 204 ? null : res.json();
}

function sendJson(method, url, body) {
  return request(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
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
export const savePosition = (id, sid) => sendJson("PUT", `${pack(id)}/position`, { sentence_id: sid });
export const getSettings = () => request("/api/settings");
export const putSettings = (partial) => sendJson("PUT", "/api/settings", partial);
export const getStatus = () => request("/api/status");
export const pdfUrl = (id) => `${pack(id)}/pdf`;
