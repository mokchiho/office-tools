// 公共脚本 - 夜间模式切换 (立即执行，避免闪烁)
const _ICONS = {
    moon: '<svg class="icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>',
    sun: '<svg class="icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>'
};

// 供页面脚本复用的小图标（如"已复制"反馈）
window.toolIcon = function(name) {
    return _ICONS[name] || '';
};

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
            themeBtn.innerHTML = _ICONS.sun;
        }

        // 点击切换主题
        themeBtn.addEventListener('click', () => {
            const current = document.documentElement.getAttribute('data-theme');
            const next = current === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem('theme', next);
            themeBtn.innerHTML = next === 'dark' ? _ICONS.sun : _ICONS.moon;
        });
    }
});
