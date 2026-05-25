/**
 * Citation Verifier — Premium Web App
 * Handles verification, comparison rendering, and copy corrected content.
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

let data = null, view = 'comparison';

const V = {
    VERIFIED:      { icon:'✅', vi:'Xác minh',     css:'verified' },
    SUSPICIOUS:    { icon:'⚠️', vi:'Nghi ngờ',      css:'suspicious' },
    MISMATCH:      { icon:'❌', vi:'Sai lệch',     css:'mismatch' },
    DEAD_DOI:      { icon:'💀', vi:'DOI ảo',       css:'dead_doi' },
    NO_DOI:        { icon:'🔍', vi:'Không DOI',    css:'no_doi' },
    TITLE_MATCHED: { icon:'📗', vi:'Khớp tiêu đề', css:'title_matched' },
    API_ERROR:     { icon:'🔌', vi:'Lỗi API',      css:'api_error' },
};

const SORDER = [
    {k:'total',   l:'Tổng cộng',   c:'s-total'},
    {k:'VERIFIED',l:'Xác minh',    c:'s-verified'},
    {k:'SUSPICIOUS',l:'Nghi ngờ',  c:'s-suspicious'},
    {k:'MISMATCH',l:'Sai lệch',   c:'s-mismatch'},
    {k:'DEAD_DOI',l:'DOI ảo',     c:'s-dead'},
    {k:'NO_DOI',  l:'Không DOI',   c:'s-nodoi'},
    {k:'TITLE_MATCHED',l:'Khớp tiêu đề',c:'s-matched'},
];

// Events
refInput.addEventListener('input', () => charCount.textContent = refInput.value.length + ' ký tự');
clearBtn.addEventListener('click', () => { refInput.value = ''; charCount.textContent = '0 ký tự'; refInput.focus(); });
verifyBtn.addEventListener('click', doVerify);
viewComp.addEventListener('click', () => setView('comparison'));
viewList.addEventListener('click', () => setView('list'));
copyOriginalBtn.addEventListener('click', () => copyOriginal());
copyCorrectedBtn.addEventListener('click', () => copyCorrected());
diffCopyBtn.addEventListener('click', () => copyCorrected());
exportJsonBtn.addEventListener('click', () => exportJSON());

// Verify
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

// Render
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
            // Animate the button
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
    const body = view === 'comparison' ? buildComp(r) : `<div style="padding:1rem 1.25rem;font-family:var(--mono);font-size:.78rem;color:var(--text-secondary);line-height:1.7;word-break:break-word">${esc(r.raw_text)}</div>`;

    return `<div class="card" style="animation-delay:${Math.min(i*.04,.8)}s">
        <div class="card__header">
            <div class="card__left">
                <span class="card__num">[${num}]</span>
                <span class="badge badge--${v.css}">${v.icon} ${v.vi}</span>
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
            ${r.error ? `<div class="card__error">⚠ ${esc(r.error)}</div>` : ''}
        </div>
    </div>`;
}

function buildCardCopyBar(r, index) {
    const num = r.ref_number || index + 1;
    const corrected = buildSingleCorrected(r, index);
    // Show only the first line in preview (multi-line for MISMATCH warnings)
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
            <div class="comp__tag comp__tag--original">📝 Trích dẫn gốc (chưa sửa)</div>
            ${cRow('Tiêu đề', r.cited_title, isBad&&titleDiff ? 'comp__value--diff' : '')}
            ${doiRow('DOI', r.doi)}
            ${cRow('Năm', r.cited_year, yearDiff ? 'comp__value--diff' : '')}
            ${cRow('Tác giả', r.cited_authors)}
        </div>
        <div class="comp__col">
            <div class="comp__tag comp__tag--truth">✅ Dữ liệu thực tế (đã sửa)</div>
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
        <div class="scores__item"><span class="scores__label">Final</span><span class="scores__val" style="color:${sColor(s.final)};font-size:.85rem">${s.final.toFixed(1)}%</span></div>
        ${s.year_match !== null ? `<div class="scores__item"><span class="scores__label">Năm</span><span class="scores__val" style="color:${s.year_match?'var(--green)':'var(--red)'}">${s.year_match?'✓ Khớp':'✗ Lệch'}</span></div>` : ''}
    </div>`;
}

// ─── Copy Corrected Content ─────────────────────────────────────
function buildSingleCorrected(r, index) {
    const num = r.ref_number || index + 1;
    const gt = r.ground_truth;

    // If we have ground truth data from API, build a clean corrected reference
    if (gt && gt.title) {
        const authors = gt.authors && gt.authors.length > 0
            ? formatAuthors(gt.authors) : (r.cited_authors || 'Unknown');
        const year = gt.year || r.cited_year || 'n.d.';
        const title = gt.title;
        const journal = gt.source_journal ? `. ${gt.source_journal}` : '';
        const doi = gt.doi ? `. https://doi.org/${gt.doi}` : (r.doi ? `. https://doi.org/${r.doi}` : '');
        return `[${num}]. ${authors} (${year}). ${title}${journal}${doi}`;
    }

    // No ground truth available — keep original text
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
    a.href = url; a.download = 'verification_report.json'; a.click();
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

// ─── View Switch ─────────────────────────────────────────────────
function setView(v) {
    view = v;
    document.querySelectorAll('.toolbar__btn').forEach(b => b.classList.remove('active'));
    (v === 'comparison' ? viewComp : viewList).classList.add('active');
    if (data) renderCards();
}

// ─── Utilities ───────────────────────────────────────────────────
function sColor(s) { return s >= 90 ? 'var(--green)' : s >= 70 ? 'var(--yellow)' : 'var(--red)'; }
function esc(t) { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; }
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function shake(el) { el.style.animation = 'none'; el.offsetHeight; el.style.animation = 'shake .4s ease'; setTimeout(() => el.style.animation = '', 500); }

function copyToClipboard(text, msg) {
    // Use fallback textarea method first — works on HTTP localhost
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
    } catch(e) { /* fallback failed, try clipboard API */ }

    // Try modern Clipboard API (requires HTTPS or localhost)
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
let lastScroll = 0;
window.addEventListener('scroll', () => {
    const nav = $('nav');
    if (window.scrollY > 50) nav.style.borderBottomColor = 'rgba(255,255,255,0.08)';
    else nav.style.borderBottomColor = 'rgba(255,255,255,0.04)';
});
