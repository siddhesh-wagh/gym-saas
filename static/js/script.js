// --------------------
// STATE
// --------------------
let currentFilter = "all";
let searchTimer   = null;


// --------------------
// HELPERS
// --------------------
function showResult(elId, msg, type) {
    const el = document.getElementById(elId);
    if (!el) return;
    el.textContent = msg;
    el.className   = type;
    el.classList.add("show");
    setTimeout(() => el.classList.remove("show"), 4000);
}

function expiryBadge(dateStr) {
    const today    = new Date(); today.setHours(0,0,0,0);
    const diffDays = Math.ceil((new Date(dateStr) - today) / 86400000);
    if (diffDays < 0)  return `<span class="badge badge-expired">Expired</span>`;
    if (diffDays <= 3) return `<span class="badge badge-expiring">Expiring (${diffDays}d)</span>`;
    return `<span class="badge badge-active">Active</span>`;
}


// --------------------
// LOAD PLANS
// --------------------
function loadPlans() {
    fetch("/plans")
        .then(res => { if (!res.ok) throw new Error(); return res.json(); })
        .then(plans => {
            ["#plan_id", "#csvPlanId", "#renewPlanId"].forEach(sel => {
                const el = document.querySelector(sel);
                if (!el) return;
                const prev = el.value;
                el.innerHTML = "";

                if (!plans.length) {
                    el.innerHTML = `<option value="">No plans — add in Profile</option>`;
                    return;
                }

                plans.forEach(p => {
                    const opt = document.createElement("option");
                    opt.value = p.id;
                    const dur = p.duration_days === 0 ? "Walk-in" : p.duration_days + " days";
                    opt.textContent = `${p.name} (${dur})${p.price ? " — ₹" + p.price : ""}`;
                    el.appendChild(opt);
                });

                if (prev && el.querySelector(`option[value="${prev}"]`)) el.value = prev;
            });
        })
        .catch(err => console.error("loadPlans:", err));
}


// --------------------
// LOAD MEMBERS — server-side search + filter
// --------------------
function loadMembers(filter, search) {
    filter = filter ?? currentFilter ?? "all";
    search = search ?? (document.getElementById("searchInput")?.value || "");

    const params = new URLSearchParams();
    if (filter && filter !== "all") params.set("filter", filter);
    if (search.trim()) params.set("search", search.trim());

    const url = "/members" + (params.toString() ? "?" + params.toString() : "");

    fetch(url)
        .then(res => { if (!res.ok) throw new Error(); return res.json(); })
        .then(data => {
            renderTable(data);
            // Only update stat counts when loading ALL (no filter active)
            if (filter === "all" && !search.trim()) updateStats(data);
        })
        .catch(err => console.error("loadMembers:", err));
}

// Alias for refresh button (no args = reload with current state)
function reloadMembers() {
    loadMembers(currentFilter, document.getElementById("searchInput")?.value || "");
}


// --------------------
// FILTER BUTTONS
// --------------------
function applyFilter(filter) {
    currentFilter = filter;

    // Highlight active button
    ["all","active","expiring","expired"].forEach(f => {
        const btn = document.getElementById("filter" + f.charAt(0).toUpperCase() + f.slice(1));
        if (!btn) return;
        btn.className = f === filter
            ? "btn btn-sm" + (f === "all" ? "" : f === "active" ? " btn-success" : f === "expiring" ? " btn-warning" : " btn-danger")
            : "btn btn-ghost btn-sm";
    });

    // Update badge
    const badge = document.getElementById("filterBadge");
    if (badge) {
        if (filter === "all") {
            badge.style.display = "none";
        } else {
            badge.style.display = "inline";
            badge.textContent = filter.charAt(0).toUpperCase() + filter.slice(1);
        }
    }

    loadMembers(filter, document.getElementById("searchInput")?.value || "");
}


