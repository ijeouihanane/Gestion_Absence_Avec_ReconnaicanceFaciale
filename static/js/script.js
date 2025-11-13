document.addEventListener("DOMContentLoaded", function() {
    const video = document.getElementById("video");
    const captureButton = document.getElementById("capture");
    const result = document.getElementById("result");
    const subjectId = document.getElementById("subject_id");

    // Accéder à la caméra
    navigator.mediaDevices.getUserMedia({ video: true })
        .then(stream => {
            video.srcObject = stream;
        })
        .catch(err => {
            console.error("Erreur d'accès à la caméra : ", err);
            result.innerText = "Erreur d'accès à la caméra";
        });

    // Capturer l'image et envoyer au serveur
    captureButton.addEventListener("click", function() {
        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        canvas.getContext("2d").drawImage(video, 0, 0);
        canvas.toBlob(blob => {
            const formData = new FormData();
            formData.append("image", blob, "capture.jpg");
            formData.append("subject_id", subjectId.value);

            fetch("/scan", {
                method: "POST",
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.message) {
                    result.innerText = data.message;
                } else {
                    result.innerText = data.error || "Erreur inconnue";
                }
            })
            .catch(err => {
                result.innerText = "Erreur : " + err.message;
            });
        }, "image/jpeg");
    });
});