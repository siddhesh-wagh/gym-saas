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
    const expiry   = new Date(dateStr);
    const diffDays = Math.ceil((expiry - today) / 86400000);

    if (diffDays < 0)  return `<span class="badge badge-expired">Expired</span>`;
    if (diffDays <= 3) return `<span class="badge badge-expiring">Expiring (${diffDays}d)</span>`;
    return `<span class="badge badge-active">Active</span>`;
}


// --------------------
// LOAD PLANS  — populates all plan dropdowns from /plans API
// --------------------
function loadPlans() {
    fetch("/plans")
        .then(res => { if (!res.ok) throw new Error(); return res.json(); })
        .then(plans => {
            const selectors = ["#plan_id", "#csvPlanId", "#renewPlanId"];

            selectors.forEach(sel => {
                const el = document.querySelector(sel);
                if (!el) return;

                // Remember previously selected value (if any)
                const prev = el.value;
                el.innerHTML = "";

                if (!plans.length) {
                    el.innerHTML = `<option value="">No plans available</option>`;
                    return;
                }

                plans.forEach(p => {
                    const opt = document.createElement("option");
                    opt.value       = p.id;
                    opt.textContent = `${p.name} (${p.duration_days} days)`;
                    el.appendChild(opt);
                });

                // Restore selection if still valid
                if (prev && el.querySelector(`option[value="${prev}"]`)) {
                    el.value = prev;
                }
            });
        })
        .catch(err => console.error("loadPlans:", err));
}


// --------------------
// LOAD MEMBERS + STATS
// --------------------
function loadMembers() {
    fetch("/members")
        .then(res => { if (!res.ok) throw new Error("Failed"); return res.json(); })
        .then(data => {
            renderTable(data);
            updateStats(data);
        })
        .catch(err => console.error("loadMembers:", err));
}

function renderTable(data) {
    const tbody = document.querySelector("#membersTable tbody");
    if (!data.length) {
        tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;color:var(--text-3);padding:30px;">No members yet</td></tr>`;
        return;
    }

    tbody.innerHTML = data.map(m => `
        <tr data-search="${(m.name + " " + m.phone).toLowerCase()}">
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
            <td>${m.photo ? `<a href="${m.photo}" target="_blank" style="font-size:12px;">View</a>` : "—"}</td>
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

function updateStats(data) {
    const today    = new Date(); today.setHours(0,0,0,0);
    const active   = data.filter(m => new Date(m.expiry_date) >= today).length;
    const expiring = data.filter(m => {
        const d    = new Date(m.expiry_date);
        const diff = Math.ceil((d - today) / 86400000);
        return diff >= 0 && diff <= 3;
    }).length;

    const elTotal    = document.getElementById("statTotal");
    const elActive   = document.getElementById("statActive");
    const elExpiring = document.getElementById("statExpiring");

    if (elTotal)    elTotal.textContent    = data.length;
    if (elActive)   elActive.textContent   = active;
    if (elExpiring) elExpiring.textContent = expiring;
}


// --------------------
// SEARCH / FILTER
// --------------------
function filterTable() {
    const q = document.getElementById("searchInput").value.toLowerCase();
    document.querySelectorAll("#membersTable tbody tr").forEach(row => {
        const s = row.dataset.search || row.innerText.toLowerCase();
        row.style.display = s.includes(q) ? "" : "none";
    });
}


// --------------------
// ADD MEMBER
// --------------------
document.getElementById("memberForm").addEventListener("submit", function(e) {
    e.preventDefault();

    const btn = this.querySelector("button[type='submit']");
    btn.textContent = "Adding…";
    btn.disabled    = true;

    fetch("/add-member", { method: "POST", body: new FormData(this) })
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                showResult("result", "❌ " + data.error, "error");
            } else {
                showResult("result", `✅ Added! ID: ${data.member_id} | Expiry: ${data.expiry_date}`, "success");
                this.reset();
                // Reload plans after reset (reset clears the select)
                loadPlans();
                loadMembers();
                loadAlerts();
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
        .then(() => { loadMembers(); loadAlerts(); })
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
    document.getElementById("editModal").classList.add("open");
}

function closeEdit() {
    document.getElementById("editModal").classList.remove("open");
}

document.getElementById("editModal").addEventListener("click", function(e) {
    if (e.target === this) closeEdit();
});

function saveEdit() {
    const id = document.getElementById("editId").value;

    fetch(`/update-member/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            name:    document.getElementById("editName").value,
            phone:   document.getElementById("editPhone").value,
            email:   document.getElementById("editEmail").value,
            age:     document.getElementById("editAge").value || null,
            gender:  document.getElementById("editGender").value,
            address: document.getElementById("editAddress").value,
        })
    })
    .then(res => { if (!res.ok) throw new Error(); return res.json(); })
    .then(() => { closeEdit(); loadMembers(); })
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

            if (!data.length) {
                if (card) card.style.display = "none";
                return;
            }

            if (card) card.style.display = "block";
            list.innerHTML = data.map(m =>
                `<li>⚠️ <strong>${m.name}</strong> — ${m.phone} — Expires: ${m.expiry_date}</li>`
            ).join("");
        })
        .catch(err => console.error("loadAlerts:", err));
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
    btn.textContent = "Uploading…";
    btn.disabled    = true;

    fetch("/upload-csv", { method: "POST", body: formData })
        .then(res => { if (!res.ok) throw new Error(); return res.json(); })
        .then(data => {
            showResult("csvResult", `✅ Inserted: ${data.inserted} | Skipped: ${data.skipped}`, "success");
            loadMembers();
            loadAlerts();
        })
        .catch(() => showResult("csvResult", "❌ Upload failed", "error"))
        .finally(() => { btn.textContent = "Upload"; btn.disabled = false; });
}


// --------------------
// AUTO LOAD
// --------------------
window.onload = function() {
    loadPlans();     // fills plan dropdowns from DB
    loadMembers();
    loadAlerts();
};