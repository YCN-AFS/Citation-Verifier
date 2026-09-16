/**
 * CiteGuard — Web Application
 * Handles verification, comparison rendering, copy corrected content,
 * and animated global stats counters.
 */
const $ = id => document.getElementById(id);

// DOM
const refInput = $('refInput'), charCount = $('charCount'), clearBtn = $('clearBtn');
const verifyBtn = $('verifyBtn'), crossToggle = $('crossToggle');
const progressSec = $('progressSection'), progressFill = $('progressFill');
const progressTitle = $('progressTitle'), progressDetail = $('progressDetail');
const resultsSec = $('resultsSection'), summary = $('summary');
const cardsContainer = $('cardsContainer');
const viewComp = $('viewComp'), viewList = $('viewList');
const copyOriginalBtn = $('copyOriginalBtn'), copyCorrectedBtn = $('copyCorrectedBtn');
const exportJsonBtn = $('exportJsonBtn'), diffBanner = $('diffBanner');
const diffCount = $('diffCount'), diffCopyBtn = $('diffCopyBtn');
const toast = $('toast'), toastMsg = $('toastMsg');
const historyBtn = $('historyBtn'), historyDropdown = $('historyDropdown');
const historyCount = $('historyCount'), editor = $('editor');

let data = null, view = 'comparison';

const V = {
    VERIFIED:      { vi:'Xác minh',     css:'verified' },
    SUSPICIOUS:    { vi:'Nghi ngờ',      css:'suspicious' },
    MISMATCH:      { vi:'Sai lệch',     css:'mismatch' },
    DEAD_DOI:      { vi:'DOI không tồn tại', css:'dead_doi' },
    NO_DOI:        { vi:'Không có DOI',  css:'no_doi' },
    TITLE_MATCHED: { vi:'Khớp tiêu đề', css:'title_matched' },
    API_ERROR:     { vi:'Lỗi API',      css:'api_error' },
    RETRACTED:     { vi:'Đã bị thu hồi', css:'retracted' },
};

const SORDER = [
    {k:'total',   l:'Tổng cộng',   c:'s-total'},
    {k:'RETRACTED',l:'Thu hồi',    c:'s-retracted'},
    {k:'VERIFIED',l:'Xác minh',    c:'s-verified'},
    {k:'SUSPICIOUS',l:'Nghi ngờ',  c:'s-suspicious'},
    {k:'MISMATCH',l:'Sai lệch',   c:'s-mismatch'},
    {k:'DEAD_DOI',l:'DOI ảo',     c:'s-dead'},
    {k:'NO_DOI',  l:'Không DOI',   c:'s-nodoi'},
    {k:'TITLE_MATCHED',l:'Khớp tiêu đề',c:'s-matched'},
];

// ─── Global Stats Counter ────────────────────────────────────
function fetchStats() {
    fetch('/api/stats')
        .then(r => r.json())
        .then(stats => {
            animateCounter($('counterRefs'), stats.total_references || 0);
            animateCounter($('counterSessions'), stats.total_sessions || 0);
        })
        .catch(() => { /* silently fail — counters stay at 0 */ });
}

