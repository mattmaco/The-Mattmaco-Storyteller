// Read-along player. One <audio> element, one active request at a time: every
// navigation bumps a private token, and every async continuation (clip fetch,
// play(), 'ended', pause timers) checks it and exits without side effects when
// stale. That is what keeps two clips from ever playing at once.
import { getClip, getStatus, focus, savePosition } from "./api.js";

const PREFETCH = 3;
const SKIP_DELAY_MS = 300;
const SAVE_DEBOUNCE_MS = 2000;
export const MIN_SPEED = 0.75;
export const MAX_SPEED = 2.0;

const noop = () => {};

export class Player {
  #packId;
  #sentences;
  #indexOf = new Map(); // sid -> index
  #cb;
  #audio;
  #token = 0;
  #playToken = -1; // token that owns the audio currently loaded / playing
  #state = "idle";
  #cur = null; // current sid
  #loaded = null; // sid whose clip is in #audio
  #clip = null; // clip data for #loaded
  #wordShown = -1;
  #timer = 0; // pause-after / skip timer
  #raf = 0;
  #speed = 1;
  #clips = new Map(); // sid -> Promise<clip>
  #durations = new Map(); // sid -> seconds at speed 1
  #saveTimer = 0;
  #pendingSave = null;

  /**
   * @param {{packId:string, script:object, onSentence?:(sid:string)=>void,
   *   onWord?:(sid:string, displayIndex:number)=>void, onState?:(state:string)=>void,
   *   onError?:(sid:string)=>void, onOffline?:(err:object)=>void}} opts
   */
  constructor({ packId, script, onSentence, onWord, onState, onError, onOffline }) {
    this.#packId = packId;
    this.#sentences = script.sentences;
    this.#sentences.forEach((s, i) => this.#indexOf.set(s.id, i));
    this.#cb = {
      onSentence: onSentence || noop,
      onWord: onWord || noop,
      onState: onState || noop,
      onError: onError || noop,
      onOffline: onOffline || noop,
    };
    const audio = document.createElement("audio");
    audio.preload = "auto";
    audio.preservesPitch = true;
    audio.hidden = true;
    document.body.append(audio);
    this.#audio = audio;
    audio.addEventListener("ended", () => this.#onEnded());
    audio.addEventListener("error", () => this.#onAudioError());
  }

  get state() {
    return this.#state;
  }

  get current() {
    return this.#cur;
  }

  get speed() {
    return this.#speed;
  }

  /** The single audio element used for playback (Task 13's voice preview may reuse it). */
  get audio() {
    return this.#audio;
  }

  /** Clip duration in seconds at speed 1.0, or undefined when not fetched yet. */
  knownDuration(sid) {
    return this.#durations.get(sid);
  }

  /** Show `sid` as the current sentence without playing it (restored position). */
  cue(sid) {
    if (!this.#indexOf.has(sid)) return;
    this.#token++;
    this.#halt();
    this.#cur = sid;
    this.#wordShown = -1;
    this.#setState("idle");
    this.#cb.onSentence(sid);
  }

  async playFrom(sid) {
    const i = this.#indexOf.get(sid);
    if (i === undefined) return;
    const token = ++this.#token;
    this.#halt();
    this.#cur = sid;
    this.#wordShown = -1;
    this.#setState("loading");
    this.#cb.onSentence(sid);
    focus(this.#packId, sid).catch((e) => this.#apiFailed(e));
    this.#scheduleSave(sid);
    this.#prefetch(i);

    let clip;
    try {
      clip = await this.#fetchClip(sid);
    } catch (e) {
      if (token === this.#token) this.#clipFailed(sid, e, token);
      return;
    }
    if (token !== this.#token) return;

    const audio = this.#audio;
    this.#loaded = sid;
    this.#clip = clip;
    this.#playToken = token;
    audio.src = clip.url; // resets playbackRate to defaultPlaybackRate
    audio.defaultPlaybackRate = this.#speed;
    audio.playbackRate = this.#speed;
    audio.preservesPitch = true;
    await this.#startAudio(token);
  }

  pause() {
    if (this.#state !== "playing" && this.#state !== "loading") return;
    this.#token++;
    this.#halt();
    this.#setState("paused");
  }

  resume() {
    if (this.#state !== "paused" && this.#state !== "idle") return;
    const sid = this.#cur ?? this.#sentences[0]?.id;
    if (!sid) return;
    const audio = this.#audio;
    if (this.#loaded === sid && audio.src && !audio.ended && audio.currentTime > 0) {
      const token = ++this.#token;
      this.#playToken = token;
      this.#setState("loading");
      this.#startAudio(token);
    } else if (this.#loaded === sid && audio.ended && this.#indexOf.get(sid) < this.#sentences.length - 1) {
      this.#advance();
    } else {
      this.playFrom(sid);
    }
  }

  toggle() {
    if (this.#state === "playing" || this.#state === "loading") this.pause();
    else this.resume();
  }

  next() {
    const i = this.#cur === null ? -1 : this.#indexOf.get(this.#cur);
    const s = this.#sentences[i + 1];
    if (s) this.playFrom(s.id);
  }

  prev() {
    const i = this.#cur === null ? 1 : this.#indexOf.get(this.#cur);
    const s = this.#sentences[Math.max(i - 1, 0)];
    if (s) this.playFrom(s.id);
  }

  replay() {
    const sid = this.#cur ?? this.#sentences[0]?.id;
    if (sid) this.playFrom(sid);
  }

  /** Clamp to 0.75–2.0 in 0.05 steps; pitch is preserved, pauses stay constant. */
  setSpeed(x) {
    const v = Math.min(MAX_SPEED, Math.max(MIN_SPEED, Math.round(Number(x) * 20) / 20));
    if (!Number.isFinite(v)) return this.#speed;
    this.#speed = v;
    this.#audio.defaultPlaybackRate = v;
    this.#audio.playbackRate = v;
    return v;
  }

  /** Save a pending (debounced) position now; used on page hide. */
  flushPosition() {
    if (!this.#pendingSave) return;
    clearTimeout(this.#saveTimer);
    const sid = this.#pendingSave;
    this.#pendingSave = null;
    savePosition(this.#packId, sid, { keepalive: true }).catch(noop);
  }

  // ---- internals -----------------------------------------------------------

  #setState(s) {
    if (s === this.#state) return;
    this.#state = s;
    this.#cb.onState(s);
  }

  /** Synchronously stop everything the previous request started. */
  #halt() {
    clearTimeout(this.#timer);
    this.#timer = 0;
    cancelAnimationFrame(this.#raf);
    this.#raf = 0;
    this.#audio.pause();
  }

  async #startAudio(token) {
    try {
      await this.#audio.play();
    } catch (e) {
      if (token !== this.#token) return;
      // A media error is reported through the 'error' event; anything else
      // (e.g. NotAllowedError) leaves us paused rather than retrying.
      if (!this.#audio.error) this.#setState("paused");
      return;
    }
    if (token !== this.#token) return;
    this.#setState("playing");
    this.#trackWords(token);
  }

  #trackWords(token) {
    const step = () => {
      if (token !== this.#token) return;
      const clip = this.#clip;
      const sentence = this.#sentences[this.#indexOf.get(this.#loaded)];
      if (clip && sentence) {
        const t = this.#audio.currentTime;
        let k = -1;
        for (let j = 0; j < clip.words.length && clip.words[j][0] <= t; j++) k = j;
        const display = k >= 0 && sentence.spoken[k] ? sentence.spoken[k].word_index : -1;
        if (display >= 0 && display !== this.#wordShown) {
          this.#wordShown = display;
          this.#cb.onWord(sentence.id, display);
        }
      }
      this.#raf = requestAnimationFrame(step);
    };
    this.#raf = requestAnimationFrame(step);
  }

  #onEnded() {
    const token = this.#token;
    if (this.#playToken !== token || this.#loaded !== this.#cur) return;
    cancelAnimationFrame(this.#raf);
    const s = this.#sentences[this.#indexOf.get(this.#cur)];
    clearTimeout(this.#timer);
    this.#timer = setTimeout(() => {
      if (token === this.#token) this.#advance();
    }, s ? s.pause_after_ms : 0);
  }

  #advance() {
    const i = this.#indexOf.get(this.#cur);
    const s = this.#sentences[i + 1];
    if (s) {
      this.playFrom(s.id);
    } else {
      this.#token++;
      this.#halt();
      this.#setState("idle");
    }
  }

  async #onAudioError() {
    const token = this.#token;
    if (this.#playToken !== token || !this.#audio.getAttribute("src")) return;
    const sid = this.#loaded;
    // Distinguish "server gone" from "this clip is broken".
    let offline = false;
    try {
      await getStatus();
    } catch (e) {
      offline = !!(e && e.offline);
    }
    if (token !== this.#token) return;
    this.#clips.delete(sid);
    this.#clipFailed(sid, offline ? { offline: true } : { error: "audio_failed" }, token);
  }

  #clipFailed(sid, err, token) {
    this.#halt();
    if (err && err.offline) {
      // Server unreachable: stop and wait for the user, don't skip the whole document.
      this.#token++;
      this.#setState("paused");
      this.#cb.onOffline(err);
      return;
    }
    this.#cb.onError(sid);
    this.#timer = setTimeout(() => {
      if (token === this.#token) this.#advance();
    }, SKIP_DELAY_MS);
  }

  #fetchClip(sid) {
    let p = this.#clips.get(sid);
    if (!p) {
      p = getClip(this.#packId, sid).then((clip) => {
        this.#durations.set(sid, clip.duration);
        return clip;
      });
      p.catch((e) => {
        if (this.#clips.get(sid) === p) this.#clips.delete(sid); // retry next time
        if (e && e.offline) this.#cb.onOffline(e);
      });
      this.#clips.set(sid, p);
    }
    return p;
  }

  #prefetch(i) {
    for (let k = i + 1; k <= i + PREFETCH && k < this.#sentences.length; k++) {
      this.#fetchClip(this.#sentences[k].id).catch(noop);
    }
  }

  #scheduleSave(sid) {
    clearTimeout(this.#saveTimer);
    this.#pendingSave = sid;
    this.#saveTimer = setTimeout(() => {
      this.#pendingSave = null;
      savePosition(this.#packId, sid).catch((e) => this.#apiFailed(e));
    }, SAVE_DEBOUNCE_MS);
  }

  #apiFailed(e) {
    if (e && e.offline) this.#cb.onOffline(e);
  }
}
