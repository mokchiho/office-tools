// 公共脚本 - 夜间模式切换 (立即执行，避免闪烁)
(function() {
    // 立即读取并应用保存的主题
    const savedTheme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
})();

// 页面加载完成后设置按钮状态
document.addEventListener('DOMContentLoaded', function() {
    const themeBtn = document.querySelector('.btn-icon[title="夜间模式"]');
    if (themeBtn) {
        // 根据当前主题设置按钮图标
        const currentTheme = document.documentElement.getAttribute('data-theme');
        if (currentTheme === 'dark') {
            themeBtn.textContent = '☀️';
        }
        
        // 点击切换主题
        themeBtn.addEventListener('click', () => {
            const current = document.documentElement.getAttribute('data-theme');
            const next = current === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem('theme', next);
            themeBtn.textContent = next === 'dark' ? '☀️' : '🌙';
        });
    }
});