function animateCounter(el, target, duration = 1800) {
    if (!el || target === 0) { if (el) el.textContent = '0'; return; }
    let start = null;
    const step = ts => {
        if (!start) start = ts;
        const progress = Math.min((ts - start) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
        el.textContent = Math.floor(eased * target).toLocaleString('vi-VN');
        if (progress < 1) requestAnimationFrame(step);
        else el.textContent = target.toLocaleString('vi-VN');
    };
    requestAnimationFrame(step);
}

// Fetch stats on page load
fetchStats();

// ─── Events ──────────────────────────────────────────────────
refInput.addEventListener('input', () => charCount.textContent = refInput.value.length + ' ký tự');
clearBtn.addEventListener('click', () => { refInput.value = ''; charCount.textContent = '0 ký tự'; refInput.focus(); });
verifyBtn.addEventListener('click', doVerify);
viewComp.addEventListener('click', () => setView('comparison'));
viewList.addEventListener('click', () => setView('list'));
copyOriginalBtn.addEventListener('click', () => copyOriginal());
copyCorrectedBtn.addEventListener('click', () => copyCorrected());
diffCopyBtn.addEventListener('click', () => copyCorrected());
exportJsonBtn.addEventListener('click', () => exportJSON());

// ─── Verify ──────────────────────────────────────────────────
async function doVerify() {
    const text = refInput.value.trim();
    if (!text) { shake(refInput.closest('.editor')); return; }

    verifyBtn.classList.add('loading'); verifyBtn.disabled = true;
    resultsSec.classList.add('hidden');
    progressSec.classList.remove('hidden');
    progressFill.style.width = '8%';
    progressTitle.textContent = 'Đang xác minh...';
    progressDetail.textContent = 'Phân tích tham chiếu';

    const anim = animProgress();
    try {
        const r = await fetch('/api/verify', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ text, cross_validate: crossToggle.checked })
        });
        clearInterval(anim);
        progressFill.style.width = '100%';
        progressDetail.textContent = 'Hoàn tất!';
        if (!r.ok) throw new Error((await r.json()).error || 'HTTP ' + r.status);
        data = await r.json();
        await sleep(350);
        render();
        // Refresh counters after successful verification
        fetchStats();
    } catch(e) {
        clearInterval(anim);
        progressTitle.textContent = '❌ Lỗi';
        progressDetail.textContent = e.message;
    } finally {
        verifyBtn.classList.remove('loading'); verifyBtn.disabled = false;
    }
}

function animProgress() {
    let w = 8;
    const steps = [[20,'Trích xuất DOI...'],[40,'Truy vấn Crossref...'],[55,'Truy vấn DataCite...'],[70,'Đối chiếu OpenAlex...'],[85,'So khớp mờ...'],[92,'Tổng hợp...']];
    return setInterval(() => {
        if (w < 92) { w += Math.random()*3; w = Math.min(w,93); progressFill.style.width = w+'%';
            for (const [t,m] of steps) if (w >= t && w < t+5) progressDetail.textContent = m;
        }
    }, 700);
}

// ─── Render ──────────────────────────────────────────────────
function render() {
    progressSec.classList.add('hidden');
    resultsSec.classList.remove('hidden');
    renderSummary();
    renderCards();
    showDiffBanner();
    resultsSec.scrollIntoView({behavior:'smooth',block:'start'});
}

function renderSummary() {
    summary.innerHTML = SORDER.map((s,i) => {
        const n = s.k === 'total' ? data.total : (data.summary[s.k]||0);
        if (s.k !== 'total' && n === 0) return '';
        return `<div class="summary__card ${s.c}" style="animation-delay:${i*0.06}s"><div class="summary__num">${n}</div><div class="summary__label">${s.l}</div></div>`;
    }).join('');
}

function renderCards() {
    cardsContainer.innerHTML = data.results.map((r,i) => buildCard(r,i)).join('');
    document.querySelectorAll('.card__header').forEach(h =>
        h.addEventListener('click', () => h.closest('.card').classList.toggle('open'))
    );
    // Wire per-card copy buttons
    document.querySelectorAll('.card__copy-single').forEach(btn => {
        btn.addEventListener('click', e => {
            e.stopPropagation();
            const idx = parseInt(btn.dataset.index);
            const r = data.results[idx];
            const text = buildSingleCorrected(r, idx);
            copyToClipboard(text, `Đã copy trích dẫn [${r.ref_number || idx+1}]!`);
            btn.classList.add('copied');
            const orig = btn.innerHTML;
            btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M4 7l2.5 2.5L10 4.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg> Đã copy!';
            setTimeout(() => { btn.classList.remove('copied'); btn.innerHTML = orig; }, 1800);
        });
    });
}

