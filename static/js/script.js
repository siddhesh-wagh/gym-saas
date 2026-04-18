const GYM_ID = 1;

// --------------------
// ADD MEMBER
// --------------------
document.getElementById("memberForm").addEventListener("submit", function (e) {
    e.preventDefault();

    let formData = new FormData(this);

    formData.append("gym_id", GYM_ID);
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
    fetch(`/members/${GYM_ID}`)
    .then(res => res.json())
    .then(data => {
        let table = document.querySelector("#membersTable tbody");
        table.innerHTML = "";

        if (!data.length) {
            table.innerHTML = "<tr><td colspan='8'>No members found</td></tr>";
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
                </tr>
            `;

            table.innerHTML += row;
        });
    })
    .catch(err => console.error(err));
}


// --------------------
// LOAD ALERTS
// --------------------
function loadAlerts() {
    fetch(`/expiry-alerts/${GYM_ID}`)
    .then(res => res.json())
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
    .catch(err => console.error(err));
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
    formData.append("gym_id", GYM_ID);
    formData.append("plan_id", document.getElementById("plan_id").value);

    fetch("/upload-csv", {
        method: "POST",
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        document.getElementById("csvResult").innerText =
            `✅ Inserted: ${data.inserted}, Skipped: ${data.skipped}`;

        loadMembers();
        loadAlerts();
    })
    .catch(err => {
        console.error(err);
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