// --------------------
// SEARCH (debounced, server-side)
// --------------------
function handleSearch() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
        loadMembers(currentFilter, document.getElementById("searchInput").value);
    }, 300);
}


// --------------------
// RENDER TABLE
// --------------------
function renderTable(data) {
    const tbody = document.querySelector("#membersTable tbody");
    if (!data.length) {
        tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;color:var(--text-3);padding:30px;">No members found</td></tr>`;
        return;
    }

    tbody.innerHTML = data.map(m => `
        <tr>
            <td style="color:var(--text-3);font-size:12px;">${m.unique_id || ""}</td>
            <td>
                <a href="/member/${m.unique_id}" target="_blank" style="font-weight:600;">
                    ${m.name || "N/A"}
                </a>
            </td>
            <td>${m.phone || "N/A"}</td>
            <td style="color:var(--text-2);">${m.email || "—"}</td>
            <td>${m.age || "—"}</td>
            <td>${m.gender || "—"}</td>
            <td>${m.photo
                ? `<a href="${m.photo}" target="_blank">
                     <img src="${m.photo}" style="width:32px;height:32px;border-radius:50%;
                     object-fit:cover;border:2px solid var(--border);"/>
                   </a>`
                : "—"}</td>
            <td>${m.expiry_date || "—"}</td>
            <td>${expiryBadge(m.expiry_date)}</td>
            <td>
                <div class="td-actions">
                    <button class="btn btn-sm" onclick='openEdit(${JSON.stringify(m)})'>✏️ Edit</button>
                    <button class="btn btn-sm btn-danger" onclick="deleteMember(${m.id})">🗑</button>
                </div>
            </td>
        </tr>
    `).join("");
}


// --------------------
// STAT COUNTS (full load only)
// --------------------
function updateStats(data) {
    const today    = new Date(); today.setHours(0,0,0,0);
    const active   = data.filter(m => new Date(m.expiry_date) >= today).length;
    const expired  = data.filter(m => new Date(m.expiry_date) < today).length;
    const expiring = data.filter(m => {
        const diff = Math.ceil((new Date(m.expiry_date) - today) / 86400000);
        return diff >= 0 && diff <= 3;
    }).length;

    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set("statTotal",    data.length);
    set("statActive",   active);
    set("statExpiring", expiring);
    set("statExpired",  expired);
}


// --------------------
// ADD MEMBER
// --------------------
document.getElementById("memberForm").addEventListener("submit", function(e) {
    e.preventDefault();
    const btn = this.querySelector("button[type='submit']");
    btn.textContent = "Adding…"; btn.disabled = true;

    fetch("/add-member", { method: "POST", body: new FormData(this) })
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                showResult("result", "❌ " + data.error, "error");
            } else {
                showResult("result", `✅ Added! ID: ${data.member_id} | Expiry: ${data.expiry_date}`, "success");
                this.reset();
                loadPlans();
                loadMembers("all", "");
                loadAlerts();
                loadLogs();
            }
        })
        .catch(() => showResult("result", "❌ Server error", "error"))
        .finally(() => { btn.textContent = "Add Member"; btn.disabled = false; });
});


// --------------------
// DELETE MEMBER
// --------------------
function deleteMember(id) {
    if (!confirm("Delete this member?")) return;
    fetch(`/delete-member/${id}`, { method: "DELETE" })
        .then(res => { if (!res.ok) throw new Error(); return res.json(); })
        .then(() => { loadMembers(currentFilter); loadAlerts(); loadLogs(); })
        .catch(() => alert("❌ Delete failed"));
}