function buildCard(r, i) {
    const v = V[r.verdict] || V.API_ERROR;
    const num = r.ref_number || i+1;
    const sc = r.scores ? r.scores.final : null;
    const body = view === 'comparison' ? buildComp(r) : `<div style="padding:1rem 1.25rem;font-family:var(--mono);font-size:.76rem;color:var(--text-secondary);line-height:1.7;word-break:break-word">${esc(r.raw_text)}</div>`;

    return `<div class="card" style="animation-delay:${Math.min(i*.04,.8)}s">
        <div class="card__header">
            <div class="card__left">
                <span class="card__num">[${num}]</span>
                <span class="badge badge--${v.css}">${v.vi}</span>
            </div>
            <div class="card__right">
                ${sc !== null ? `<span class="card__score" style="color:${sColor(sc)}">${sc.toFixed(1)}%</span>` : ''}
                ${r.cross_validated ? '<span class="card__cv">✓ OA</span>' : ''}
                <span class="card__chevron">▾</span>
            </div>
        </div>
        <div class="card__body">
            ${body}
            ${buildCardCopyBar(r, i)}
            ${buildScores(r)}
            ${r.error && r.verdict === 'RETRACTED' ? `<div class="card__error--retracted">${esc(r.error)}</div>` : r.error ? `<div class="card__error">${esc(r.error)}</div>` : ''}
        </div>
    </div>`;
}

function buildCardCopyBar(r, index) {
    const num = r.ref_number || index + 1;
    const corrected = buildSingleCorrected(r, index);
    const previewLine = corrected.split('\n')[0];
    const preview = previewLine.length > 120 ? previewLine.substring(0, 120) + '...' : previewLine;
    return `<div class="card__copybar">
        <div class="card__copybar-preview">${esc(preview)}</div>
        <button class="btn btn--accent btn--sm card__copy-single" data-index="${index}" title="Copy trích dẫn [${num}] đã sửa">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><rect x="4.5" y="4.5" width="8" height="8" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M9.5 4.5V3a1.5 1.5 0 00-1.5-1.5H3A1.5 1.5 0 001.5 3v5A1.5 1.5 0 003 9.5h1.5" stroke="currentColor" stroke-width="1.3"/></svg>
            Copy [${num}]
        </button>
    </div>`;
}

function buildComp(r) {
    const gt = r.ground_truth || {};
    const isBad = r.verdict === 'MISMATCH' || r.verdict === 'DEAD_DOI';
    const titleDiff = gt.title && r.cited_title && gt.title.toLowerCase() !== (r.cited_title||'').toLowerCase();
    const yearDiff = r.scores && r.scores.year_match === false;

    return `<div class="comp">
        <div class="comp__col">
            <div class="comp__tag comp__tag--original">Trích dẫn gốc</div>
            ${cRow('Tiêu đề', r.cited_title, isBad&&titleDiff ? 'comp__value--diff' : '')}
            ${doiRow('DOI', r.doi)}
            ${cRow('Năm', r.cited_year, yearDiff ? 'comp__value--diff' : '')}
            ${cRow('Tác giả', r.cited_authors)}
        </div>
        <div class="comp__col">
            <div class="comp__tag comp__tag--truth">Dữ liệu API</div>
            ${cRow('Tiêu đề', gt.title, gt.title ? 'comp__value--correct' : 'comp__value--dim')}
            ${doiRow('DOI', gt.doi)}
            ${cRow('Năm', gt.year, gt.year ? 'comp__value--correct' : '')}
            ${cRow('Tác giả', gt.authors ? gt.authors.join(', ') : null, gt.authors ? 'comp__value--correct' : '')}
            ${gt.source_journal ? cRow('Tạp chí', gt.source_journal) : ''}
            ${gt.api_source ? cRow('Nguồn API', gt.api_source, 'comp__value--mono') : ''}
        </div>
    </div>`;
}

function cRow(label, value, cls='') {
    const disp = value != null && value !== '' ? esc(String(value)) : '<span class="comp__value--dim">—</span>';
    return `<div class="comp__row"><div class="comp__label">${label}</div><div class="comp__value ${cls}">${disp}</div></div>`;
}

