// Sentence and word highlights, drawn as absolutely-positioned rects in each page's
// .hl-layer. Positions are percentages of the page in PDF points, so they stay
// aligned when the page is resized. Layers have pointer-events: none.

let index = { byPage: new Map() };

/** @returns {{byPage: Map<number, {sid:string, wordIndex:number, bbox:number[]}[]>}} */
export function buildIndex(script) {
  const byPage = new Map();
  for (const s of script.sentences) {
    s.display.forEach((w, wordIndex) => {
      if (!byPage.has(w.page)) byPage.set(w.page, []);
      byPage.get(w.page).push({ sid: s.id, wordIndex, bbox: w.bbox });
    });
  }
  index = { byPage };
  return index;
}

/** Group words into display lines and merge neighbours on a line into one box. */
function lineBoxes(words) {
  const lines = [];
  for (const w of words) {
    const [x0, y0, x1, y1] = w.bbox;
    const h = y1 - y0;
    const line = lines.find(
      (l) => l.page === w.page && Math.abs((l.y0 + l.y1) / 2 - (y0 + y1) / 2) < 0.5 * Math.max(h, l.y1 - l.y0),
    );
    if (line) line.words.push(w.bbox);
    else lines.push({ page: w.page, y0, y1, words: [w.bbox] });
  }
  const boxes = [];
  for (const l of lines) {
    l.words.sort((a, b) => a[0] - b[0]);
    let cur = null;
    for (const b of l.words) {
      const h = b[3] - b[1];
      if (cur && b[0] - cur[2] <= 1.2 * h) {
        cur[0] = Math.min(cur[0], b[0]);
        cur[1] = Math.min(cur[1], b[1]);
        cur[2] = Math.max(cur[2], b[2]);
        cur[3] = Math.max(cur[3], b[3]);
      } else {
        if (cur) boxes.push({ page: l.page, bbox: cur });
        cur = [...b];
      }
    }
    if (cur) boxes.push({ page: l.page, bbox: cur });
  }
  return boxes;
}

function place(div, bbox, view) {
  const [x0, y0, x1, y1] = bbox;
  div.style.left = `${(x0 / view.width) * 100}%`;
  div.style.top = `${(y0 / view.height) * 100}%`;
  div.style.width = `${((x1 - x0) / view.width) * 100}%`;
  div.style.height = `${((y1 - y0) / view.height) * 100}%`;
}

function layerOf(view) {
  return view.el.querySelector(".hl-layer");
}

function drop(selector) {
  document.querySelectorAll(selector).forEach((n) => n.remove());
}

export function showSentence(sentence, pageViews) {
  drop(".hl-sentence");
  for (const { page, bbox } of lineBoxes(sentence.display)) {
    const view = pageViews[page];
    if (!view) continue;
    const div = document.createElement("div");
    div.className = "hl-sentence";
    div.dataset.sid = sentence.id;
    place(div, bbox, view);
    layerOf(view).append(div);
  }
}

export function showWord(sentence, wordIndex, pageViews) {
  drop(".hl-word");
  const w = sentence.display[wordIndex];
  const view = w && pageViews[w.page];
  if (!view) return;
  const div = document.createElement("div");
  div.className = "hl-word";
  div.dataset.sid = sentence.id;
  place(div, w.bbox, view);
  layerOf(view).append(div);
}

export function clear() {
  drop(".hl-sentence, .hl-word");
}

/** Sentence id of the word nearest (x, y) in PDF points on a page, within 12 pt; else null. */
export function hitTest(pageIndex, x, y) {
  let best = null;
  let bestDist = 12;
  for (const e of index.byPage.get(pageIndex) || []) {
    const [x0, y0, x1, y1] = e.bbox;
    const d = Math.hypot(Math.max(x0 - x, 0, x - x1), Math.max(y0 - y, 0, y - y1));
    if (d <= bestDist) {
      if (best === null || d < bestDist) {
        best = e.sid;
        bestDist = d;
      }
    }
  }
  return best;
}

export function clearWord() {
  drop(".hl-word");
}

export const SKIPPED_TEXT = "Skipped — couldn't read this sentence";

/** Mark a sentence whose clip failed, at its first display word. Kept until reload. */
export function showSkipped(sentence, pageViews) {
  const w = sentence && sentence.display[0];
  const view = w && pageViews[w.page];
  if (!view || document.querySelector(`.skipped-marker[data-sid="${CSS.escape(sentence.id)}"]`)) return;
  const mark = document.createElement("span");
  mark.className = "skipped-marker";
  mark.dataset.sid = sentence.id;
  mark.setAttribute("role", "note");
  mark.setAttribute("aria-label", SKIPPED_TEXT);
  mark.title = SKIPPED_TEXT;
  mark.textContent = "Skipped";
  mark.style.left = `${(w.bbox[0] / view.width) * 100}%`;
  mark.style.top = `${(w.bbox[1] / view.height) * 100}%`;
  layerOf(view).append(mark);
}
