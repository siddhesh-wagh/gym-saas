const GYM_ID = 1;
const PLAN_ID = 1;

// --------------------
// ADD MEMBER
// --------------------
function addMember() {
    fetch("/add-member", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            name: document.getElementById("name").value,
            phone: document.getElementById("phone").value,
            gym_id: GYM_ID,
            plan_id: PLAN_ID
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            document.getElementById("result").innerText = "❌ " + data.error;
        } else {
            document.getElementById("result").innerText =
                "✅ Member added | Expiry: " + data.expiry_date;

            loadMembers();
            loadAlerts();
        }
    });
}

// --------------------
// LOAD MEMBERS
// --------------------
function loadMembers() {
    fetch(`/members/${GYM_ID}`)
    .then(res => res.json())
    .then(data => {
        let list = document.getElementById("membersList");
        list.innerHTML = "";

        data.forEach(member => {
            let li = document.createElement("li");
            li.innerText =
                member.name + " | " +
                member.phone + " | Expiry: " +
                member.expiry_date;

            list.appendChild(li);
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
