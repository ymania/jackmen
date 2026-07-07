/**
 * jack门 — 前端逻辑 v0.3
 */

const API = "https://jackmen-production.up.railway.app";
const MATCH_API = API + "/api/match";

let role = null;
let answers = new Array(12).fill(null);
let currentQ = 0;
let userId = null;
let contact = "";
let pageHistory = ["home"];  // 返回导航栈

// ---- 题目 ----
const questions = [
    { id: 0, title: "上了一天课，晚上你更想：", options: ["约朋友出去逛逛", "自己待着刷手机/看书", "看心情，一半一半", "不确定"], dim: "EI" },
    { id: 1, title: "小组讨论时你通常：", options: ["先发言带动气氛", "先听别人说完再开口", "一半一半", "看主题"], dim: "EI" },
    { id: 2, title: "学新东西时你更依赖：", options: ["具体例子和操作步骤", "抽象概念和底层框架", "一半一半", "分情况"], dim: "SN" },
    { id: 3, title: "看一篇教程你更在意：", options: ["有没有可操作的步骤", "底层原理讲清楚没有", "都重要", "看心情"], dim: "SN" },
    { id: 4, title: "做重要决定时你优先考虑：", options: ["逻辑和数据", "感受和价值观", "一半一半", "问别人"], dim: "TF" },
    { id: 5, title: "朋友找你诉苦，你第一反应：", options: ["帮忙分析解决方案", "先共情，说你懂他", "都有", "不知道说什么"], dim: "TF" },
    { id: 6, title: "面对截止日期：", options: ["提前规划、分步完成", "截止前冲刺效率最高", "看任务类型", "没注意过"], dim: "JP" },
    { id: 7, title: "周末安排：", options: ["列出计划按顺序来", "随心所欲想到啥做啥", "只有大概方向", "完全不计划"], dim: "JP" },
    { id: 8, title: "你更擅长帮别人解决哪类问题？", options: ["学习方法 / 考试技巧", "技术 / 编程 / 工具使用", "情感 / 人际关系", "生活信息（选课/食堂/周边）"], dim: "help" },
    { id: 9, title: "你遇到困难时习惯：", options: ["马上找人问", "自己先搜/先试，不行再问", "不好意思开口，等别人主动", "看困难大小"], dim: "help" },
    { id: 10, title: "和别人一起学习/工作时你更喜欢：", options: ["你带节奏，对方跟着做", "对方带节奏，你跟着做", "平等分工各干各的", "看对方水平"], dim: "help" },
    { id: 11, title: "什么样的人你最愿意帮？", options: ["主动求助、目标明确的", "和我性格像的", "确实有困难、不帮不行的", "能学到新东西的"], dim: "help" }
];

// ---- 导航 ----
function showPage(name) {
    pageHistory.push(name);
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const page = document.getElementById('page-' + name);
    if (page) page.classList.add('active');

    const nav = document.getElementById('nav-bar');
    if (name === 'home') {
        nav.style.display = 'none';
    } else {
        nav.style.display = 'flex';
        document.getElementById('nav-title').textContent =
            name === 'quiz' ? '性格问卷' :
            name === 'result' ? '匹配结果' :
            name === 'notif' ? '通知' :
            name === 'privacy' ? '隐私说明' : '';
    }

    if (name === 'result' && userId) {
        loadMatch(false);
    }
}

function goBack() {
    if (pageHistory.length > 1) pageHistory.pop();
    const prev = pageHistory[pageHistory.length - 1] || 'home';
    pageHistory.pop();
    showPage(prev);
}

// ---- 通知 ----
async function checkNotifications() {
    if (!userId) return;
    try {
        const res = await fetch(API + '/notifications/' + userId);
        const data = await res.json();
        if (data.unread > 0) {
            document.getElementById('nav-badge').style.display = 'inline';
            document.getElementById('nav-badge').textContent = data.unread;
        }
    } catch (e) {}
}