// --------------------
// EDIT MODAL
// --------------------
function openEdit(member) {
    document.getElementById("editId").value      = member.id;
    document.getElementById("editName").value    = member.name    || "";
    document.getElementById("editPhone").value   = member.phone   || "";
    document.getElementById("editEmail").value   = member.email   || "";
    document.getElementById("editAge").value     = member.age     || "";
    document.getElementById("editGender").value  = member.gender  || "";
    document.getElementById("editAddress").value = member.address || "";

    const photoInput = document.getElementById("editPhoto");
    if (photoInput) photoInput.value = "";

    const wrap = document.getElementById("currentPhotoWrap");
    const img  = document.getElementById("currentPhotoImg");
    if (wrap && img) {
        if (member.photo) { img.src = member.photo; wrap.style.display = "block"; }
        else              { wrap.style.display = "none"; }
    }

    document.getElementById("editModal").classList.add("open");
}

function closeEdit() { document.getElementById("editModal").classList.remove("open"); }

document.getElementById("editModal").addEventListener("click", function(e) {
    if (e.target === this) closeEdit();
});

function saveEdit() {
    const id = document.getElementById("editId").value;
    const fd = new FormData();
    fd.append("name",    document.getElementById("editName").value);
    fd.append("phone",   document.getElementById("editPhone").value);
    fd.append("email",   document.getElementById("editEmail").value);
    fd.append("age",     document.getElementById("editAge").value);
    fd.append("gender",  document.getElementById("editGender").value);
    fd.append("address", document.getElementById("editAddress").value);

    const photoFile = document.getElementById("editPhoto");
    if (photoFile && photoFile.files[0]) fd.append("photo", photoFile.files[0]);

    fetch(`/update-member/${id}`, { method: "POST", body: fd })
        .then(res => { if (!res.ok) throw new Error(); return res.json(); })
        .then(() => { closeEdit(); loadMembers(currentFilter); loadLogs(); })
        .catch(() => alert("❌ Update failed"));
}


// --------------------
// LOAD ALERTS
// --------------------
function loadAlerts() {
    fetch("/expiry-alerts")
        .then(res => { if (!res.ok) throw new Error(); return res.json(); })
        .then(data => {
            const card = document.getElementById("alertsCard");
            const list = document.getElementById("alertsList");
            if (!list) return;
            if (!data.length) { if (card) card.style.display = "none"; return; }
            if (card) card.style.display = "block";
            list.innerHTML = data.map(m =>
                `<li>⚠️ <strong>${m.name}</strong> — ${m.phone} — Expires: ${m.expiry_date}</li>`
            ).join("");
        })
        .catch(err => console.error("loadAlerts:", err));
}


// --------------------
// ACTIVITY LOG
// --------------------
function loadLogs() {
    const body = document.getElementById("logBody");
    if (!body) return;

    fetch("/my-logs")
        .then(res => { if (!res.ok) throw new Error(); return res.json(); })
        .then(logs => {
            if (!logs.length) {
                body.innerHTML = `<tr><td colspan="2" style="text-align:center;color:var(--text-3);padding:20px;">No activity yet</td></tr>`;
                return;
            }
            body.innerHTML = logs.map(l => `
                <tr>
                    <td class="log-action-cell">${l.action}</td>
                    <td class="log-time-cell">${l.created_at}</td>
                </tr>
            `).join("");
        })
        .catch(err => console.error("loadLogs:", err));
}


// --------------------
// CSV UPLOAD
// --------------------
function uploadCSV() {
    const fileInput = document.getElementById("csvFile");
    if (!fileInput.files[0]) { alert("Select a CSV file first"); return; }

    const formData = new FormData();
    formData.append("file",    fileInput.files[0]);
    formData.append("plan_id", document.getElementById("csvPlanId").value);

    const btn = event.target;
    btn.textContent = "Uploading…"; btn.disabled = true;

    fetch("/upload-csv", { method: "POST", body: formData })
        .then(res => { if (!res.ok) throw new Error(); return res.json(); })
        .then(data => {
            showResult("csvResult", `✅ Inserted: ${data.inserted} | Skipped: ${data.skipped}`, "success");
            loadMembers("all", "");
            loadAlerts();
            loadLogs();
        })
        .catch(() => showResult("csvResult", "❌ Upload failed", "error"))
        .finally(() => { btn.textContent = "Upload"; btn.disabled = false; });
}


