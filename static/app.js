const PAGE_SIZE = 48;
let currentPage = 0;
let totalListings = 0;

const state = {
  beds: "",
  ac: false,
  wd: false,
  maxPrice: "",
  minSqft: "",
  neighborhoods: [],
  source: "",
  sort: "newest",
};

// ── Fetch & render ────────────────────────────────────────────────────────────

async function fetchListings() {
  showLoading();
  const params = new URLSearchParams({
    limit: PAGE_SIZE,
    offset: currentPage * PAGE_SIZE,
    sort: state.sort,
  });
  if (state.beds) params.set("bedrooms", state.beds);
  if (state.ac) params.set("has_ac", "true");
  if (state.wd) params.set("has_washer_dryer", "true");
  if (state.maxPrice) params.set("max_price", state.maxPrice);
  if (state.minSqft) params.set("min_sqft", state.minSqft);
  if (state.neighborhoods.length) params.set("neighborhoods", state.neighborhoods.join(","));
  if (state.source) params.set("source", state.source);

  try {
    const res = await fetch(`/api/listings?${params}`);
    const data = await res.json();
    totalListings = data.total;
    renderGrid(data.listings);
    renderPagination();
    document.getElementById("result-count").textContent =
      `${data.total.toLocaleString()} listing${data.total !== 1 ? "s" : ""}`;
  } catch (e) {
    showError();
  }
}

async function fetchStats() {
  try {
    const res = await fetch("/api/stats");
    const data = await res.json();
    document.getElementById("stats").textContent =
      `${data.total.toLocaleString()} total listings`;
  } catch (_) {}
}

// ── Grid rendering ─────────────────────────────────────────────────────────────

function renderGrid(listings) {
  const grid = document.getElementById("grid");
  if (!listings.length) {
    grid.innerHTML = `<div class="empty" style="grid-column:1/-1">
      <div style="font-size:40px;margin-bottom:12px">🏙️</div>
      <div style="font-weight:600;margin-bottom:4px">No listings found</div>
      <div style="font-size:14px">Try adjusting your filters</div>
    </div>`;
    return;
  }

  grid.innerHTML = listings.map(renderCard).join("");
}

function renderCard(l) {
  const price = l.price ? `$${l.price.toLocaleString()}/mo` : "Price TBD";
  const meta = [l.bedrooms === "studio" ? "Studio" : l.bedrooms === "1br" ? "1 Bedroom" : null, l.sqft ? `${l.sqft.toLocaleString()} sqft` : null]
    .filter(Boolean).join(" · ");
  const location = l.neighborhood || l.address || "";

  const imgTag = l.image_url
    ? `<img class="card-img" src="${escHtml(l.image_url)}" loading="lazy" onerror="this.parentNode.innerHTML='<div class=card-img-placeholder>🏠</div>'" />`
    : `<div class="card-img-placeholder">🏠</div>`;

  const badges = [
    l.has_ac ? `<span class="badge badge-ac">AC</span>` : "",
    l.has_washer_dryer ? `<span class="badge badge-wd">W/D</span>` : "",
    `<span class="badge badge-source">${escHtml(l.source)}</span>`,
    isNew(l.first_seen) ? `<span class="badge badge-new">New</span>` : "",
  ].join("");

  return `
    <div class="card">
      ${imgTag}
      <div class="card-body">
        <div class="card-price">${price}</div>
        ${meta ? `<div class="card-meta">${escHtml(meta)}</div>` : ""}
        ${location ? `<div class="card-location">${escHtml(location)}</div>` : ""}
        <div class="badges">${badges}</div>
        <a class="card-link" href="${escHtml(l.url)}" target="_blank" rel="noopener">View listing →</a>
      </div>
    </div>
  `;
}

function isNew(isoDate) {
  if (!isoDate) return false;
  const age = Date.now() - new Date(isoDate).getTime();
  return age < 24 * 60 * 60 * 1000;
}

// ── Pagination ─────────────────────────────────────────────────────────────────

function renderPagination() {
  const totalPages = Math.ceil(totalListings / PAGE_SIZE);
  if (totalPages <= 1) {
    document.getElementById("pagination").innerHTML = "";
    return;
  }

  const pages = [];
  pages.push(`<button ${currentPage === 0 ? "disabled" : ""} data-page="${currentPage - 1}">← Prev</button>`);

  for (let i = 0; i < totalPages; i++) {
    if (totalPages > 7 && Math.abs(i - currentPage) > 2 && i !== 0 && i !== totalPages - 1) {
      if (i === 1 || i === totalPages - 2) pages.push(`<button disabled>…</button>`);
      continue;
    }
    pages.push(`<button class="${i === currentPage ? "active" : ""}" data-page="${i}">${i + 1}</button>`);
  }

  pages.push(`<button ${currentPage >= totalPages - 1 ? "disabled" : ""} data-page="${currentPage + 1}">Next →</button>`);
  document.getElementById("pagination").innerHTML = pages.join("");
}

// ── Loading states ─────────────────────────────────────────────────────────────

function showLoading() {
  document.getElementById("grid").innerHTML = `
    <div class="loading" style="grid-column:1/-1">
      <div class="loading-spinner"></div>
      <div>Loading listings...</div>
    </div>`;
  document.getElementById("pagination").innerHTML = "";
}

function showError() {
  document.getElementById("grid").innerHTML = `
    <div class="empty" style="grid-column:1/-1">
      <div style="font-size:40px;margin-bottom:12px">⚠️</div>
      <div style="font-weight:600">Could not load listings</div>
    </div>`;
}

// ── Event listeners ────────────────────────────────────────────────────────────

function applyFilters() {
  currentPage = 0;
  fetchListings();
}

