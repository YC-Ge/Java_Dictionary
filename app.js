const state = {
  selected: null,
  lang: "zh",
  results: [],
  mode: "explain",
  stickyThreshold: 0,
  stickyActive: false,
};

const els = {
  body: document.body,
  form: document.querySelector("#search-form"),
  searchPanel: document.querySelector("#search-panel"),
  query: document.querySelector("#query"),
  language: document.querySelector("#language"),
  jdkVersion: document.querySelector("#jdk-version"),
  docsBase: document.querySelector("#docs-base"),
  resultCount: document.querySelector("#result-count"),
  results: document.querySelector("#results"),
  detailTitle: document.querySelector("#detail-title"),
  officialLink: document.querySelector("#official-link"),
  detailMeta: document.querySelector("#detail-meta"),
  modeTabs: document.querySelectorAll(".mode-tab"),
  modePanels: document.querySelectorAll(".mode-panel"),
  signature: document.querySelector("#signature"),
  officialExcerpt: document.querySelector("#official-excerpt"),
  chineseExplanation: document.querySelector("#chinese-explanation"),
  conceptSummary: document.querySelector("#concept-summary"),
  interviewList: document.querySelector("#interview-list"),
  exampleTitle: document.querySelector("#example-title"),
  exampleCode: document.querySelector("#example-code"),
  exampleNote: document.querySelector("#example-note"),
  copySnippet: document.querySelector("#copy-snippet"),
  copyStatus: document.querySelector("#copy-status"),
  resultTemplate: document.querySelector("#result-template"),
};

const languageLabels = {
  zh: "ZH",
  es: "ES",
  ja: "JA",
};

async function readJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function setMode(mode) {
  state.mode = mode;
  for (const tab of els.modeTabs) {
    tab.classList.toggle("is-active", tab.dataset.mode === mode);
  }
  for (const panel of els.modePanels) {
    panel.classList.toggle("is-active", panel.id === `mode-${mode}`);
  }
}

function measureStickyThreshold() {
  state.stickyThreshold = Math.max(0, els.searchPanel.offsetTop - 10);
}

function renderList(target, items) {
  target.innerHTML = "";
  for (const item of items) {
    const li = document.createElement("li");
    li.textContent = item;
    target.appendChild(li);
  }
}

function renderInterview(items) {
  els.interviewList.innerHTML = "";
  for (const item of items) {
    const card = document.createElement("article");
    card.className = "qa-card";
    card.innerHTML = `
      <div class="language-block">
        <span class="lang-tag">EN</span>
        <p><strong>Q:</strong> ${item.en.question}</p>
        <p><strong>A:</strong> ${item.en.answer}</p>
      </div>
      <div class="language-block">
        <span class="lang-tag">${languageLabels[state.lang] || state.lang.toUpperCase()}</span>
        <p><strong>Q:</strong> ${item.secondary.question}</p>
        <p><strong>A:</strong> ${item.secondary.answer}</p>
      </div>
    `;
    els.interviewList.appendChild(card);
  }
}

function renderError(message) {
  const text = `Failed to load app data: ${message}`;
  els.signature.textContent = "No signature extracted for this page.";
  els.officialExcerpt.textContent = text;
  els.chineseExplanation.textContent = text;
  els.conceptSummary.innerHTML = "";
  els.interviewList.innerHTML = "";
  els.exampleCode.textContent = "";
  els.exampleNote.textContent = "";
}

function renderResults() {
  els.results.innerHTML = "";
  els.resultCount.textContent = `${state.results.length} results`;
  for (const result of state.results) {
    const node = els.resultTemplate.content.firstElementChild.cloneNode(true);
    node.classList.toggle("is-active", state.selected?.url === result.url);
    node.querySelector(".result-kind").textContent = result.kind;
    node.querySelector(".result-title").textContent = result.title;
    node.querySelector(".result-subtitle").textContent = result.subtitle;
    node.addEventListener("click", async () => {
      state.selected = result;
      renderResults();
      await loadDocument(result);
    });
    els.results.appendChild(node);
  }
}

function renderDocument(result, documentData) {
  els.detailTitle.textContent = documentData.pageTitle || result.title;
  els.officialLink.href = result.url;
  els.detailMeta.innerHTML = "";
  [result.kind, result.module, result.package].filter(Boolean).forEach((token) => {
    const badge = document.createElement("span");
    badge.textContent = token;
    els.detailMeta.appendChild(badge);
  });
  els.signature.textContent = documentData.signature || "No signature extracted for this page.";
  els.officialExcerpt.textContent = documentData.officialExcerpt;
  els.chineseExplanation.textContent = documentData.chineseExplanation;
  renderList(els.conceptSummary, documentData.conceptSummary);
  renderInterview(documentData.interviewQA);
  els.exampleTitle.textContent = documentData.example.title;
  els.exampleCode.textContent = documentData.example.code;
  els.exampleNote.textContent = documentData.example.notes[state.lang] || documentData.example.notes.en;
  els.copyStatus.textContent = "";
}

async function loadDocument(result) {
  try {
    const params = new URLSearchParams({
      url: result.url,
      kind: result.kind,
      title: result.title,
      label: result.label,
      package: result.package,
      module: result.module,
      className: result.className,
      anchor: result.anchor,
      lang: state.lang,
    });
    const payload = await readJson(`/api/doc?${params.toString()}`);
    renderDocument(result, payload.document);
  } catch (error) {
    renderError(error.message);
  }
}

async function search(query) {
  try {
    const params = new URLSearchParams({ q: query, lang: state.lang });
    const payload = await readJson(`/api/search?${params.toString()}`);
    els.jdkVersion.textContent = `JDK ${payload.latestJdkVersion}`;
    state.results = payload.results;
    state.selected = payload.selected;
    renderResults();
    if (payload.selected && payload.document) {
      renderDocument(payload.selected, payload.document);
      return;
    }
    renderError("No matching documentation was returned.");
  } catch (error) {
    renderError(error.message);
  }
}

async function loadConfig() {
  const payload = await readJson("/api/config");
  els.jdkVersion.textContent = `JDK ${payload.latestJdkVersion}`;
  els.docsBase.textContent = payload.docsBaseUrl;
}

els.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  state.lang = els.language.value;
  await search(els.query.value.trim());
});

els.language.addEventListener("change", async () => {
  state.lang = els.language.value;
  if (state.selected) {
    await loadDocument(state.selected);
  }
});

for (const tab of els.modeTabs) {
  tab.addEventListener("click", () => setMode(tab.dataset.mode));
}

els.copySnippet.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(els.exampleCode.textContent);
    els.copyStatus.textContent = "Copied";
  } catch {
    els.copyStatus.textContent = "Copy failed";
  }
});

function syncStickySearch() {
  const enterAt = state.stickyThreshold + 10;
  const leaveAt = Math.max(0, state.stickyThreshold - 10);

  if (!state.stickyActive && window.scrollY >= enterAt) {
    state.stickyActive = true;
  } else if (state.stickyActive && window.scrollY <= leaveAt) {
    state.stickyActive = false;
  }

  els.searchPanel.classList.toggle("is-stuck", state.stickyActive);
  els.body.classList.toggle("search-stuck", state.stickyActive);
}

window.addEventListener("scroll", syncStickySearch, { passive: true });
window.addEventListener("resize", () => {
  measureStickyThreshold();
  syncStickySearch();
}, { passive: true });

async function init() {
  setMode(state.mode);
  measureStickyThreshold();
  syncStickySearch();
  await loadConfig();
  await search(els.query.value.trim());
}

init().catch((error) => {
  console.error(error);
  renderError(error.message);
});