// --------------------
// EXPORT MEMBERS
// --------------------
function exportCSV()   { window.location.href = "/export/members/csv"; }

function exportExcel() {
    fetch("/export/members/json").then(r => r.json()).then(data => {
        if (!data.length) { alert("No members to export"); return; }
        const headers = Object.keys(data[0]);
        const rows    = data.map(r => headers.map(h =>
            `"${(r[h]||"").toString().replace(/"/g,'""')}"`).join(","));
        const blob = new Blob([[headers.join(","), ...rows].join("\n")], { type: "text/csv" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob); a.download = "members_export.csv"; a.click();
    }).catch(() => alert("❌ Export failed"));
}

function exportPDF() {
    fetch("/export/members/json").then(r => r.json()).then(data => {
        if (!data.length) { alert("No members to export"); return; }
        const win  = window.open("", "_blank");
        const rows = data.map(m => `<tr>
            <td>${m.ID}</td><td>${m.Name}</td><td>${m.Phone}</td><td>${m.Email}</td>
            <td>${m.Age||"—"}</td><td>${m.Gender||"—"}</td>
            <td>${m["Join Date"]}</td><td>${m.Expiry}</td>
        </tr>`).join("");
        win.document.write(`<!DOCTYPE html><html><head><title>Members Report</title>
            <style>body{font-family:Arial,sans-serif;padding:20px;font-size:12px}
            table{width:100%;border-collapse:collapse}
            th{background:#4f46e5;color:white;padding:8px 10px;text-align:left;font-size:11px}
            td{padding:7px 10px;border-bottom:1px solid #eee}
            tr:nth-child(even) td{background:#f9fafb}
            @media print{button{display:none}}</style></head><body>
            <h2>Members Report</h2>
            <p style="color:#666;margin-bottom:16px;">
                Generated: ${new Date().toLocaleString()} | Total: ${data.length}
            </p>
            <table><thead><tr>
                <th>ID</th><th>Name</th><th>Phone</th><th>Email</th>
                <th>Age</th><th>Gender</th><th>Join Date</th><th>Expiry</th>
            </tr></thead><tbody>${rows}</tbody></table>
            <script>window.onload=()=>window.print();<\/script></body></html>`);
        win.document.close();
    }).catch(() => alert("❌ Export failed"));
}


// --------------------
// EXPORT LOGS PDF
// --------------------
function exportLogPDF() {
    fetch("/export/logs/json").then(r => r.json()).then(logs => {
        if (!logs.length) { alert("No logs to export"); return; }
        const win  = window.open("", "_blank");
        const rows = logs.map(l => `<tr><td>${l.Action}</td><td>${l.Time}</td></tr>`).join("");
        win.document.write(`<!DOCTYPE html><html><head><title>Activity Log</title>
            <style>body{font-family:Arial,sans-serif;padding:20px;font-size:12px}
            table{width:100%;border-collapse:collapse}
            th{background:#1e1b4b;color:white;padding:8px 10px;text-align:left;font-size:11px}
            td{padding:7px 10px;border-bottom:1px solid #eee}
            @media print{button{display:none}}</style></head><body>
            <h2>Activity Log Report</h2>
            <p style="color:#666;margin-bottom:16px;">
                Generated: ${new Date().toLocaleString()} | Total: ${logs.length}
            </p>
            <table><thead><tr><th>Action</th><th>Time</th></tr></thead>
            <tbody>${rows}</tbody></table>
            <script>window.onload=()=>window.print();<\/script></body></html>`);
        win.document.close();
    }).catch(() => alert("❌ Export failed"));
}


// --------------------
// AUTO LOAD
// --------------------
window.onload = function() {
    loadPlans();
    loadMembers("all", "");
    loadAlerts();
    loadLogs();
};