document.querySelectorAll('input[name="beds"]').forEach(r =>
  r.addEventListener("change", () => { state.beds = r.value; applyFilters(); })
);
document.getElementById("filter-ac").addEventListener("change", e => {
  state.ac = e.target.checked; applyFilters();
});
document.getElementById("filter-wd").addEventListener("change", e => {
  state.wd = e.target.checked; applyFilters();
});
document.getElementById("filter-price").addEventListener("change", e => {
  state.maxPrice = e.target.value; applyFilters();
});
document.getElementById("filter-sqft").addEventListener("change", e => {
  state.minSqft = e.target.value; applyFilters();
});
document.getElementById("sort-select").addEventListener("change", e => {
  state.sort = e.target.value; applyFilters();
});

document.querySelectorAll(".source-pill").forEach(pill =>
  pill.addEventListener("click", () => {
    document.querySelectorAll(".source-pill").forEach(p => p.classList.remove("active"));
    pill.classList.add("active");
    state.source = pill.dataset.source;
    applyFilters();
  })
);

async function loadNeighborhoods() {
  try {
    const res = await fetch("/api/neighborhoods");
    const neighborhoods = await res.json();
    const container = document.getElementById("filter-neighborhood");
    neighborhoods.forEach(n => {
      const label = document.createElement("label");
      label.className = "checkbox-row";
      label.innerHTML = `<input type="checkbox" value="${escHtml(n)}" />${escHtml(n)}`;
      label.querySelector("input").addEventListener("change", e => {
        if (e.target.checked) {
          state.neighborhoods.push(n);
        } else {
          state.neighborhoods = state.neighborhoods.filter(x => x !== n);
        }
        applyFilters();
      });
      container.appendChild(label);
    });
  } catch (_) {}
}
loadNeighborhoods();

document.getElementById("reset-btn").addEventListener("click", () => {
  state.beds = "";
  state.ac = false;
  state.wd = false;
  state.minSqft = "";
  state.maxPrice = "";
  state.neighborhoods = [];
  state.source = "";
  state.sort = "newest";
  document.querySelector('input[name="beds"][value=""]').checked = true;
  document.getElementById("filter-ac").checked = false;
  document.getElementById("filter-wd").checked = false;
  document.getElementById("filter-price").value = "";
  document.getElementById("filter-sqft").value = "";
  document.querySelectorAll("#filter-neighborhood input[type='checkbox']").forEach(cb => cb.checked = false);
  document.getElementById("sort-select").value = "newest";
  document.querySelectorAll(".source-pill").forEach(p => p.classList.remove("active"));
  document.querySelector('.source-pill[data-source=""]').classList.add("active");
  applyFilters();
});

document.getElementById("pagination").addEventListener("click", e => {
  const btn = e.target.closest("[data-page]");
  if (!btn || btn.disabled) return;
  currentPage = parseInt(btn.dataset.page);
  fetchListings();
  window.scrollTo({ top: 0, behavior: "smooth" });
});

document.getElementById("scrape-btn").addEventListener("click", async () => {
  const btn = document.getElementById("scrape-btn");
  btn.textContent = "Refreshing...";
  btn.classList.add("loading");
  try {
    await fetch("/api/scrape", { method: "POST" });
    setTimeout(() => {
      fetchListings();
      fetchStats();
      btn.textContent = "Refresh listings";
      btn.classList.remove("loading");
    }, 5000);
  } catch (_) {
    btn.textContent = "Refresh listings";
    btn.classList.remove("loading");
  }
});

// ── Utilities ──────────────────────────────────────────────────────────────────

function escHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Chat ───────────────────────────────────────────────────────────────────────

const chatHistory = [];
let chatStreaming = false;

const chatPanel = document.getElementById("chat-panel");
const chatMessages = document.getElementById("chat-messages");
const chatInput = document.getElementById("chat-input");
const chatSend = document.getElementById("chat-send");

document.getElementById("chat-btn").addEventListener("click", () => {
  chatPanel.classList.toggle("open");
  if (chatPanel.classList.contains("open")) chatInput.focus();
});
document.getElementById("chat-close").addEventListener("click", () => {
  chatPanel.classList.remove("open");
});

chatInput.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
});
chatSend.addEventListener("click", sendChat);

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = `msg msg-${role}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  div.appendChild(bubble);
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return bubble;
}

function addTypingIndicator() {
  const div = document.createElement("div");
  div.className = "msg msg-assistant";
  div.id = "typing-indicator";
  div.innerHTML = `<div class="bubble"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div>`;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function removeTypingIndicator() {
  const el = document.getElementById("typing-indicator");
  if (el) el.remove();
}

async function sendChat() {
  const text = chatInput.value.trim();
  if (!text || chatStreaming) return;

  chatInput.value = "";
  chatSend.disabled = true;
  chatStreaming = true;

  addMessage("user", text);
  chatHistory.push({ role: "user", content: text });

  addTypingIndicator();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: chatHistory }),
    });

    removeTypingIndicator();
    const bubble = addMessage("assistant", "");
    let fullText = "";

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const data = line.slice(6).trim();
        if (data === "[DONE]") break;
        try {
          const parsed = JSON.parse(data);
          if (parsed.text) {
            fullText += parsed.text;
            bubble.textContent = fullText;
            chatMessages.scrollTop = chatMessages.scrollHeight;
          }
          if (parsed.error) bubble.textContent = "Sorry, something went wrong. Try again.";
        } catch (_) {}
      }
    }

    chatHistory.push({ role: "assistant", content: fullText });
  } catch (_) {
    removeTypingIndicator();
    addMessage("assistant", "Sorry, couldn't connect. Try again.");
  }

  chatStreaming = false;
  chatSend.disabled = false;
  chatInput.focus();
}

// ── Init ───────────────────────────────────────────────────────────────────────

fetchListings();
fetchStats();
