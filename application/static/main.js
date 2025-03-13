// 更新时间
function updateTime() {
    const now = new Date();
    const timeString = now.toLocaleTimeString();
    const dateString = now.toLocaleDateString();
    const timeElement = document.getElementById('time');
    timeElement.textContent = `${dateString} ${timeString}`;
}

// 初始调用更新时间
updateTime();

// 每秒更新一次时间
setInterval(updateTime, 1000);

// 汉堡菜单事件
const hamburger = document.querySelector('.hamburger');
const sidebar = document.querySelector('.sidebar');
const mainContent = document.querySelector('.main-content');

hamburger.addEventListener('click', () => {
    sidebar.classList.toggle('hidden');
    mainContent.classList.toggle('hidden');
});

// 子菜单的展开与收起
const submenuItems = document.querySelectorAll('.has-submenu > a');
submenuItems.forEach(item => {
    item.addEventListener('click', (e) => {
        const submenu = item.nextElementSibling;
        submenu.style.display = submenu.style.display === 'block' ? 'none' : 'block';
        e.preventDefault(); // 阻止默认行为，防止页面跳转
    });
});

