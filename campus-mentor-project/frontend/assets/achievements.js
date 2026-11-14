/* Browser-only achievements. No chat completion or server reputation is inferred. */
(() => {
  const key = 'ppunppun-achievements-v1';
  const achievementVersion = 2;
  const definitions = [
    ['introduction', '🌱', '반가운 선배', '선배 소개를 처음 임시 저장하기', 'senior'],
    ['storyteller', '📖', '경험 나누미', '200자 이상의 경험 소개를 임시 저장하기', 'senior'],
    ['concern', '✍️', '용기 있는 한마디', '직접 쓴 고민으로 추천 요청하기', 'junior'],
    ['recommendation', '✨', '새로운 인연', '선배 3명 추천 결과 받기', 'junior'],
    ['first-step', '👣', '첫걸음', '선배에게 첫 메시지 보내기', 'junior'],
    ['explorer', '🧭', '인연 탐험가', '서로 다른 선배와 채팅 기록 3개 만들기', 'junior']
  ];
  const titles = ['새싹 선배', '열정적인 선배', '열혈한 선배', '든든한 선배', '믿음직한 선배', '다정한 길잡이', '캠퍼스 멘토', '빛나는 선배', '최고의 길잡이', '전설의 선배'];
  let state = { unlocked: {}, mentors: [], version: achievementVersion }, persistent = true, role = 'junior', storageKey = key, migrationPending = false;
  function browserStorages() {
    const stores = [];
    for (const name of ['localStorage', 'sessionStorage']) {
      try { stores.push(window[name]); } catch (_) {}
    }
    return stores;
  }
  function sessionFor(owner) {
    const sessionKey = owner === 'senior' ? 'ppunppun-senior-session' : 'ppunppun-junior-session';
    for (const storage of browserStorages()) {
      try {
        const session = JSON.parse(storage.getItem(sessionKey) || 'null');
        if (session) return session;
      } catch (_) {}
    }
    return null;
  }
  function accountKey() {
    try {
      const session = sessionFor(role);
      const id = role === 'senior' ? session?.mentor_id : session?.junior_id;
      return id ? `${key}:${role}:${encodeURIComponent(id)}` : key;
    } catch (_) { return key; }
  }
  function load() {
    storageKey = accountKey(); state = { unlocked: {}, mentors: [], version: achievementVersion }; migrationPending = false;
    for (const storage of browserStorages()) {
      try {
        const saved = JSON.parse(storage.getItem(storageKey) || 'null');
        if (saved && typeof saved.unlocked === 'object' && saved.unlocked && Array.isArray(saved.mentors)) {
          definitions.forEach(([id]) => { if (typeof saved.unlocked[id] === 'string') state.unlocked[id] = saved.unlocked[id]; });
          state.mentors = [...new Set(saved.mentors.filter(id => typeof id === 'string'))];
          if (saved.version !== achievementVersion) {
            // Preserve earned badges across app upgrades. Criteria changes must not
            // revoke an achievement or make its one-time toast appear again.
            migrationPending = true;
          }
          break;
        }
      } catch (_) { persistent = false; }
    }
  }
  load();
  const style = document.createElement('style');
  style.textContent = `.nav .achievement-nav{border:0;background:transparent;color:#687398;text-align:center;padding:8px 45px;border-radius:12px;font:inherit;font-size:13px;cursor:pointer}.nav .achievement-nav:hover{background:#f0efff;color:#5e43c8}.nav .achievement-nav:focus-visible{outline:3px solid #7656e2;outline-offset:2px}.nav .achievement-nav span{display:block;font-size:20px;margin-bottom:3px}@media(max-width:760px){.nav a,.nav .achievement-nav{padding:8px clamp(12px,5vw,35px)}}.achievement-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:flex-end}.achievement-button{border:1px solid #ded9fa;background:#fff;color:#5742b0;border-radius:14px;padding:10px 14px;font:inherit;font-size:13px;cursor:pointer}.achievement-button strong{font-size:19px;display:block;margin-top:3px}.achievement-dialog{border:1px solid #ded9fa;border-radius:24px;padding:26px;color:#1b2451;background:#fafaff;width:min(560px,calc(100% - 28px));max-height:85vh;overflow:auto;font-family:inherit}.achievement-dialog::backdrop{background:#18234d66}.achievement-heading{display:flex;justify-content:space-between;align-items:center;gap:12px}.achievement-dialog h2{font-size:22px;margin:0}.achievement-dialog p{font-size:13px;line-height:1.7;color:#647092}.achievement-items{display:grid;gap:10px}.achievement-item{background:white;border:1px solid #e1e5f5;border-radius:14px;padding:15px}.achievement-item p{margin:6px 0 0}.achievement-locked{background:#f1f2f8;color:#69728c}.achievement-earned{background:#edeaff;border-color:#b9a9f5;color:#382978}.achievement-current{border:2px solid #7656e2}.achievement-toast{position:fixed;bottom:110px;left:50%;transform:translateX(-50%);background:#382978;color:white;padding:14px 22px;border-radius:16px;z-index:20;max-width:90%;box-shadow:0 8px 30px #30346b30}.achievement-button:focus-visible{outline:3px solid #7656e2;outline-offset:3px}@media(max-width:480px){.achievement-actions{gap:5px}.achievement-button{padding:8px;font-size:12px}header{gap:8px;flex-wrap:wrap}}`;
  document.head.append(style);
  const actions = document.createElement('div'); actions.className = 'achievement-actions';
  const temperature = document.createElement('button'); temperature.type = 'button'; temperature.className = 'achievement-button'; temperature.innerHTML = '학점온도 <strong>0.000 / 4.500</strong>'; temperature.hidden = true;
  const badges = document.createElement('button'); badges.type = 'button'; badges.className = 'achievement-nav'; badges.setAttribute('aria-haspopup', 'dialog'); badges.innerHTML = '<span aria-hidden="true">🏅</span>업적';
  actions.append(temperature); const header = document.querySelector('header'); const login = header.querySelector('#login'); if (login) actions.append(login); header.append(actions); actions.style.marginLeft = 'auto'; document.querySelector('.nav').append(badges);
  const dialog = document.createElement('dialog'); dialog.className = 'achievement-dialog'; dialog.setAttribute('aria-labelledby', 'achievement-title'); document.body.append(dialog);
  const toast = document.createElement('div'); toast.className = 'achievement-toast'; toast.setAttribute('role', 'status'); toast.hidden = true; document.body.append(toast);
  let timeout, toastShowing = false;
  const toastQueue = [];
  function refresh() { badges.setAttribute('aria-label', '업적, 달성한 배지 ' + definitions.filter(([id,,,,owner]) => owner === role && state.unlocked[id]).length + '개'); }
  function save() {
    state.version = achievementVersion;
    let saved = false;
    for (const storage of browserStorages()) {
      try { storage.setItem(storageKey, JSON.stringify(state)); saved = true; } catch (_) {}
    }
    if (!saved) persistent = false;
    refresh();
  }
  function refreshOpenBadges() {
    if (!dialog.open || dialog.dataset.mode !== 'badges') return;
    dialog.querySelectorAll('[data-achievement-id]').forEach(row => {
      const item = definitions.find(definition => definition[0] === row.dataset.achievementId);
      if (!item) return;
      const [id, icon, name, description] = item;
      const earned = Boolean(state.unlocked[id]);
      row.classList.toggle('achievement-earned', earned);
      row.classList.toggle('achievement-locked', !earned);
      row.querySelector('strong').textContent = (earned ? icon : '🔒') + ' ' + name + ' · ' + (earned ? '달성' : '미달성');
      row.querySelector('p').textContent = description;
    });
  }
  function showNextToast() {
    if (toastShowing || !toastQueue.length) return;
    toastShowing = true;
    toast.textContent = toastQueue.shift();
    toast.hidden = false;
    timeout = setTimeout(() => {
      toast.hidden = true;
      toastShowing = false;
      showNextToast();
    }, 3500);
  }
  function award(id) {
    const item = definitions.find(d => d[0] === id);
    if (!item || state.unlocked[id]) return;
    state.unlocked[id] = new Date().toISOString(); save();
    refreshOpenBadges();
    toastQueue.push(item[1] + ' ‘' + item[2] + '’ 배지를 받았어요!');
    showNextToast();
  }
  async function syncJuniorProgress() {
    if (role !== 'junior') return;
    try {
      const session = sessionFor('junior');
      if (!session?.token) return;
      const response = await fetch('/api/junior-achievements', { headers: { Authorization: 'Bearer ' + session.token } });
      if (!response.ok) return;
      const data = await response.json();
      (Array.isArray(data.unlocked) ? data.unlocked : []).forEach(award);
    } catch (_) {}
  }
  function open(mode) {
    dialog.dataset.mode = mode;
    dialog.replaceChildren();
    const head = document.createElement('div'); head.className = 'achievement-heading';
    const title = document.createElement('h2'); title.id = 'achievement-title'; title.textContent = mode === 'temperature' ? '나의 학점온도' : '나의 배지';
    const close = document.createElement('button'); close.className = 'achievement-button'; close.type = 'button'; close.textContent = '닫기'; close.onclick = () => dialog.close(); head.append(title, close); dialog.append(head);
    const info = document.createElement('p'); info.textContent = mode === 'temperature' ? '현재 0.000 · 새싹 선배. 실제 성적이 아닌 활동 지표예요. 4.500이 최대이며, 점수 적립은 추후 연결됩니다.' : '로그인한 계정별로 이 브라우저에 저장되는 ' + (role === 'senior' ? '선배' : '후배') + '용 배지예요.'; dialog.append(info);
    if (!persistent) { const warning = document.createElement('p'); warning.textContent = '브라우저 저장이 제한되어 새로고침하면 이번 기록이 사라질 수 있어요.'; dialog.append(warning); }
    const items = document.createElement('div'); items.className = 'achievement-items'; dialog.append(items);
    if (mode === 'temperature') {
      titles.forEach((name, index) => { const row = document.createElement('div'); row.className = 'achievement-item' + (index === 0 ? ' achievement-current' : ''); row.textContent = (index * .5).toFixed(3) + ' 이상 · ' + name + (index === 0 ? ' (현재)' : ''); items.append(row); });
    } else {
      definitions.filter(d => d[4] === role).forEach(([id, icon, name, description]) => { const earned = Boolean(state.unlocked[id]); const row = document.createElement('div'); row.dataset.achievementId = id; row.className = 'achievement-item' + (earned ? ' achievement-earned' : ' achievement-locked'); const label = document.createElement('strong'); label.textContent = (earned ? icon : '🔒') + ' ' + name + ' · ' + (earned ? '달성' : '미달성'); const detail = document.createElement('p'); detail.textContent = description; row.append(label, detail); items.append(row); });
      const note = document.createElement('p'); note.textContent = '첫걸음은 첫 메시지 전송 성공 시, 인연 탐험가는 채팅 기록이 3개 이상 쌓이면 달성돼요.'; dialog.append(note);
    }
    dialog.showModal();
  }
  temperature.onclick = () => open('temperature'); badges.onclick = () => open('badges');
  window.PpunAchievements = {
    award,
    setRole(value) { role = value === 'senior' ? 'senior' : 'junior'; load(); temperature.hidden = role !== 'senior'; refresh(); if (migrationPending) { save(); migrationPending = false; } if (role === 'junior') syncJuniorProgress(); },
    selectMentor(id) { if (id) window.ppunSelectedMentor = String(id); },
    chatWithMentor(id) { if (!id || role !== 'junior') return; const value = String(id); if (!state.mentors.includes(value)) state.mentors.push(value); save(); award('first-step'); syncJuniorProgress(); }
  };
  refresh();
  try { sessionStorage.removeItem('ppunppun-pending-achievement-toasts'); } catch (_) {}
  if (migrationPending) { save(); migrationPending = false; }
})();
