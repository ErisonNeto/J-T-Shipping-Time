let evoChart;
let filtrosData = { scs: [], bases: [] };

const metas = {6: 25.6, 7: 6.0, 8: 23.4};
const $ = s => document.querySelector(s);
const fmtH = v => `${Number(v || 0).toLocaleString('pt-BR', {minimumFractionDigits:2, maximumFractionDigits:2})} h`;
const fmtN = v => Number(v || 0).toLocaleString('pt-BR');
const fmtDate = d => d ? d.split('-').reverse().join('/') : '--';
const dataD1 = () => {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
};
const esc = v => String(v ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

async function get(url){
  const r = await fetch(url);
  if(!r.ok) throw new Error(await r.text());
  return r.json();
}

function queryParams(){
  const p = new URLSearchParams();
  p.set('data_inicial', $('#dataInicial').value);
  p.set('data_final', $('#dataFinal').value);
  if($('#scSelect').value) p.set('sc', $('#scSelect').value);
  if($('#baseSelect').value) p.set('base', $('#baseSelect').value);
  return p;
}

function performanceClass(valor, meta){
  if(valor <= meta) return 'ok';
  if(valor <= meta * 1.15) return 'warn';
  return 'bad';
}

function updateStage(stage, valor){
  const meta = metas[stage];
  $(`#k${stage}`).textContent = fmtH(valor);
  const status = performanceClass(Number(valor), meta);
  const dot = $(`#dot${stage}`);
  dot.className = `status-dot ${status}`;
  const pct = Math.min(100, (Number(valor) / (meta * 1.6)) * 100);
  const bar = $(`#bar${stage}`);
  bar.style.width = `${pct}%`;
  bar.className = status;
}

function tabelaBases(rows, meta){
  if(!rows.length) return '<div class="empty">Nenhuma base encontrada para este recorte.</div>';
  return `<table class="rank"><thead><tr><th>Base</th><th>S/C</th><th>Horas</th><th>Pacotes</th></tr></thead><tbody>${rows.map(r=>{
    const cls = performanceClass(Number(r.horas), meta);
    return `<tr><td><div class="base-name">${esc(r.base)}</div><small>${esc(r.codigo_base)}</small></td><td><span class="sc-name">${esc(r.sc || '-')}</span></td><td class="num"><span class="time-pill ${cls}">${fmtH(r.horas)}</span></td><td class="num">${fmtN(r.pacotes)}</td></tr>`;
  }).join('')}</tbody></table>`;
}

function tabelaSC(rows){
  if(!rows.length) return '<div class="empty">Nenhum S/C encontrado para este recorte.</div>';
  return `<table class="rank"><thead><tr><th>S/C</th><th>Bases</th><th>Pacotes</th><th>E6</th><th>E7</th><th>E8</th><th>Total</th></tr></thead><tbody>${rows.map(r=>`<tr><td><div class="sc-main">${esc(r.sc)}</div></td><td class="num">${fmtN(r.bases)}</td><td class="num">${fmtN(r.pacotes)}</td><td class="num">${fmtH(r.etapa_6)}</td><td class="num">${fmtH(r.etapa_7)}</td><td class="num">${fmtH(r.etapa_8)}</td><td class="num"><span class="total-pill">${fmtH(r.total)}</span></td></tr>`).join('')}</tbody></table>`;
}

function atualizarBases(){
  const sc = $('#scSelect').value;
  const atual = $('#baseSelect').value;
  const bases = filtrosData.bases.filter(b => !sc || b.sc === sc);
  $('#baseSelect').innerHTML = '<option value="">Todas as bases</option>' + bases.map(b => `<option value="${esc(b.base)}">${esc(b.base)} · ${fmtN(b.pacotes)} pct</option>`).join('');
  if(bases.some(b => b.base === atual)) $('#baseSelect').value = atual;
}

async function carregarFiltrosData(){
  const di = $('#dataInicial').value;
  const df = $('#dataFinal').value;
  if(!di || !df) return;
  filtrosData = await get(`/api/filtros?data_inicial=${encodeURIComponent(di)}&data_final=${encodeURIComponent(df)}`);
  const scAtual = $('#scSelect').value;
  $('#scSelect').innerHTML = '<option value="">Todos os S/C</option>' + filtrosData.scs.map(sc => `<option value="${esc(sc)}">${esc(sc)}</option>`).join('');
  if(filtrosData.scs.includes(scAtual)) $('#scSelect').value = scAtual;
  atualizarBases();
}

async function carregar(){
  const di = $('#dataInicial').value;
  const df = $('#dataFinal').value;
  if(!di || !df) return;
  $('#dataTitulo').textContent = di === df ? fmtDate(di) : `${fmtDate(di)} → ${fmtDate(df)}`;

  const p = queryParams();
  const top = $('#topSelect').value || '0';

  try {
    const [k,b6,b7,b8,sc,evo] = await Promise.all([
      get(`/api/kpis?${p}`),
      get(`/api/piores-bases?${p}&etapa=6&limite=${top}`),
      get(`/api/piores-bases?${p}&etapa=7&limite=${top}`),
      get(`/api/piores-bases?${p}&etapa=8&limite=${top}`),
      get(`/api/piores-sc?${p}&limite=${top}`),
      get(`/api/evolutivo?${p}`)
    ]);

    updateStage(6, k.etapa_6);
    updateStage(7, k.etapa_7);
    updateStage(8, k.etapa_8);
    $('#kp').textContent = fmtN(k.pacotes);
    $('#kt').textContent = fmtH(k.total_6_8);
    $('#kBases').textContent = fmtN(k.bases);
    $('#kGargalo').textContent = `${k.gargalo} · ${fmtH(k.gargalo_h)}`;

    const recorte = $('#baseSelect').value || $('#scSelect').value || 'Todas as bases';
    $('#kRecorte').textContent = recorte;

    $('#b6').innerHTML = tabelaBases(b6, metas[6]);
    $('#b7').innerHTML = tabelaBases(b7, metas[7]);
    $('#b8').innerHTML = tabelaBases(b8, metas[8]);
    $('#sc').innerHTML = tabelaSC(sc);
    renderEvo(evo);
  } catch(e){
    console.error(e);
    ['#b6','#b7','#b8','#sc'].forEach(id => $(id).innerHTML = '<div class="empty">Sem dados para os filtros selecionados.</div>');
  }
}

function renderEvo(rows){
  const ctx = $('#evoChart');
  if(evoChart) evoChart.destroy();
  evoChart = new Chart(ctx, {
    type:'line',
    data:{
      labels: rows.map(r=>fmtDate(r.data)),
      datasets:[
        {label:'Etapa 6', data:rows.map(r=>r.etapa_6), borderColor:'#d71920', backgroundColor:'#d71920', borderWidth:2, pointRadius:3, tension:.3},
        {label:'Etapa 7', data:rows.map(r=>r.etapa_7), borderColor:'#111827', backgroundColor:'#111827', borderWidth:2, pointRadius:3, tension:.3},
        {label:'Etapa 8', data:rows.map(r=>r.etapa_8), borderColor:'#7b8189', backgroundColor:'#7b8189', borderWidth:2, pointRadius:3, tension:.3},
        {label:'Total 6+7+8', data:rows.map(r=>r.total), borderColor:'#8b1117', backgroundColor:'#8b1117', borderWidth:3, pointRadius:4, tension:.3}
      ]
    },
    options:{
      responsive:true,
      maintainAspectRatio:false,
      interaction:{mode:'index',intersect:false},
      plugins:{legend:{position:'bottom',labels:{usePointStyle:true,boxWidth:8,padding:18}}},
      scales:{
        x:{grid:{display:false},ticks:{maxRotation:0}},
        y:{beginAtZero:true,title:{display:true,text:'Horas'},grid:{color:'rgba(15,23,42,.06)'}}
      }
    }
  });
}

async function atualizarPeriodo(){
  const di = $('#dataInicial').value;
  const df = $('#dataFinal').value;
  if(!di || !df) return;
  if(di > df){
    $('#dataFinal').value = di;
  }
  await carregarFiltrosData();
  await carregar();
}

async function init(){
  const datas = await get('/api/datas');
  if(!datas.length) throw new Error('Nenhuma data disponível');
  const d1 = dataD1();
  $('#dataInicial').value = d1;
  $('#dataFinal').value = d1;
  await carregarFiltrosData();

  $('#dataInicial').addEventListener('change', atualizarPeriodo);
  $('#dataFinal').addEventListener('change', atualizarPeriodo);
  $('#scSelect').addEventListener('change', async()=>{ atualizarBases(); await carregar(); });
  $('#baseSelect').addEventListener('change', carregar);
  $('#topSelect').addEventListener('change', carregar);
  $('#resetFilters').addEventListener('click', async()=>{
    $('#dataInicial').value = d1;
    $('#dataFinal').value = d1;
    $('#scSelect').value='';
    atualizarBases();
    $('#baseSelect').value='';
    $('#topSelect').value='0';
    await carregarFiltrosData();
    await carregar();
  });

  await carregar();
}

init().catch(e=>{
  console.error(e);
  alert('Erro ao carregar dashboard. Verifique o backend/Supabase.');
});