function doiRow(label, doi) {
    if (!doi) return cRow(label, null, 'comp__value--mono');
    const url = doi.startsWith('http') ? doi : `https://doi.org/${doi}`;
    const display = doi.replace(/^https?:\/\/doi\.org\//, '');
    return `<div class="comp__row"><div class="comp__label">${label}</div><div class="comp__value comp__value--mono"><a href="${esc(url)}" target="_blank" rel="noopener" class="doi-link">${esc(display)} ↗</a></div></div>`;
}

function buildScores(r) {
    if (!r.scores) return '';
    const s = r.scores;
    return `<div class="scores">
        <div class="scores__item"><span class="scores__label">Ratio</span><span class="scores__val" style="color:${sColor(s.ratio)}">${s.ratio.toFixed(1)}</span></div>
        <div class="scores__item"><span class="scores__label">Token Sort</span><span class="scores__val" style="color:${sColor(s.token_sort)}">${s.token_sort.toFixed(1)}</span></div>
        <div class="scores__item"><span class="scores__label">Token Set</span><span class="scores__val" style="color:${sColor(s.token_set)}">${s.token_set.toFixed(1)}</span></div>
        <div class="scores__item"><span class="scores__label">Final</span><span class="scores__val" style="color:${sColor(s.final)};font-size:.82rem">${s.final.toFixed(1)}%</span></div>
        ${s.year_match !== null ? `<div class="scores__item"><span class="scores__label">Năm</span><span class="scores__val" style="color:${s.year_match?'var(--green)':'var(--red)'}">${s.year_match?'✓ Khớp':'✗ Lệch'}</span></div>` : ''}
    </div>`;
}

// ─── Copy Corrected Content ─────────────────────────────────
function buildSingleCorrected(r, index) {
    const num = r.ref_number || index + 1;
    const gt = r.ground_truth;

    if (gt && gt.title) {
        const authors = gt.authors && gt.authors.length > 0
            ? formatAuthors(gt.authors) : (r.cited_authors || 'Unknown');
        const year = gt.year || r.cited_year || 'n.d.';
        const title = gt.title;
        const journal = gt.source_journal ? `. ${gt.source_journal}` : '';
        const doi = gt.doi ? `. https://doi.org/${gt.doi}` : (r.doi ? `. https://doi.org/${r.doi}` : '');
        return `[${num}]. ${authors} (${year}). ${title}${journal}${doi}`;
    }

    return `[${num}]. ${r.raw_text.replace(/^\[\d+\]\.?\s*/, '')}`;
}

function buildCorrectedText() {
    if (!data) return '';
    return data.results.map((r, i) => buildSingleCorrected(r, i)).join('\n');
}

function formatAuthors(authors) {
    if (authors.length <= 3) return authors.join(', ');
    return authors.slice(0, 3).join(', ') + ', ... & ' + authors[authors.length - 1];
}

function copyCorrected() {
    const text = buildCorrectedText();
    copyToClipboard(text, 'Đã copy bản đã sửa!');
}

function copyOriginal() {
    if (!data) return;
    const text = data.results.map(r => r.raw_text).join('\n');
    copyToClipboard(text, 'Đã copy bản gốc!');
}

function exportJSON() {
    if (!data) return;
    const blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'citeguard_report.json'; a.click();
    URL.revokeObjectURL(url);
    showToast('Đã xuất báo cáo JSON!');
}

function showDiffBanner() {
    if (!data) return;
    const correctable = data.results.filter(r =>
        r.ground_truth && r.ground_truth.title &&
        (r.verdict === 'VERIFIED' || r.verdict === 'SUSPICIOUS' || r.verdict === 'TITLE_MATCHED')
    ).length;
    const issues = data.results.filter(r => r.verdict === 'MISMATCH' || r.verdict === 'DEAD_DOI').length;

    if (correctable > 0 || issues > 0) {
        diffBanner.classList.remove('hidden');
        diffCount.textContent = correctable;
        if (issues > 0) {
            diffBanner.querySelector('.diff-banner__text').innerHTML =
                `<strong>${correctable}</strong> trích dẫn đã được sửa, <strong style="color:var(--red)">${issues}</strong> cần kiểm tra thủ công`;
        }
    } else {
        diffBanner.classList.add('hidden');
    }
}

// ─── View Switch ─────────────────────────────────────────────
function setView(v) {
    view = v;
    document.querySelectorAll('.toolbar__btn').forEach(b => b.classList.remove('active'));
    (v === 'comparison' ? viewComp : viewList).classList.add('active');
    if (data) renderCards();
}

// ─── Utilities ───────────────────────────────────────────────
function sColor(s) { return s >= 90 ? 'var(--green)' : s >= 70 ? 'var(--yellow)' : 'var(--red)'; }
function esc(t) { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; }
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function shake(el) { el.style.animation = 'none'; el.offsetHeight; el.style.animation = 'shake .4s ease'; setTimeout(() => el.style.animation = '', 500); }

function copyToClipboard(text, msg) {
    try {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.cssText = 'position:fixed;left:-9999px;top:-9999px;opacity:0';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        ta.setSelectionRange(0, ta.value.length);
        const ok = document.execCommand('copy');
        document.body.removeChild(ta);
        if (ok) { showToast(msg); return; }
    } catch(e) { /* fallback failed */ }

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text)
            .then(() => showToast(msg))
            .catch(() => showToast('❌ Copy thất bại — thử HTTPS'));
    } else {
        showToast('❌ Copy thất bại — trình duyệt không hỗ trợ');
    }
}

