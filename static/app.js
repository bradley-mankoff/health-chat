// Storage: sessionStorage for hc_pass is preferred over localStorage because it clears on tab close,
// reducing passcode persistence on shared devices. localStorage would persist indefinitely.
// We keep JOBKEY in localStorage (no PHI, only job id) so reload can recover a job.
// Rendering is same-origin only: marked + DOMPurify are vendored under /static/.
// md() fails closed to escaped text when the sanitizer is missing or throws.
const KEY = "hc_pass";
const JOBKEY = "hc_job";
const messagesEl = document.getElementById("messages");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");
const gate = document.getElementById("gate");
const statusEl = document.getElementById("status");
const logoutBtn = document.getElementById("logout");

if (window.marked && marked.setOptions) marked.setOptions({ gfm: true, breaks: true });
// Sanitize AI markdown output with vendored DOMPurify; fail closed to escaped text.
// Blocks remote media sinks (http/https/protocol-relative src) so a malicious
// model/record cannot exfiltrate via <img>; CSP img-src backs this up.
if (window.DOMPurify && DOMPurify.addHook) {
  DOMPurify.addHook("uponSanitizeAttribute", function (node, data) {
    var n = (data.attrName || "").toLowerCase();
    if (n === "src" || n === "srcset" || n === "poster" || n === "background") {
      var v = String(data.attrValue || "").trim().toLowerCase();
      if (v.indexOf("http:") === 0 || v.indexOf("https:") === 0 || v.indexOf("//") === 0) data.keepAttr = false;
    }
  });
}

let history = [];
let streaming = false;
let pass = sessionStorage.getItem(KEY) || "";
function esc(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function md(text) {
  try {
    if (!window.DOMPurify || typeof DOMPurify.sanitize !== "function") throw new Error("no sanitizer");
    const raw = marked.parse(text);
    return DOMPurify.sanitize(raw, { FORBID_TAGS: ["object", "embed", "iframe", "form", "base", "link", "style", "script", "meta", "title"], FORBID_ATTR: ["style"] });
  }
  catch (e) { return esc(text); }
}
function addMsg(role, html, cls) {
  const d = document.createElement("div");
  d.className = "msg " + role + (cls ? " " + cls : "");
  d.innerHTML = html;
  messagesEl.appendChild(d);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return d;
}

function newAiBubble() {
  return addMsg("ai",
    '<details class="think" hidden><summary>Thinking</summary><div class="think-body"></div></details>' +
    '<div class="answer-body"><span class="cursor"></span></div>');
}

function showGate() {
  gate.style.display = "flex";
  document.getElementById("code").focus();
}
function hideGate() { gate.style.display = "none"; }

async function getJson(path) {
  const res = await fetch(path, { headers: { "Authorization": "Bearer " + pass } });
  if (res.status === 401) {
    sessionStorage.removeItem(KEY);
    pass = "";
    showGate();
    throw new Error("unauthorized");
  }
  return res;
}

async function api(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": "Bearer " + pass,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) {
    sessionStorage.removeItem(KEY);
    pass = "";
    showGate();
    throw new Error("unauthorized");
  }
  return res;
}

async function refreshStatus() {
  try {
    const res = await fetch("/api/health", {
      headers: { "Authorization": "Bearer " + pass },
    });
    const j = await res.json();
    if (statusEl) statusEl.textContent = j.files.length + " file" + (j.files.length === 1 ? "" : "s") +
      " \u00b7 " + j.chunks + " chunks";
  } catch (e) { /* gate handles 401 */ }
}

// --- Upload: drag-drop + file input + preview table -----------------------
const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const uploadBtn = document.getElementById("upload-btn");
const uploadStatus = document.getElementById("upload-status");
const previewEl = document.getElementById("preview");
let pendingFiles = [];

function updateUploadBtn() {
  uploadBtn.disabled = pendingFiles.length === 0;
  if (pendingFiles.length) {
    uploadStatus.textContent = pendingFiles.length + " file" + (pendingFiles.length === 1 ? "" : "s") + " selected — click Upload";
  } else {
    uploadStatus.textContent = "";
    previewEl.style.display = "none";
  }
}

function setPending(files) {
  pendingFiles = Array.from(files || []);
  updateUploadBtn();
}

fileInput.addEventListener("change", function () { setPending(fileInput.files); });
dropZone.addEventListener("click", function (e) {
  if (e.target.tagName === "LABEL") return;
  fileInput.click();
});
dropZone.addEventListener("keydown", function (e) {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
});
["dragenter", "dragover"].forEach(function (ev) {
  dropZone.addEventListener(ev, function (e) { e.preventDefault(); dropZone.classList.add("dragover"); });
});
["dragleave", "drop"].forEach(function (ev) {
  dropZone.addEventListener(ev, function (e) { e.preventDefault(); dropZone.classList.remove("dragover"); });
});
dropZone.addEventListener("drop", function (e) {
  const dt = e.dataTransfer;
  if (dt && dt.files && dt.files.length) setPending(dt.files);
});

