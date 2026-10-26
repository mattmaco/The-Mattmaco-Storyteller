// pdf.js page rendering. Each page is a <div class="page" data-page="N"> sized
// from the page's real viewport, with a lazily-drawn canvas and a highlight layer.
import * as pdfjs from "../vendor/pdfjs/pdf.mjs";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("../vendor/pdfjs/pdf.worker.mjs", import.meta.url).href;

function scrollRoot(el) {
  for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
    const o = getComputedStyle(p).overflowY;
    if (o === "auto" || o === "scroll") return p;
  }
  return null;
}

/**
 * @returns {Promise<{pageIndex:number, el:HTMLElement, scale:number, width:number, height:number}[]>}
 * width/height are the page size in PDF points; scale = el.clientWidth / width (pixels per point).
 */
export async function renderPages(container, pdfUrl) {
  const pdf = await pdfjs.getDocument({ url: pdfUrl }).promise;
  container.replaceChildren();
  const views = [];

  for (let i = 0; i < pdf.numPages; i++) {
    const page = await pdf.getPage(i + 1);
    const vp = page.getViewport({ scale: 1 });
    const el = document.createElement("div");
    el.className = "page";
    el.dataset.page = String(i);
    el.setAttribute("role", "img");
    el.setAttribute("aria-label", `Page ${i + 1} of ${pdf.numPages}`);
    el.style.aspectRatio = `${vp.width} / ${vp.height}`;
    const layer = document.createElement("div");
    layer.className = "hl-layer";
    el.append(layer);
    container.append(el);
    views.push({ pageIndex: i, el, scale: 1, width: vp.width, height: vp.height, page, drawnAt: 0, task: null });
  }

  const measure = () => {
    for (const v of views) v.scale = v.el.clientWidth / v.width;
  };

  function release(v) {
    if (v.task) v.task.cancel();
    v.task = null;
    v.drawnAt = 0;
    v.el.querySelector("canvas")?.remove();
    delete v.el.dataset.rendered;
  }

  async function draw(v) {
    const px = v.el.clientWidth;
    if (!px) return;
    const dpr = window.devicePixelRatio || 1;
    const target = Math.round(px * dpr);
    if (v.drawnAt === target) return;
    v.drawnAt = target;
    if (v.task) v.task.cancel();
    const viewport = v.page.getViewport({ scale: target / v.width });
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(viewport.width);
    canvas.height = Math.round(viewport.height);
    const task = v.page.render({ canvasContext: canvas.getContext("2d"), viewport });
    v.task = task;
    try {
      await task.promise;
    } catch (e) {
      if (e && e.name === "RenderingCancelledException") return;
      v.drawnAt = 0;
      throw e;
    }
    if (v.task !== task) return;
    v.task = null;
    v.el.querySelector("canvas")?.remove();
    v.el.prepend(canvas);
    v.el.dataset.rendered = "true";
  }

  // Observe against the scrolling ancestor: with the viewport as root, the
  // scroller's clipping would make rootMargin useless.
  const root = scrollRoot(container);
  const visible = new Set();
  const io = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        const v = views[Number(e.target.dataset.page)];
        if (e.isIntersecting) {
          visible.add(v);
          draw(v).catch(() => {});
        } else {
          visible.delete(v);
        }
      }
    },
    { root, rootMargin: "800px 0px" },
  );
  views.forEach((v) => io.observe(v.el));

  // Free canvases of pages more than 3 viewport heights away; they redraw on return.
  const keep = new IntersectionObserver(
    (entries) => {
      for (const e of entries) if (!e.isIntersecting) release(views[Number(e.target.dataset.page)]);
    },
    { root, rootMargin: "300% 0px" },
  );
  views.forEach((v) => keep.observe(v.el));

  let pending = 0;
  new ResizeObserver(() => {
    measure();
    clearTimeout(pending);
    pending = setTimeout(() => visible.forEach((v) => draw(v).catch(() => {})), 150);
  }).observe(container);

  measure();
  return views;
}