function showNotifications() {
    if (!userId) return;
    showPage('notif');
    fetch(API + '/notifications/' + userId)
        .then(r => r.json())
        .then(data => {
            const list = document.getElementById('notif-list');
            if (!data.notifications || data.notifications.length === 0) {
                list.innerHTML = '<div class="empty-state"><div style="color:var(--text-dim);">暂无通知</div></div>';
                return;
            }
            list.innerHTML = data.notifications.map(n => `
                <div class="notif-item ${n.read ? '' : 'unread'}">
                    <div style="font-weight:600;">${n.message}</div>
                    <div style="font-size:13px;color:var(--text-dim);margin-top:4px;">来自：${n.from_contact} · ${n.from_role}</div>
                    <div style="font-size:12px;color:var(--text-dim);margin-top:2px;">${n.time || ''}</div>
                </div>
            `).join('');
            fetch(API + '/notifications/' + userId + '/read', { method: 'POST' });
            document.getElementById('nav-badge').style.display = 'none';
        });
}

setInterval(() => { if (userId) checkNotifications(); }, 30000);

// ---- 老用户返回 ----
function returnUser() {
    const id = document.getElementById('input-return-id').value.trim();
    if (!id) return;
    userId = id;
    showPage('result');
}

// ---- 角色选择 ----
function selectRole(r) {
    role = r;
    document.querySelectorAll('.role-card').forEach(c => c.classList.remove('selected'));
    document.querySelector(`.role-card[data-role="${r}"]`).classList.add('selected');
    const btn = document.getElementById('btn-start');
    btn.disabled = false;
    btn.style.opacity = '1';
    btn.textContent = '开始答题 →';
}

document.getElementById('btn-start').addEventListener('click', () => {
    if (!role) return;
    showPage('quiz');
    renderQuestion();
});

// ---- 问卷渲染 ----
function renderQuestion() {
    const q = questions[currentQ];
    document.getElementById('q-current').textContent = currentQ + 1;
    document.getElementById('q-total').textContent = questions.length;
    document.getElementById('q-bar').style.width = ((currentQ / questions.length) * 100) + '%';
    document.getElementById('q-title').textContent = q.title;

    const optsDiv = document.getElementById('q-options');
    optsDiv.innerHTML = '';
    q.options.forEach((opt, i) => {
        const btn = document.createElement('button');
        btn.className = 'option';
        if (answers[currentQ] === i) btn.classList.add('selected');
        btn.textContent = opt;
        btn.addEventListener('click', () => selectOption(i));
        optsDiv.appendChild(btn);
    });

    document.getElementById('btn-prev').style.display = currentQ === 0 ? 'none' : 'block';
    const nextBtn = document.getElementById('btn-next');
    nextBtn.textContent = currentQ === questions.length - 1 ? '提交 ✓' : '下一题 →';
    nextBtn.disabled = answers[currentQ] === null;
}

function selectOption(i) {
    answers[currentQ] = i;
    document.getElementById('btn-next').disabled = false;
    document.querySelectorAll('.option').forEach((o, idx) => o.classList.toggle('selected', idx === i));
}

document.getElementById('btn-prev').addEventListener('click', () => {
    if (currentQ > 0) { currentQ--; renderQuestion(); document.getElementById('btn-next').disabled = answers[currentQ] === null; }
});

document.getElementById('btn-next').addEventListener('click', () => {
    if (currentQ < questions.length - 1) { currentQ++; renderQuestion(); document.getElementById('btn-next').disabled = answers[currentQ] === null; }
    else showContactInput();
});

// ---- 联系方式 ----
function showContactInput() {
    const card = document.querySelector('#page-quiz .card');
    card.innerHTML = `
        <div class="question-title">最后一步 — 留下联系方式</div>
        <p style="font-size:14px;color:var(--text-dim);margin-bottom:16px;">匹配成功后，对方会看到这个联系方式来找你。</p>
        <label class="input-label">微信号 / QQ</label>
        <input class="input-field" id="input-contact" type="text" placeholder="例如：@wechat_id">
    `;
    document.getElementById('btn-prev').style.display = 'none';
    const nextBtn = document.getElementById('btn-next');
    nextBtn.textContent = '提交匹配 🚀';
    nextBtn.disabled = false;
    nextBtn.onclick = async () => {
        contact = document.getElementById('input-contact').value.trim();
        if (!contact) { alert('请填写联系方式'); return; }
        await submitQuiz();
    };
}