function renderPreview(data) {
  const preview = data.parsed_preview || data.parsed_labs || [];
  const files = data.files || [];
  const errors = data.errors || [];
  let html = "";
  if (preview.length) {
    preview.forEach(function (p) {
      const status = p.status || (p.labs_parsed ? "parsed " + p.labs_parsed + " labs" : "unparsed \u2014 raw chunks only");
      html += '<div class="prev-file"><span class="pf-name">' + esc(p.file) + '</span> \u2014 <span class="pf-status">' + esc(status) + '</span>';
      if (p.labs && p.labs.length) {
        html += '<table><thead><tr><th>name</th><th>value</th><th>unit</th><th>flag</th><th>range</th></tr></thead><tbody>';
        p.labs.forEach(function (row) {
          const rangeStr = (row.ranges || []).map(function (r) { return r.range + (r.phase ? " " + r.phase : ""); }).join("; ");
          html += "<tr><td>" + esc(row.name || "") + "</td><td>" + esc(String(row.value != null ? row.value : "")) + "</td><td>" + esc(row.unit || "") + "</td><td>" + esc(row.flag || "") + "</td><td>" + esc(rangeStr) + "</td></tr>";
        });
        html += "</tbody></table>";
      }
      html += "</div>";
    });
  }
  if (errors.length) {
    html += '<div class="prev-file" style="color:#b91c1c"><strong>Errors:</strong> ' + esc(errors.join("; ")) + "</div>";
  }
  if (!html) html = '<div class="prev-file">No files</div>';
  previewEl.innerHTML = '<div class="prev-head">Upload result \u2014 ' + esc(String(files.length)) + ' file' + (files.length === 1 ? "" : "s") + ' indexed</div>' + html;
  previewEl.style.display = "block";
}

async function doUpload() {
  if (!pendingFiles.length) return;
  uploadBtn.disabled = true;
  uploadStatus.textContent = "Uploading\u2026";
  previewEl.style.display = "none";
  const fd = new FormData();
  pendingFiles.forEach(function (f) { fd.append("files", f, f.name); });
  try {
    const res = await fetch("/api/upload", { method: "POST", headers: { "Authorization": "Bearer " + pass }, body: fd });
    if (res.status === 401) { sessionStorage.removeItem(KEY); pass = ""; showGate(); throw new Error("unauthorized"); }
    if (!res.ok) { const t = await res.text(); throw new Error(t.slice(0, 300) || "upload failed"); }
    const data = await res.json();
    renderPreview(data);
    const n = (data.uploaded && data.uploaded.length) || (data.parsed_preview && data.parsed_preview.length) || pendingFiles.length;
    uploadStatus.textContent = "Done \u2014 " + n + " file(s) saved";
    pendingFiles = [];
    fileInput.value = "";
    uploadBtn.disabled = true;
    refreshStatus();
  } catch (err) {
    uploadStatus.textContent = "Upload failed: " + err.message;
    uploadBtn.disabled = false;
  }
}
uploadBtn.addEventListener("click", doUpload);

// Turn model citations into clickable links, e.g. "per ARUP FSH Test Directory"
function applyLinks(text, gl) {
  for (const g of gl) {
    text = text.split(g.name).join("[" + g.name + "](" + g.url + ")");
    text = text.split(g.file).join("[" + g.name + "](" + g.url + ")");
  }
  text = text.replace(/\[src: [^\]]+\]/g, "");  // chunk artifacts, if echoed
  return text;
}

