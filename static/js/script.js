// --------------------
// GYM ID (set in HTML as: <div id="app" data-gym-id="{{ session['gym_id'] }}"></div>)
// --------------------
const gymId = document.getElementById("app").dataset.gymId;


// --------------------
// ADD MEMBER
// --------------------
document.getElementById("memberForm").addEventListener("submit", function (e) {
    e.preventDefault();

    let formData = new FormData(this);
    formData.append("plan_id", document.getElementById("plan_id").value);

    fetch("/add-member", {
        method: "POST",
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            document.getElementById("result").innerText = "❌ " + data.error;
        } else {
            document.getElementById("result").innerText =
                `✅ ID: ${data.member_id} | Expiry: ${data.expiry_date}`;

            document.getElementById("memberForm").reset();

            loadMembers();
            loadAlerts();
        }
    })
    .catch(err => {
        console.error(err);
        document.getElementById("result").innerText = "❌ Server error";
    });
});


// --------------------
// LOAD MEMBERS
// --------------------
function loadMembers() {
    fetch(`/members/${gymId}`)
    .then(res => {
        if (!res.ok) throw new Error("Failed to load members");
        return res.json();
    })
    .then(data => {
        let table = document.querySelector("#membersTable tbody");
        table.innerHTML = "";

        if (!data.length) {
            table.innerHTML = "<tr><td colspan='9'>No members found</td></tr>";
            return;
        }

        data.forEach(member => {
            let row = `
                <tr>
                    <td>${member.unique_id || ""}</td>

                    <td>
                        <a href="/member/${member.unique_id}" target="_blank">
                            ${member.name || "N/A"}
                        </a>
                    </td>

                    <td>${member.phone || "N/A"}</td>
                    <td>${member.email || "N/A"}</td>
                    <td>${member.age || "-"}</td>
                    <td>${member.gender || "-"}</td>

                    <td>
                        ${member.photo
                            ? `<a href="${member.photo}" target="_blank">View</a>`
                            : "No Photo"}
                    </td>

                    <td>${member.expiry_date || "-"}</td>

                    <td>
                        <button onclick='editMember(${JSON.stringify(member)})'>
                            Edit
                        </button>

                        <button onclick="deleteMember(${member.id})"
                            style="background:red;color:white;">
                            Delete
                        </button>
                    </td>
                </tr>
            `;

            table.innerHTML += row;
        });
    })
    .catch(err => console.error("loadMembers error:", err));
}


// --------------------
// DELETE MEMBER
// --------------------
function deleteMember(id) {
    if (!confirm("Are you sure you want to delete this member?")) return;

    fetch(`/delete-member/${id}`, {
        method: "DELETE"
    })
    .then(res => {
        if (!res.ok) throw new Error("Delete failed");
        return res.json();
    })
    .then(data => {
        alert(data.message || data.error);
        loadMembers();
        loadAlerts();
    })
    .catch(err => console.error("deleteMember error:", err));
}


// --------------------
// EDIT MEMBER
// --------------------
function editMember(member) {
    let name    = prompt("Name", member.name);
    let phone   = prompt("Phone", member.phone);
    let email   = prompt("Email", member.email);
    let age     = prompt("Age", member.age);
    let gender  = prompt("Gender", member.gender);
    let address = prompt("Address", member.address);

    fetch(`/update-member/${member.id}`, {
        method: "PUT",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            name,
            phone,
            email,
            age: age ? parseInt(age) : null,
            gender,
            address
        })
    })
    .then(res => {
        if (!res.ok) throw new Error("Update failed");
        return res.json();
    })
    .then(data => {
        alert(data.message || data.error);
        loadMembers();
    })
    .catch(err => console.error("editMember error:", err));
}


// --------------------
// LOAD ALERTS
// --------------------
function loadAlerts() {
    fetch(`/expiry-alerts/${gymId}`)
    .then(res => {
        if (!res.ok) throw new Error("Failed to load alerts");
        return res.json();
    })
    .then(data => {
        let list = document.getElementById("alertsList");
        list.innerHTML = "";

        if (!data.length) {
            list.innerHTML = "<li>No expiring members</li>";
            return;
        }

        data.forEach(member => {
            let li = document.createElement("li");
            li.classList.add("alert");
            li.innerText =
                `${member.name} | ${member.phone} | Expiring: ${member.expiry_date}`;
            list.appendChild(li);
        });
    })
    .catch(err => console.error("loadAlerts error:", err));
}


// --------------------
// CSV UPLOAD
// --------------------
function uploadCSV() {
    let fileInput = document.getElementById("csvFile");
    let file = fileInput.files[0];

    if (!file) {
        alert("Select a file first!");
        return;
    }

    let formData = new FormData();
    formData.append("file", file);
    formData.append("plan_id", document.getElementById("plan_id").value);

    fetch("/upload-csv", {
        method: "POST",
        body: formData
    })
    .then(res => {
        if (!res.ok) throw new Error("CSV upload failed");
        return res.json();
    })
    .then(data => {
        document.getElementById("csvResult").innerText =
            `✅ Inserted: ${data.inserted}, Skipped: ${data.skipped}`;

        loadMembers();
        loadAlerts();
    })
    .catch(err => {
        console.error("uploadCSV error:", err);
        document.getElementById("csvResult").innerText = "❌ Upload failed";
    });
}


// --------------------
// AUTO LOAD
// --------------------
window.onload = function () {
    loadMembers();
    loadAlerts();
};
