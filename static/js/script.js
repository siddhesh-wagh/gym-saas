const GYM_ID = 1;
const PLAN_ID = 1;


// --------------------
// ADD MEMBER (WITH PHOTO)
// --------------------
document.getElementById("memberForm").addEventListener("submit", function(e) {
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
                "✅ ID: " + data.member_id +
                " | Expiry: " + data.expiry_date;

            // refresh data
            loadMembers();
            loadAlerts();
        }
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

        data.forEach(member => {
            let row = `
                <tr>
                    <td>${member.unique_id}</td>
                    <td>
                        ${member.photo ? `<img src="${member.photo}" width="40">` : ""}
                        ${member.name}
                    </td>
                    <td>${member.phone}</td>
                    <td>${member.email || ""}</td>
                    <td>${member.age || ""}</td>
                    <td>${member.gender || ""}</td>
                    <td>${member.expiry_date}</td>
                </tr>
            `;

            table.innerHTML += row;
        });
    });
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

        data.forEach(member => {
            let li = document.createElement("li");
            li.classList.add("alert");

            li.innerText =
                member.name + " | " +
                member.phone + " | Expiring: " +
                member.expiry_date;

            list.appendChild(li);
        });
    });
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
    formData.append("plan_id", PLAN_ID);

    fetch("/upload-csv", {
        method: "POST",
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        document.getElementById("csvResult").innerText =
            "✅ " + data.message;

        loadMembers();
        loadAlerts();
    });
}


// --------------------
// AUTO LOAD
// --------------------
window.onload = function () {
    loadMembers();
    loadAlerts();
};
