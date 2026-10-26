import { listPacks, uploadPdf } from "./api.js";

const list = document.getElementById("pack-list");
const empty = document.getElementById("empty");
const message = document.getElementById("message");
const drop = document.getElementById("drop");
const input = document.getElementById("file-input");
let timer = null;

function say(text, isError) {
  message.textContent = text;
  message.classList.toggle("error", !!isError);
}

function describe(e) {
  return e && e.offline
    ? "Can't reach the Storyteller server. Is it still running?"
    : (e && e.message) || "Something went wrong.";
}

function packItem(p) {
  const li = document.createElement("li");
  li.className = "pack";
  li.dataset.packId = p.id;

  const info = document.createElement("div");
  info.className = "pack-info";
  const h = document.createElement("h2");
  h.textContent = p.title;
  const meta = document.createElement("p");
  meta.className = "pack-meta";
  meta.textContent = `${p.page_count} pages · ${p.filename}`;
  const prog = document.createElement("p");
  prog.className = "pack-progress";
  prog.textContent = `Audio ready: ${p.rendered}/${p.total}`;
  const bar = document.createElement("progress");
  bar.max = Math.max(p.total, 1);
  bar.value = p.rendered;
  bar.setAttribute("aria-label", `Audio prepared for ${p.title}`);
  info.append(h, meta, prog, bar);

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "primary";
  btn.textContent = p.position ? "Resume" : "Start";
  btn.setAttribute("aria-label", `${btn.textContent} ${p.title}`);
  btn.addEventListener("click", () => {
    location.href = `/read/${encodeURIComponent(p.id)}`;
  });
  li.append(info, btn);
  return li;
}

async function refresh() {
  clearTimeout(timer);
  try {
    const packs = await listPacks();
    list.replaceChildren(...packs.map(packItem));
    empty.hidden = packs.length > 0;
    if (packs.some((p) => p.rendered < p.total)) timer = setTimeout(refresh, 4000);
  } catch (e) {
    say(describe(e), true);
  }
}

async function addFile(file) {
  if (!file) return;
  say(`Adding ${file.name}…`, false);
  try {
    await uploadPdf(file);
    say(`Added ${file.name}.`, false);
    await refresh();
  } catch (e) {
    say(describe(e), true);
  }
}

drop.addEventListener("click", () => input.click());
drop.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    input.click();
  }
});
input.addEventListener("change", () => {
  addFile(input.files[0]);
  input.value = "";
});
for (const t of ["dragenter", "dragover"]) {
  drop.addEventListener(t, (e) => {
    e.preventDefault();
    drop.classList.add("over");
  });
}
for (const t of ["dragleave", "drop"]) {
  drop.addEventListener(t, (e) => {
    e.preventDefault();
    drop.classList.remove("over");
  });
}
drop.addEventListener("drop", (e) => addFile(e.dataTransfer.files[0]));

refresh();
