// Reader page: loads the pack, renders pages, and wires the player to the
// highlights, auto-scroll, progress readouts and the offline banner.
// Nothing plays until the user clicks a sentence or presses Play.
import { getScript, getSettings, getStatus, listPacks, pdfUrl } from "./api.js";
import { renderPages } from "./pages.js";
import { buildIndex, clearWord, hitTest, showSentence, showSkipped, showWord, SKIPPED_TEXT } from "./highlight.js";
import { Player } from "./player.js";

const SECONDS_PER_CHAR = 0.06; // estimate for clips not fetched yet (≈ Kokoro at 1.0×)
const STATUS_POLL_MS = 3000;
const SCROLL_KEYS = new Set(["PageUp", "PageDown", "Home", "End"]);

const $ = (id) => document.getElementById(id);
const packId = decodeURIComponent(location.pathname.split("/").pop());
const pagesEl = $("pages");
const scroller = document.querySelector(".centre");
const errorEl = $("error");
const reconnectEl = $("reconnect");
const announceEl = $("announce");
const playBtn = $("play");
const speedEl = $("speed");
const progressEl = $("progress");
const remainingEl = $("remaining");
const backBtn = $("back-to-reading");

// A file dropped on the reader must not navigate away from it.
for (const t of ["dragover", "drop"]) window.addEventListener(t, (e) => e.preventDefault());

// ---- connection ------------------------------------------------------------

let reloadOnReconnect = false;

function showOffline() {
  reconnectEl.hidden = false;
}

function showOnline() {
  if (reconnectEl.hidden) return;
  reconnectEl.hidden = true;
  if (reloadOnReconnect) location.reload();
}

// Heartbeat every 3 s: notices a stopped server even while idle, and hides the
// banner as soon as the server answers again.
async function pollStatus() {
  try {
    await getStatus();
    showOnline();
  } catch (e) {
    if (e && e.offline) showOffline();
  }
  setTimeout(pollStatus, STATUS_POLL_MS);
}
setTimeout(pollStatus, STATUS_POLL_MS);

// ---- readouts --------------------------------------------------------------