function showToast(msg) {
    toastMsg.textContent = msg;
    toast.classList.remove('hidden');
    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.classList.add('hidden'), 300); }, 2500);
}

// Inject shake keyframes
const sty = document.createElement('style');
sty.textContent = '@keyframes shake{0%,100%{transform:translateX(0)}25%{transform:translateX(-5px)}75%{transform:translateX(5px)}}';
document.head.appendChild(sty);

// Nav scroll effect
window.addEventListener('scroll', () => {
    const nav = $('nav');
    if (window.scrollY > 50) nav.style.borderBottomColor = 'rgba(0,0,0,0.08)';
    else nav.style.borderBottomColor = 'var(--border)';
});

// ─── History ─────────────────────────────────────────────────
let historyOpen = false;

historyBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    historyOpen = !historyOpen;
    if (historyOpen) { fetchHistory(); historyDropdown.classList.remove('hidden'); }
    else { historyDropdown.classList.add('hidden'); }
});

document.addEventListener('click', (e) => {
    if (historyOpen && !historyDropdown.contains(e.target) && !historyBtn.contains(e.target)) {
        historyOpen = false;
        historyDropdown.classList.add('hidden');
    }
});

function fetchHistory() {
    fetch('/api/history')
        .then(r => r.json())
        .then(sessions => {
            if (sessions.length > 0) {
                historyCount.textContent = sessions.length;
                historyCount.classList.remove('hidden');
            } else {
                historyCount.classList.add('hidden');
            }
            renderHistory(sessions);
        })
        .catch(() => {});
}

