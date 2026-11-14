(() => {
  const nav=document.querySelector('.nav'); if(!nav)return;
  const achievement=nav.querySelector('.achievement-nav');
  nav.querySelectorAll('a').forEach(a=>a.remove());
  function link(icon,label,url){const a=document.createElement('a');const span=document.createElement('span');span.textContent=icon;a.append(span,document.createTextNode(label));a.href=url;nav.insertBefore(a,achievement);return a}
  link('☘','홈','../main.html');
  link('🤖','학교봇','../school-bot/');
  const chat=link('💬','채팅창','#chat');
  link('🛡','관리자','../admin.html');
  function get(key){try{return JSON.parse(localStorage.getItem(key)||'null')}catch(e){return null}}
  chat.onclick=event=>{event.preventDefault();const senior=get('ppunppun-senior-session'),junior=get('ppunppun-junior-session');let role='';try{role=localStorage.getItem('ppunppun-active-role')||''}catch(e){}
    if(!(role==='senior'&&senior?.mentor_id&&senior?.token)&&!(role==='junior'&&junior?.junior_id&&junior?.token))role=junior?.junior_id&&junior?.token?'junior':senior?.mentor_id&&senior?.token?'senior':'';
    if(role==='senior'){location.href='../chat/index.html?role=senior&mentor='+encodeURIComponent(senior.mentor_id);return}
    if(role==='junior'){location.href='../chat/index.html?role=junior';return}
    alert('채팅을 보려면 먼저 선배 또는 후배로 로그인해 주세요.');
  };
  try{const role=localStorage.getItem('ppunppun-active-role');if(role==='senior'||role==='junior')window.PpunAchievements?.setRole(role)}catch(e){}
})();