function render(job, els, done) {
  const think = els.think, thinkBody = els.thinkBody, answerBody = els.answerBody;
  const thinkText = job.reasoning.join("");
  const answer = job.answer.join("");
  const gl = job.gl || [];
  if (thinkText) {
    think.hidden = false;
    think.open = true;
    thinkBody.innerHTML = md(thinkText);
  }
  answerBody.innerHTML = md(applyLinks(answer, gl));
  if (!done) answerBody.insertAdjacentHTML("beforeend", '<span class="cursor"></span>');
  if (job.sources && job.sources.length) {
    answerBody.insertAdjacentHTML("beforeend",
      '<div class="srcs">Source: ' + esc(job.sources.join(", ")) + "</div>");
  }
  if (done && thinkText) think.open = false;
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

async function pollJob(id, els) {
  let failures = 0;
  for (;;) {
    let job;
    try {
      const res = await getJson("/api/chat/" + id);
      if (res.status === 404) {
        throw terminal("the answer was lost (the server restarted mid-generation) \u2014 please ask again");
      }
      job = await res.json();
      failures = 0;
    } catch (err) {
      if (err.terminal) throw err;           // auth / job lost: give up
      if (err.message === "unauthorized") throw err;
      failures += 1;                          // transient (phone suspended, wifi blip): retry
      const wait = Math.min(2500 * Math.pow(2, failures - 1), 30000);
      if (statusEl) statusEl.textContent = "connection paused \u2014 retrying\u2026";
      await new Promise(r => setTimeout(r, wait));
      continue;
    }
    if (statusEl) statusEl.textContent = job.status === "queued"
      ? "waiting for the model\u2026" : "";
    if (job.status === "error") throw terminal(job.error || "generation failed");
    render(job, els, job.status === "done");
    if (job.status === "done") {
      history.push({ role: "assistant", content: job.answer.join("") });
      return;
    }
    await new Promise(r => setTimeout(r, 2500));
  }
}

function terminal(msg) {
  const e = new Error(msg);
  e.terminal = true;
  return e;
}

async function send() {
  const q = input.value.trim();
  if (!q || streaming) return;
  input.value = "";
  input.style.height = "auto";
  addMsg("user", esc(q));
  history.push({ role: "user", content: q });
  history = history.slice(-8);
  const bubble = newAiBubble();
  const els = {
    think: bubble.querySelector(".think"),
    thinkBody: bubble.querySelector(".think-body"),
    answerBody: bubble.querySelector(".answer-body"),
  };
  streaming = true;
  sendBtn.disabled = true;
  if (statusEl) statusEl.textContent = "working\u2026";
  try {
    const res = await api("/api/chat", { question: q, history: history.slice(0, -1) });
    const j = await res.json();
    localStorage.setItem(JOBKEY, j.id);
    await pollJob(j.id, els);
    localStorage.removeItem(JOBKEY);  // success: key consumed
  } catch (err) {
    bubble.className = "msg ai err";
    bubble.textContent = "Something went wrong: " + err.message;
    if (err.terminal || err.message === "unauthorized") localStorage.removeItem(JOBKEY);
    // transient failure: keep the key so a reload can still recover the answer
  } finally {
    streaming = false;
    sendBtn.disabled = false;
    if (statusEl) statusEl.textContent = "";
    input.focus();
  }
}

// Reload/suspension recovery: an in-flight or finished job is still on the server.
async function resumeJob() {
  const id = localStorage.getItem(JOBKEY);
  if (!id || !pass) return;
  let job;
  try {
    const res = await getJson("/api/chat/" + id);
    if (!res.ok) { localStorage.removeItem(JOBKEY); return; }
    job = await res.json();
  } catch (e) { return; }
  if (job.status === "error") {
    addMsg("user", esc(job.question));
    const b = addMsg("ai", '<div class="answer-body"></div>', "err");
    b.textContent = "This answer failed server-side: " + (job.error || "generation failed") +
      ". Please ask again.";
    localStorage.removeItem(JOBKEY);
    return;
  }
  addMsg("user", esc(job.question));
  history.push({ role: "user", content: job.question });
  history = history.slice(-8);
  const bubble = newAiBubble();
  const els = {
    think: bubble.querySelector(".think"),
    thinkBody: bubble.querySelector(".think-body"),
    answerBody: bubble.querySelector(".answer-body"),
  };
  if (job.status === "done") {
    render(job, els, true);
    history.push({ role: "assistant", content: job.answer.join("") });
    localStorage.removeItem(JOBKEY);
    return;
  }
  streaming = true;
  sendBtn.disabled = true;
  if (statusEl) statusEl.textContent = "working\u2026";
  try {
    await pollJob(id, els);
  } catch (err) {
    bubble.className = "msg ai err";
    bubble.textContent = "Something went wrong: " + err.message;
  } finally {
    localStorage.removeItem(JOBKEY);
    streaming = false;
    sendBtn.disabled = false;
    if (statusEl) statusEl.textContent = "";
  }
}

document.getElementById("unlock").addEventListener("click", function () {
  const code = document.getElementById("code").value.trim();
  if (!code) return;
  pass = code;
  sessionStorage.setItem(KEY, code);
  hideGate();
  refreshStatus();
  resumeJob();
});
if (logoutBtn) logoutBtn.addEventListener("click", function () {
  sessionStorage.removeItem(KEY);
  pass = "";
  showGate();
});

sendBtn.addEventListener("click", send);
input.addEventListener("keydown", function (e) {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
});
input.addEventListener("input", function () {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 120) + "px";
});

if (!pass) showGate();
else { refreshStatus(); resumeJob(); }
