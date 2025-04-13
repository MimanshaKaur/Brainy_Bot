let userId = null;

async function login() {
    const email = document.getElementById("email").value;
    const password = document.getElementById("password").value;

    const res = await fetch("/user/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password })
    });

    const data = await res.json();
    if (res.ok) {
        userId = data.user_id;
        alert("Login successful!");
    } else alert(data.message);
}

async function uploadPDF() {
    const file = document.getElementById("pdfFile").files[0];
    const formData = new FormData();
    formData.append("file", file);
    formData.append("user_id", userId);

    const res = await fetch("/pdf/upload", { method: "POST", body: formData });
    const data = await res.json();
    document.getElementById("output").innerText = data.text;
}

async function transcribe() {
    const url = document.getElementById("youtubeLink").value;
    const res = await fetch("/youtube/transcribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url })
    });
    const data = await res.json();
    document.getElementById("output").innerText = data.transcript;
}