function renderHistory(sessions) {
    if (sessions.length === 0) {
        historyDropdown.innerHTML = `
            <div class="history-dropdown__header">
                <span class="history-dropdown__title">Lịch sử xác minh</span>
            </div>
            <div class="history-dropdown__empty">Chưa có lịch sử nào</div>`;
        return;
    }

    const items = sessions.map(s => {
        const sumParts = [];
        if (s.summary.RETRACTED) sumParts.push(`${s.summary.RETRACTED} retracted`);
        if (s.summary.VERIFIED) sumParts.push(`${s.summary.VERIFIED} verified`);
        if (s.summary.SUSPICIOUS) sumParts.push(`${s.summary.SUSPICIOUS} suspicious`);
        if (s.summary.MISMATCH) sumParts.push(`${s.summary.MISMATCH} mismatch`);
        if (s.summary.DEAD_DOI) sumParts.push(`${s.summary.DEAD_DOI} dead`);
        const sumText = sumParts.join(', ') || '';
        const statusDot = s.has_critical ? 'api-dot--cr' : 'api-dot--oa';
        return `<div class="history-item" data-id="${s.id}">
            <span class="history-item__icon"><span class="api-dot ${statusDot}" style="width:8px;height:8px"></span></span>
            <div class="history-item__info">
                <div class="history-item__refs">${s.total_refs} tài liệu${sumText ? ' — ' + sumText : ''}</div>
                <div class="history-item__preview">${esc(s.input_preview)}</div>
            </div>
            <span class="history-item__time">${timeAgo(s.created_at)}</span>
            <button class="history-item__delete" data-id="${s.id}" title="Xóa">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M3.5 3.5l7 7M10.5 3.5l-7 7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
            </button>
        </div>`;
    }).join('');

    historyDropdown.innerHTML = `
        <div class="history-dropdown__header">
            <span class="history-dropdown__title">Lịch sử xác minh</span>
            <button class="history-dropdown__clear" id="clearHistoryBtn">Xóa tất cả</button>
        </div>
        ${items}`;

    // Wire click-to-load
    historyDropdown.querySelectorAll('.history-item').forEach(item => {
        item.addEventListener('click', (e) => {
            if (e.target.closest('.history-item__delete')) return;
            loadSession(item.dataset.id);
        });
    });

    // Wire delete buttons
    historyDropdown.querySelectorAll('.history-item__delete').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteSession(btn.dataset.id);
        });
    });

    // Wire clear all
    const clearBtn2 = $('clearHistoryBtn');
    if (clearBtn2) clearBtn2.addEventListener('click', clearAllHistory);
}

function loadSession(id) {
    historyOpen = false;
    historyDropdown.classList.add('hidden');
    showToast('Đang tải...');

    fetch(`/api/history/${id}`)
        .then(r => r.json())
        .then(sessionData => {
            if (sessionData.error) { showToast('Lỗi: ' + sessionData.error); return; }
            data = sessionData;
            render();
            showToast('Đã tải kết quả từ lịch sử');
        })
        .catch(() => showToast('Không thể tải session'));
}

function deleteSession(id) {
    fetch(`/api/history/${id}`, { method: 'DELETE' })
        .then(() => { fetchHistory(); showToast('Đã xóa'); })
        .catch(() => showToast('Xóa thất bại'));
}

function clearAllHistory() {
    fetch('/api/history', { method: 'DELETE' })
        .then(() => { fetchHistory(); showToast('Đã xóa tất cả lịch sử'); })
        .catch(() => showToast('Xóa thất bại'));
}

function timeAgo(ts) {
    const diff = (Date.now() / 1000) - ts;
    if (diff < 60) return 'vừa xong';
    if (diff < 3600) return Math.floor(diff / 60) + ' phút';
    if (diff < 86400) return Math.floor(diff / 3600) + ' giờ';
    if (diff < 604800) return Math.floor(diff / 86400) + ' ngày';
    return new Date(ts * 1000).toLocaleDateString('vi-VN');
}

// Load history count on page load
fetchHistory();

// ─── Drag & Drop File Upload ─────────────────────────────────
['dragenter', 'dragover'].forEach(evt => {
    editor.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        editor.classList.add('editor--dragover');
    });
});

['dragleave', 'drop'].forEach(evt => {
    editor.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        editor.classList.remove('editor--dragover');
    });
});

editor.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length === 0) return;

    const file = files[0];
    const ext = file.name.split('.').pop().toLowerCase();
    const allowed = ['txt', 'bib', 'ris', 'csv', 'md'];

    if (!allowed.includes(ext) && !file.type.startsWith('text/')) {
        showToast(`Không hỗ trợ file .${ext} — Dùng .txt, .bib, .ris`);
        return;
    }

    const reader = new FileReader();
    reader.onload = (ev) => {
        refInput.value = ev.target.result;
        charCount.textContent = refInput.value.length + ' ký tự';
        showToast(`Đã tải ${file.name} (${(file.size / 1024).toFixed(1)} KB)`);

        // Update filename display
        const filenameEl = editor.querySelector('.editor__filename');
        if (filenameEl) filenameEl.textContent = file.name;
    };
    reader.readAsText(file, 'utf-8');
});