// ---- 提交 ----
async function submitQuiz() {
    showPage('result');
    document.getElementById('result-content').innerHTML = '<div class="loading"><div class="spinner"></div>正在匹配...</div>';

    try {
        const res = await fetch(API + '/api/match/submit', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role, answers, contact })
        });
        const data = await res.json();
        userId = data.user_id;
        await loadMatch(true);
        setTimeout(() => checkNotifications(), 2000);
    } catch (e) {
        document.getElementById('result-content').innerHTML = '<div class="empty-state"><div class="emoji">😵</div><div class="text">连接失败，请确保后端已启动。</div></div>';
    }
}

// ---- 匹配加载 ----
async function loadMatch(showNotif = false) {
    try {
        const res = await fetch(API + '/api/match/' + userId);
        const data = await res.json();
        renderResult(data);
        if (showNotif && data.matches?.length > 0) {
            setTimeout(() => checkNotifications(), 1000);
        }
    } catch (e) {
        document.getElementById('result-content').innerHTML = '<div class="empty-state"><div class="emoji">😵</div><div class="text">匹配失败，请重试</div></div>';
    }
}

// ---- 连接/忽略 ----
async function connectMatch(matchedId) {
    await fetch(API + '/api/match/' + userId + '/connect', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ matched_id: matchedId })
    });
    alert('已连接！通过上方联系方式联系对方吧。');
    location.reload();
}

async function ignoreMatch(matchedId) {
    await fetch(API + '/api/match/' + userId + '/ignore', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ matched_id: matchedId })
    });
    loadMatch(false);
}

// ---- 分享 ----
function shareResult() {
    const text = '我在 jack门 做了性格匹配，找到了能帮我的学长学姐！你也来试试？';
    if (navigator.share) {
        navigator.share({ title: 'jack门', text, url: window.location.href }).catch(() => {});
    } else {
        if (navigator.clipboard) {
            navigator.clipboard.writeText(text + ' ' + window.location.href).then(() => alert('已复制，发给朋友吧！'));
        }
    }
}

// ---- 渲染结果 ----
function renderResult(data) {
    const { matches } = data;

    if (!matches || matches.length === 0) {
        document.getElementById('result-content').innerHTML = `
            <div class="card">
                <div class="empty-state">
                    <div class="emoji">🔍</div>
                    <div style="font-size:16px;font-weight:600;margin-bottom:8px;">暂无新匹配</div>
                    <div class="text">
                        可能的原因：<br><br>
                        ① 池子里还没有和你互补的人<br>
                        ② 你已浏览过所有可匹配的人<br><br>
                        👇 分享给朋友，扩大匹配池！
                    </div>
                </div>
            </div>
            <button class="btn btn-primary" onclick="shareResult()">📤 分享给朋友</button>
            <button class="btn btn-secondary" onclick="showPage('home')" style="margin-top:8px;">← 返回首页</button>
        `;
        return;
    }

    let html = `
        <div class="card" style="text-align:center;">
            <div class="emoji" style="font-size:40px;">🎉</div>
            <div style="font-size:18px;font-weight:700;color:var(--accent);margin-top:8px;">你的最佳匹配</div>
            <div style="color:var(--text-dim);font-size:13px;margin-top:4px;">共 ${matches.length} 位 · 你的 ID：${userId}</div>
        </div>
    `;

    const emojis = ['🥇', '🥈', '🥉'];
    matches.forEach((m, i) => {
        html += `
            <div class="match-card">
                <div style="display:flex;align-items:center;gap:12px;">
                    <span style="font-size:28px;">${emojis[i] || '✨'}</span>
                    <span class="match-score">${Math.round(m.score * 100)}%</span>
                    <span style="color:var(--text-dim);font-size:13px;">匹配度</span>
                </div>
                <div class="match-reason">${m.reason}</div>
                <div class="match-contact">📲 ${m.contact}</div>
                <div style="display:flex;gap:8px;margin-top:10px;">
                    <button class="btn btn-primary" style="flex:1;padding:10px;font-size:14px;" onclick="connectMatch('${m.matched_id}')">🤝 连接</button>
                    <button class="btn btn-ignore" style="flex:1;padding:10px;font-size:14px;" onclick="ignoreMatch('${m.matched_id}')">换一批</button>
                </div>
            </div>
        `;
    });

    html += `
        <button class="btn btn-primary" onclick="shareResult()" style="margin-top:16px;">📤 分享给朋友</button>
        <button class="btn btn-secondary" onclick="showPage('home')" style="margin-top:8px;">← 返回首页</button>
    `;

    document.getElementById('result-content').innerHTML = html;
}
