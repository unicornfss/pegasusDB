document.addEventListener("DOMContentLoaded", function () {
    const linkButton = document.getElementById("show-telegram-qr");
    const qrContainer = document.getElementById("telegram-qr-container");
    const qrCodeImage = document.getElementById("telegram-qr-code");

    if (!linkButton || !qrContainer || !qrCodeImage) return;

    linkButton.addEventListener("click", function () {
        if (qrContainer.style.display === "none") {
            // Fetch the QR code URL from the server
            fetch("/telegram/link-token/")
                .then(response => response.json())
                .then(data => {
                    if (data.qr_code_url) {
                        qrCodeImage.src = data.qr_code_url;
                        qrContainer.style.display = "block";
                    } else {
                        alert("Failed to load QR code. Please try again later.");
                    }
                })
                .catch(() => {
                    alert("Failed to load QR code. Please try again later.");
                });
        } else {
            qrContainer.style.display = "none";
        }
    });
});