const state = {
  selectedRunId: null,
};

function statusBadge(value) {
  const normalized = String(value || "unknown");
  return `<span class="status status-${normalized}">${normalized}</span>`;
}

function renderEmpty(target, message, colspan) {
  target.innerHTML = `<tr><td class="empty-state" colspan="${colspan}">${message}</td></tr>`;
}

function formatNumber(value) {
  return new Intl.NumberFormat().format(value || 0);
}

function formatDate(value) {
  if (!value) return "In progress";
  return new Date(value).toLocaleString();
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(error.detail || "Request failed");
  }
  return response.json();
}

async function loadStats() {
  const stats = await fetchJson("/stats");
  document.getElementById("totalRuns").textContent = formatNumber(stats.total_runs);
  document.getElementById("totalArchived").textContent = formatNumber(stats.total_files_archived);
  document.getElementById("totalSkipped").textContent = formatNumber(stats.total_skipped);
  document.getElementById("totalErrors").textContent = formatNumber(stats.total_errors);
  document.getElementById("groupStats").textContent =
    `Most recent: ${stats.most_recent_group || "-"} | Busiest: ${stats.busiest_group || "-"}`;
}

async function loadRuns() {
  const tbody = document.getElementById("runsTableBody");
  const runs = await fetchJson("/runs");

  if (!runs.length) {
    renderEmpty(tbody, "No archive runs recorded yet.", 8);
    return;
  }

  if (!state.selectedRunId) {
    state.selectedRunId = runs[0].id;
  }

  tbody.innerHTML = runs
    .map(
      (run) => `
        <tr data-clickable="true" data-run-id="${run.id}">
          <td>${run.id}</td>
          <td>${run.group_name}</td>
          <td>${formatDate(run.started_at)}</td>
          <td>${Number(run.duration_seconds || 0).toFixed(3)}</td>
          <td>${run.total_moved}</td>
          <td>${run.total_skipped}</td>
          <td>${run.total_errors}</td>
          <td>${statusBadge(run.status)}</td>
        </tr>
      `
    )
    .join("");

  tbody.querySelectorAll("tr[data-run-id]").forEach((row) => {
    row.addEventListener("click", () => {
      state.selectedRunId = Number(row.dataset.runId);
      loadRunDetail().catch(showRefreshError);
    });
  });
}

async function loadRunDetail() {
  const tbody = document.getElementById("filesTableBody");
  const detailTitle = document.getElementById("detailTitle");

  if (!state.selectedRunId) {
    renderEmpty(tbody, "Select a run to inspect file events.", 6);
    return;
  }

  const run = await fetchJson(`/runs/${state.selectedRunId}`);
  detailTitle.textContent = `Run ${run.id} | group=${run.group_name} | status=${run.status}`;

  if (!run.files.length) {
    renderEmpty(tbody, "This run has no file events yet.", 6);
    return;
  }

  tbody.innerHTML = run.files
    .map(
      (file) => `
        <tr>
          <td>${file.username}</td>
          <td>${file.source_path}</td>
          <td>${file.destination_path || "-"}</td>
          <td>${statusBadge(file.status)}</td>
          <td>${file.reason}</td>
          <td>${formatDate(file.event_time)}</td>
        </tr>
      `
    )
    .join("");
}

function showRefreshError(error) {
  document.getElementById("refreshStatus").textContent = error.message;
}

async function refresh() {
  document.getElementById("refreshStatus").textContent = "Refreshing every 10s";
  await loadStats();
  await loadRuns();
  await loadRunDetail();
}

refresh().catch(showRefreshError);
setInterval(() => {
  refresh().catch(showRefreshError);
}, 10000);
