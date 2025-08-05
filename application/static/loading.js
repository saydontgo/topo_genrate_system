window.addEventListener('DOMContentLoaded', () => {
    const currentUrl = window.location.href;

    fetch('/initiate_topo', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ url: currentUrl })
    })
        .then(response => response.json())
        .then(data => {
            console.log("后端返回：", data.status);
        })
        .catch(error => {
            console.error("请求失败：", error);
        });
});