/** m:ss, or h:mm:ss from an hour up. */
export function formatTime(seconds) {
  const t = Math.max(0, Math.round(seconds));
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const ss = String(t % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

let script = null;
let pageViews = [];
let player = null;
let byId = new Map();
let indexOf = new Map();
let charCounts = [];
let followMode = true;

function updateProgress() {
  const n = script.sentences.length;
  const i = player.current ? indexOf.get(player.current) : 0;
  progressEl.value = n ? i / n : 0;
  let seconds = 0;
  for (let k = i; k < n; k++) {
    const known = player.knownDuration(script.sentences[k].id);
    seconds += known ?? SECONDS_PER_CHAR * charCounts[k];
  }
  remainingEl.textContent = formatTime(seconds / player.speed);
}

function updateSpeed() {
  speedEl.textContent = `${player.speed.toFixed(2)}×`;
  updateProgress();
}

function setSpeed(x) {
  player.setSpeed(x);
  updateSpeed();
}

function announce(text) {
  announceEl.textContent = "";
  requestAnimationFrame(() => (announceEl.textContent = text));
}

// ---- auto-scroll -----------------------------------------------------------

const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");

/** Keep the current sentence's first box between 25 % and 60 % of the viewport. */
function scrollToCurrent(force) {
  const sid = player && player.current;
  if (!sid || pagesEl.hidden) return;
  const el = pagesEl.querySelector(`.hl-sentence[data-sid="${CSS.escape(sid)}"]`);
  if (!el) return;
  const top = el.getBoundingClientRect().top - scroller.getBoundingClientRect().top;
  const h = scroller.clientHeight;
  if (!force && top >= 0.25 * h && top <= 0.6 * h) return;
  // Programmatic: user-scroll detection listens to input events, not 'scroll',
  // so this never switches follow mode off.
  scroller.scrollTo({ top: scroller.scrollTop + top - 0.3 * h, behavior: reducedMotion.matches ? "auto" : "smooth" });
}

function setFollow(on) {
  followMode = on;
  backBtn.hidden = on || !(player && player.current);
}

function userScrolled() {
  if (followMode) setFollow(false);
}

scroller.addEventListener("wheel", userScrolled, { passive: true });
scroller.addEventListener("touchmove", userScrolled, { passive: true });
// Dragging the scrollbar: a pointerdown on the scroller itself, right of its content box.
scroller.addEventListener("pointerdown", (e) => {
  if (e.target === scroller && e.offsetX >= scroller.clientWidth) userScrolled();
});
window.addEventListener("keydown", (e) => {
  if (SCROLL_KEYS.has(e.key) && (scroller.contains(e.target) || e.target === document.body)) userScrolled();
});
backBtn.addEventListener("click", () => {
  setFollow(true);
  scrollToCurrent(true);
});

// ---- player callbacks ------------------------------------------------------

function onSentence(sid) {
  clearWord();
  showSentence(byId.get(sid), pageViews);
  updateProgress();
  if (followMode) scrollToCurrent(false);
  else backBtn.hidden = false;
}

function onWord(sid, i) {
  showWord(byId.get(sid), i, pageViews);
}

function onState(state) {
  const busy = state === "playing" || state === "loading";
  playBtn.textContent = busy ? "Pause" : "Play";
  playBtn.setAttribute("aria-label", busy ? "Pause" : "Play");
  document.body.dataset.state = state;
  if (state === "playing") updateProgress(); // the clip's real duration is known now
}

function onError(sid) {
  showSkipped(byId.get(sid), pageViews);
  announce(SKIPPED_TEXT);
}

// ---- load ------------------------------------------------------------------

function fail(e) {
  if (e && e.offline) {
    reloadOnReconnect = true;
    showOffline();
    return;
  }
  errorEl.textContent = (e && e.message) || "Could not open this pack.";
  errorEl.hidden = false;
}

try {
  const [s, settings, packs] = await Promise.all([
    getScript(packId),
    getSettings().catch(() => null),
    listPacks().catch(() => null),
  ]);
  script = s;
  if (settings) {
    document.documentElement.style.setProperty("--sentence-color", settings.sentence_color);
    document.documentElement.style.setProperty("--word-color", settings.word_color);
  }
  document.title = `${script.title} - Storyteller`;
  buildIndex(script);
  byId = new Map(script.sentences.map((x) => [x.id, x]));
  indexOf = new Map(script.sentences.map((x, i) => [x.id, i]));
  charCounts = script.sentences.map((x) => x.spoken.map((w) => w.text).join(" ").length);
  pageViews = await renderPages(pagesEl, pdfUrl(packId));

  player = new Player({ packId, script, onSentence, onWord, onState, onError, onOffline: showOffline });
  setSpeed(settings ? settings.speed : 1);
  window.__player = player;
  window.__storyteller = { script, pageViews, hitTest, player, setSpeed, scrollToCurrent };

  const position = packs && packs.find((p) => p.id === packId)?.position;
  if (position && byId.has(position)) player.cue(position); // restored, never played

  pagesEl.addEventListener("click", (e) => {
    const el = e.target.closest(".page");
    if (!el) return;
    const view = pageViews[Number(el.dataset.page)];
    const r = el.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * view.width;
    const y = ((e.clientY - r.top) / r.height) * view.height;
    const sid = hitTest(view.pageIndex, x, y);
    if (!sid) return;
    setFollow(true);
    player.playFrom(sid);
  });
  playBtn.addEventListener("click", () => player.toggle());
  window.addEventListener("pagehide", () => player.flushPosition());
  playBtn.disabled = script.sentences.length === 0;
} catch (e) {
  fail(e);
}
