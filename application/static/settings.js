document.addEventListener("DOMContentLoaded", function () {
    // 显示节点大小的实时值
    const hostSizeInput = document.getElementById("hostSize");
    const switchSizeInput = document.getElementById("switchSize");
    const hostSizeValue = document.getElementById("hostSizeValue");
    const switchSizeValue = document.getElementById("switchSizeValue");

    hostSizeInput.addEventListener("input", () => {
        hostSizeValue.textContent = hostSizeInput.value;
    });
    switchSizeInput.addEventListener("input", () => {
        switchSizeValue.textContent = switchSizeInput.value;
    });

    // 读取已有设置
    fetch("/get_topo_settings")
        .then(response => response.json())
        .then(settings => {
            if (settings) {
                document.getElementById("hostShape").value = settings.hostShape || "ellipse";
                document.getElementById("hostColor").value = settings.hostColor || "#FFD700";
                document.getElementById("hostSize").value = settings.hostSize || 25;
                document.getElementById("hostSizeValue").textContent = settings.hostSize || 25;

                document.getElementById("switchShape").value = settings.switchShape || "box";
                document.getElementById("switchColor").value = settings.switchColor || "#87CEEB";
                document.getElementById("switchSize").value = settings.switchSize || 25;
                document.getElementById("switchSizeValue").textContent = settings.switchSize || 25;
            }
        });

    // 保存设置
    document.getElementById("saveSettingsBtn").addEventListener("click", function () {
        const settings = {
            hostShape: document.getElementById("hostShape").value,
            hostColor: document.getElementById("hostColor").value,
            hostSize: parseInt(document.getElementById("hostSize").value),
            switchShape: document.getElementById("switchShape").value,
            switchColor: document.getElementById("switchColor").value,
            switchSize: parseInt(document.getElementById("switchSize").value),
        };

        fetch("/save_topo_settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(settings)
        })
        .then(res => res.json())
        .then(res => {
            document.getElementById("saveStatus").textContent = "设置已保存";
        })
        .catch(err => {
            document.getElementById("saveStatus").style.color = "red";
            document.getElementById("saveStatus").textContent = "l保存失败";
        });
    });
});
