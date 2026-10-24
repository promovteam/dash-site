#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Remendo do dash (dash-site/index.html): botão "🎤 Abrir a apresentação deste lead".
Bruno 24/10/2026: "será que tem como puxar como ele preencheu e foi qualificado pela apresentação? sem ser cheio de
loucura?" · "essas outras perguntas o closer preenche no diagnóstico".

O que entra (3 trocas pequenas, por âncora):
  1. na ficha da reunião (janela "modal-lead"), no cabeçalho, embaixo do nome: o botão "🎤 Abrir a apresentação deste lead";
  2. no menu do evento da Agenda (abaixo de "📇 Ver ficha do lead"): o mesmo item;
  3. antes do </body>: o script que monta os campos e abre a apresentação.

Ao tocar, o dash grava localStorage['spark-campos'] = {ts, f:{...}, origem:{campo:'formulario'|'qualificacao'}} com o que
existe sobre a pessoa e abre apresentacao-spark/ numa aba nova (mesmo site = mesmo localStorage; a apresentação usa por 8 h).
  - Os dados NÃO vão no link: ficam só no navegador de quem tocou.
  - Nada de CPF, telefone ou e-mail nos campos; do nome, só o primeiro.
  - Só aparece para quem vê o item "🎤 Apresentação do closer" do menu (administradores e closers).
  - O que não existe nos dados fica vazio: o closer pergunta e preenche no diagnóstico.
  - Dentro da Clint (o dash fica num quadro da página da Clint) o Chrome separa o armazenamento do quadro do da aba nova:
    aí a aba nova abre primeiro o versao.txt do próprio site, recebe os dados e só então vai para a apresentação.

Por âncora e IDEMPOTENTE: os blocos ficam entre marcadores "apresentacao-spark:lead-…"; rodar de novo só troca o que está
entre eles (e, se nada mudou, não mexe no arquivo nem na versão). Quando muda o arquivo, guarda uma cópia do antes em
~/promov-apresentacao/copias-dash/ e sobe a versão do dash (VERSAO_DASH + versao.txt), como os outros remendos.

Uso:  python3 remendo-lead.py CAMINHO/index.html             aplica (e acerta versao.txt ao lado)
      python3 remendo-lead.py CAMINHO/index.html --conferir  só diz o que faria (não mexe em nada)
      python3 remendo-lead.py CAMINHO/index.html --tirar     tira os 3 blocos (volta ao dash sem o botão)
"""
import datetime, os, re, shutil, sys

BOT_INI, BOT_FIM = '<!-- 🎤 apresentacao-spark:lead-botao:inicio -->', '<!-- apresentacao-spark:lead-botao:fim -->'
AG_INI, AG_FIM = '  // 🎤 apresentacao-spark:lead-agenda:inicio', '  // apresentacao-spark:lead-agenda:fim'
JS_INI, JS_FIM = '<!-- 🎤 apresentacao-spark:lead-script:inicio -->', '<!-- apresentacao-spark:lead-script:fim -->'

# âncoras (cada uma tem de aparecer UMA vez no index.html)
ANCORA_BOT = '''      <span style="font-size:.7rem;color:var(--muted);font-weight:600;" id="fl-sub">—</span>\n'''   # o botão fica no cabeçalho, embaixo do nome
# (NÃO pode ser um filho novo da .modal: o layout da ficha usa a posição dos filhos — .dtl-card:nth-child(3) — e desmontaria)
ANCORA_AG = '''  h += '<div class="lm-item" onclick="fecharSlotMenu();fichaDoEvento()">📇 Ver ficha do lead</div>';\n'''

BOT = BOT_INI + '''
      <div id="fl-apres" style="display:none;margin-top:8px;"><button type="button" onclick="event.stopPropagation();apsAbrirLead()" title="Abre a apresentação do closer numa aba nova, já com o diagnóstico deste lead (o que ele respondeu no formulário e o que a pré-venda anotou). Os dados ficam só neste navegador: não vão no link." style="display:inline-flex;align-items:center;gap:6px;padding:6px 13px;border-radius:999px;font:inherit;font-size:.72rem;font-weight:800;cursor:pointer;color:#f6a350;border:1px solid rgba(246,163,80,.45);background:rgba(246,163,80,.1);">🎤 Abrir a apresentação deste lead</button></div>
''' + BOT_FIM + '\n'

AG = AG_INI + '''
  try { if (window.apsPode && apsPode()) h += '<div class="lm-item" onclick="fecharSlotMenu();apsAbrirDoEvento()">🎤 Abrir a apresentação deste lead</div>'; } catch (eAps) {}
''' + AG_FIM + '\n'

JS = JS_INI + r'''
<script>
// 🎤 APRESENTAÇÃO DESTE LEAD (Bruno 24/10/2026: "será que tem como puxar como ele preencheu e foi qualificado pela
// apresentação? sem ser cheio de loucura?" · "essas outras perguntas o closer preenche no diagnóstico").
// Na ficha da reunião e no menu do evento da Agenda, "🎤 Abrir a apresentação deste lead" grava
// localStorage['spark-campos'] = { ts, f: {...}, origem: { campo: 'formulario' | 'qualificacao' } } e abre a apresentação
// (apresentacao-spark/, mesmo site = mesmo localStorage; ela usa por 8 h) numa aba nova.
//  • De onde vem cada campo:
//    formulário do diagnóstico (planilha de leads / base do site): dor (objetivos), produto (fonte de renda), seguidores
//    (número; se ele só marcou a faixa, vai em seguidoresFaixa), investimento; o Instagram que o robô lê (aba IG Perfis):
//    seguidores exatos e o perfil pela bio, só quando UMA profissão aparece clara;
//    qualificação (a reunião na planilha de vendas): leadNome (primeiro nome), programa (o produto da reunião marcada),
//    notaPreVenda (a observação, sem e-mail, telefone, @, links e marcas do sistema) e objecao (pelas palavras da nota).
//  • Os dados NÃO vão no link: ficam só no navegador de quem tocou. Nada de CPF, telefone ou e-mail; do nome, só o primeiro.
//  • Só para quem vê o item "🎤 Apresentação do closer" do menu (administradores e closers).
//  • O que não existe fica vazio: o closer pergunta e preenche no diagnóstico da apresentação.
(function () {
  var URL_APS = 'apresentacao-spark/';
  var URL_SITE = 'https://promovteam.github.io/dash-site/apresentacao-spark/';
  var ORIGEM_IG = 'formulario';   // seguidores/perfil do Instagram: a ficha já mostra junto do formulário ('instagram' se a apresentação quiser separar)
  var PERFIL_PELA_BIO = true;     // false = não sugere o perfil pela bio do Instagram

  function pode() {   // a mesma regra do item "🎤 Apresentação do closer" do menu
    try {
      if (typeof ehAdm === 'function' && ehAdm()) return true;
      var lg = localStorage.getItem('v2Login'); if (!lg) return false;
      var p = String(lg).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').split(/\s+/)[0];
      return typeof CLOSERS !== 'undefined' && CLOSERS.some(function (c) { return c.key === p; });
    } catch (e) { return false; }
  }
  function nz(t) {
    try { return v2norm(t); } catch (e) { return String(t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/-/g, ' ').replace(/\s+/g, ' ').trim(); }
  }
  function aviso(t) { try { avisoRapido(t); } catch (e) { try { alert(t); } catch (e2) {} } }

  // "Pra. MARIA de Souza (L-123)" → "Maria"
  var TITULOS = /^(pr|pra|pastor|pastora|dr|dra|doutor|doutora|ap|apostolo|apostola|bispo|bispa|miss|missionario|missionaria|prof|profa|professor|professora|sr|sra|rev)$/;
  function primeiroNome(nome) {
    var p = String(nome || '').replace(/\([^)]*\)|\[[^\]]*\]/g, ' ').split(/[\s|,;\/·]+/);
    for (var i = 0; i < p.length; i++) {
      var w = p[i].replace(/[^A-Za-zÀ-ÖØ-öø-ÿ'-]/g, '').replace(/^['-]+|['-]+$/g, '');
      if (w.length < 2 || TITULOS.test(nz(w))) continue;
      if (w === w.toUpperCase() || w === w.toLowerCase()) w = w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
      return w;
    }
    return '';
  }
  // o produto da reunião marcada ("Programa Spark Anual", "Mentoria Legado Digital"…): só quando diz o programa
  function programaDe(prod) {
    var p = nz(prod);
    if (!p) return '';
    if (/growth/.test(p)) return 'growth';
    if (/semestral/.test(p)) return 'semestral';
    if (/legado digital|mentoria legado|\bwld\b/.test(p)) return 'legado';
    if (/spark/.test(p)) return 'spark';
    return '';
  }
  // "2.500", "3 mil", "1,5k" → número; faixa ("1.000 a 5.000", "Menos de 1.000") → null
  function numeroSeg(t) {
    var s = nz(t).replace(/seguidores?/g, '').trim();
    var m = s.match(/^(\d{1,3}(?:[.\s]\d{3})+|\d+)(?:,(\d+))?\s*(mil|k)?$/);
    if (!m) return null;
    var v = parseFloat(m[1].replace(/[.\s]/g, '') + (m[2] ? '.' + m[2] : ''));
    if (m[3]) v *= 1000;
    return isFinite(v) ? Math.round(v) : null;
  }
  // "Como funciona a sua fonte de renda hoje?" → o que ele já vende ('' = respondeu e não tem produto: CLT ou sem renda)
  function produtoDe(renda) {
    var t = nz(renda); if (!t) return null;
    var p = [];
    if (/digital/.test(t)) p.push('produto digital');
    if (/evento|mentoria|consultoria/.test(t)) p.push('eventos/mentoria/consultoria');
    if (/fisico/.test(t)) p.push('produto/serviço físico');
    return p.join(' · ');
  }
  // os objetivos que ele marcou (até 2, nas palavras do formulário)
  function dorDe(obj) {
    var p = String(obj || '').split(/\s*,\s*/).map(function (x) { return x.trim(); }).filter(Boolean);
    return p.slice(0, 2).join(' · ').slice(0, 140);
  }
  function investDe(t) { return String(t || '').replace(/\s+/g, ' ').trim().slice(0, 80); }
  // perfil pela bio do Instagram: só quando UMA profissão aparece (pastora e psicóloga ao mesmo tempo = não sugere)
  var PERFIS_BIO = [
    ['pastor', /\b(pastor|pastora|bispo|bispa|apostolo|apostola|missionario|missionaria|evangelista|pregador|pregadora|reverendo)\b/],
    ['medico', /\b(medico|medica|medicina)\b/],
    ['psicologo', /\b(psicologo|psicologa|crp)\b/],
    ['terapeuta', /\b(terapeuta|psicanalista|hipnoterapeuta|constelador|consteladora)\b/],
    ['mentor', /\b(mentor|mentora|mentoria)\b/],
    ['empresario', /\b(empresario|empresaria|ceo|empreendedor|empreendedora)\b/],
    ['comunicador', /\b(comunicador|comunicadora|palestrante|jornalista|apresentador|apresentadora|radialista)\b/],
    ['especialista', /\b(advogado|advogada|nutricionista|fisioterapeuta|dentista|fonoaudiologo|fonoaudiologa|personal trainer)\b/]
  ];
  function perfilDaBio(bio) {
    var b = nz(bio); if (!b) return '';
    var achou = PERFIS_BIO.filter(function (x) { return x[1].test(b); });
    return achou.length === 1 ? achou[0][0] : '';
  }
  // a observação da reunião sem as marcas do sistema e sem dados pessoais
  function notaDe(obs) {
    var partes = String(obs || '').replace(/##[A-Z]+(?::[^#]*)?##?/g, ' ').split(/\s*\|\s*|\n+/);
    var fica = partes.filter(function (p) {
      p = p.trim(); if (!p) return false;
      var k = nz(p);
      if (/^(e ?mail|instagram|clint|anuncio)\s*:/.test(k)) return false;
      if (/no show em|remarcad|remarcacao|horario extra aprovado|marcado em cima de outra reuniao|venda sem reuniao|linha duplicada|toque organico/.test(k)) return false;
      if (/^[\[{"]/.test(p)) return false;   // pedaço técnico
      return true;
    });
    return fica.join(' · ')
      .replace(/\b(cpf|rg|cnpj|tel|telefone|fone|cel|celular|whats|whatsapp|zap)\b\s*[:.]?\s*(?=[\d(+])/gi, ' ')   // o rótulo de um número
      .replace(/[\w.+-]+@[\w-]+\.[\w.]+/g, ' ')                                   // e-mail
      .replace(/https?:\/\/\S+|www\.\S+|\b[\w-]+\.(com|br|digital|me)(\/\S*)?/gi, ' ')   // link
      .replace(/@[A-Za-z0-9._]{2,}/g, ' ')                                        // @ do Instagram
      .replace(/\d{3}\.?\d{3}\.?\d{3}-?\d{2}/g, ' ')                              // CPF
      .replace(/(\+?55\s*)?\(?\d{2}\)?\s*9?\s?\d{4}[-\s.]?\d{4}/g, ' ')           // telefone
      .replace(/\d{8,}/g, ' ')
      .replace(/\s{2,}/g, ' ').replace(/(\s*·\s*){2,}/g, ' · ').replace(/^[\s·:;,.-]+|[\s·:;,-]+$/g, '')
      .slice(0, 280);
  }
  // a objeção pelas palavras da nota (na ordem: o que mais trava antes; o preço por último)
  var OBJECOES = [
    ['cônjuge/sócio', /\b(marido|esposa|esposo|conjuge|socio|socia|namorado|namorada|noivo|noiva|aval|decisor)\b/],
    ['já tentou e não deu', /\bja (investiu|tentou)\b|\bja comprou outr|nao teve resultado|frustr|\bja foi enganad|outra mentoria/],
    ['tempo', /\b(sem|nao tem|nao tinha|nao tenho|falta de) tempo\b|\btempo (nenhum|para se dedicar|pra se dedicar)\b|\bcorreria\b|\bagenda (cheia|lotada)\b/],
    ['vergonha/não sabe gravar', /vergonha|\btimid|nao sabe gravar|nao gosta de (aparecer|gravar)|medo de (aparecer|gravar|camera)/],
    ['poucos seguidores', /poucos seguidores|sem seguidores|perfil (pequeno|novo)|\bdo zero\b/],
    ['nicho', /\bnicho\b|nao (conseguiu|consegue) se ver|nao se viu/],
    ['preço', /\bpreco\b|\bcaro\b|\bnao (tem|tinha|tenho|teve) (investimento|dinheiro|condicoes|condicao|cartao|como pagar)\b|\bsem (investimento|dinheiro|condicoes|cartao|limite)\b|\bnao (consegue|conseguiu|pode) (investir|pagar)\b|\binvestir alto\b|\borcamento\b/]
  ];
  function objecaoDe(nota) {
    var t = nz(nota); if (!t) return '';
    for (var i = 0; i < OBJECOES.length; i++) if (OBJECOES[i][1].test(t)) return OBJECOES[i][0];
    return '';
  }
  function igDe(r, l) {
    var c = [];
    try { c.push(crInstaDe(r)); } catch (e) {}
    if (l && l.insta) c.push(l.insta);
    try { var cl = CLINT[ldTel8(r.telefone || '')]; if (cl && cl.instaClint) c.push(cl.instaClint); } catch (e) {}
    for (var i = 0; i < c.length; i++) {
      var u = ''; try { u = gvInstaLimpo(c[i]); } catch (e) { u = String(c[i] || '').replace(/^@/, '').trim(); }
      if (u) return u.toLowerCase();
    }
    return '';
  }

  // a reunião (linha da planilha de vendas) → os campos da apresentação
  function apsCamposDe(r) {
    r = r || {};
    var f = {}, o = {};
    function poe(k, v, de) { if (v === null || v === undefined || (typeof v === 'number' && !isFinite(v))) return; f[k] = v; o[k] = de; }
    var t8 = ''; try { t8 = ldTel8(r.telefone || ''); } catch (e) {}
    var pag = null, l = null;
    try { pag = (PAG.rows || []).filter(function (x) { var t = ldTel8(x.celular); return (t && t === t8) || (r.nome && nz(x.nome) === nz(r.nome)); })[0] || null; } catch (e) {}
    try { var a = acharLeadDeTodoJeito(r, pag); l = a ? a.lead : null; } catch (e) {}
    // qualificação: o nome e o programa da reunião marcada
    var nm = primeiroNome(r.nome);
    if (nm) poe('leadNome', nm, 'qualificacao'); else { nm = primeiroNome(l && l.nome); if (nm) poe('leadNome', nm, 'formulario'); }
    var pg = programaDe(r.produto); if (pg) poe('programa', pg, 'qualificacao');
    // formulário do diagnóstico
    if (l) {
      var pd = produtoDe(l.renda); if (pd !== null) poe('produto', pd, 'formulario');
      var dr = dorDe(l.obj); if (dr) poe('dor', dr, 'formulario');
      var iv = investDe(l.invest); if (iv) poe('investimento', iv, 'formulario');
      var sn = numeroSeg(l.seg);
      if (sn !== null) poe('seguidores', sn, 'formulario');
      else if (String(l.seg || '').trim()) poe('seguidoresFaixa', String(l.seg).trim().slice(0, 40), 'formulario');
    }
    if (!f.investimento) { try { var w = wsDoTel(r.telefone); if (w && w.inv) poe('investimento', investDe(w.inv), 'formulario'); } catch (e) {} }   // aplicação do workshop
    // Instagram (aba IG Perfis): seguidores exatos e o perfil pela bio
    var u = igDe(r, l), pf = null, seg = null;
    try { pf = u && IGO.perfil ? IGO.perfil[u] : null; } catch (e) {}
    if (pf && typeof pf.seg === 'number' && isFinite(pf.seg)) seg = pf.seg;
    else { try { var s2 = u && IGO.seg ? parseInt(IGO.seg[u], 10) : NaN; if (isFinite(s2)) seg = s2; } catch (e) {} }
    if (seg !== null) { poe('seguidores', seg, ORIGEM_IG); delete f.seguidoresFaixa; delete o.seguidoresFaixa; }
    if (PERFIL_PELA_BIO && pf && pf.bio) { var pp = perfilDaBio(pf.bio); if (pp) poe('perfil', pp, ORIGEM_IG); }
    // o que a pré-venda (e o closer, em reunião anterior) anotou
    var nota = notaDe(r.obs);
    if (nota) { poe('notaPreVenda', nota, 'qualificacao'); var ob = objecaoDe(nota); if (ob) poe('objecao', ob, 'qualificacao'); }
    return { ts: Date.now(), f: f, origem: o };
  }

  function abrir(pacote) {
    if (!pode()) { aviso('A apresentação é só para administradores e closers.'); return; }
    var url = location.protocol === 'file:' ? URL_SITE : new URL(URL_APS, location.href).href;
    var txt = JSON.stringify(pacote);
    var quem = (pacote.f && pacote.f.leadNome) || 'este lead';
    var emQuadro = false; try { emQuadro = window.top !== window.self; } catch (e) { emQuadro = true; }
    if (!emQuadro) {
      var ok = true; try { localStorage.setItem('spark-campos', txt); } catch (e) { ok = false; }
      var w = window.open(url, '_blank');
      if (!w) { aviso('⚠️ O navegador bloqueou a aba nova: permita pop-ups deste site e toque de novo.'); return; }
      try { w.opener = null; } catch (e) {}
      aviso(ok ? '🎤 Apresentação aberta com o diagnóstico de ' + quem : '⚠️ Este navegador não deixou guardar os dados: a apresentação abriu vazia.');
      return;
    }
    // dentro da Clint: a aba nova abre o versao.txt (arquivo pequeno do próprio site), recebe os dados no armazenamento
    // DELA e só então vai para a apresentação (o armazenamento deste quadro é separado e a apresentação não o enxerga)
    var w2 = window.open(new URL('versao.txt?aps=' + Date.now(), location.href).href, '_blank');
    if (!w2) { aviso('⚠️ O navegador bloqueou a aba nova: permita pop-ups deste site e toque de novo.'); return; }
    var t0 = Date.now(), iv = setInterval(function () {
      var pronto = false;
      try { pronto = /versao\.txt/.test(w2.location.href) && w2.document.readyState === 'complete'; } catch (e) {}
      if (pronto) {
        clearInterval(iv);
        try { w2.localStorage.setItem('spark-campos', txt); w2.location.replace(url); aviso('🎤 Apresentação aberta com o diagnóstico de ' + quem); }
        catch (e) { try { w2.location.replace(url); } catch (e2) {} aviso('⚠️ Dentro da Clint não consegui levar os dados: abra o dash numa aba normal (↗ aba) e toque de novo.'); }
      } else if (Date.now() - t0 > 15000 || w2.closed) {
        clearInterval(iv);
        try { if (!w2.closed) w2.location.replace(url); } catch (e) {}
        aviso('⚠️ Dentro da Clint não consegui levar os dados: abra o dash numa aba normal (↗ aba) e toque de novo.');
      }
    }, 120);
  }

  window.apsPode = pode;
  window.apsCamposDe = apsCamposDe;
  window.apsAbrirLead = function () {   // botão da ficha da reunião
    var r = null; try { r = _v2reg[_fichaAtual]; } catch (e) {}
    if (!r) { aviso('Abra a ficha de uma reunião primeiro.'); return; }
    abrir(apsCamposDe(r));
  };
  window.apsAbrirDoEvento = function () {   // menu do evento na Agenda
    var ev = null; try { ev = _evAtual; } catch (e) {}
    if (!ev) return;
    var r = null; try { r = leadDoEvento(ev); } catch (e) {}
    if (!r) {   // o evento ainda não achou a linha da planilha: vai o que o próprio evento sabe
      var nm = ''; try { nm = agNomeDoEvento(ev.title); } catch (e) {}
      r = { nome: nm, telefone: ev.tel8 || '', produto: /entrevista wld/i.test(String(ev.title || '')) ? 'Entrevista WLD' : '',
            obs: ev.instagram ? 'Instagram: ' + ev.instagram : '' };
    }
    abrir(apsCamposDe(r));
  };
  function apsLeadBotao() { var b = document.getElementById('fl-apres'); if (b) b.style.display = pode() ? 'block' : 'none'; }
  window.apsLeadBotao = apsLeadBotao;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', apsLeadBotao); else apsLeadBotao();
  setTimeout(apsLeadBotao, 1500);
  window.addEventListener('storage', function (e) { if (!e || e.key === 'v2Login') apsLeadBotao(); });
})();
</script>
''' + JS_FIM + '\n'

RX_VERSAO = re.compile(r"var VERSAO_DASH = '([^']*)';")
COPIAS = os.path.expanduser('~/promov-apresentacao/copias-dash')

def parar(m):
    sys.stderr.write('PAREI (remendo do botão do lead): ' + m + ' Nada foi mudado.\n'); sys.exit(3)

def trocar_bloco(t, ini, fim, novo):
    a, b = t.find(ini), t.find(fim)
    if a < 0 and b < 0: return None
    if a < 0 or b < 0 or b < a or t.count(ini) != 1 or t.count(fim) != 1: parar('marcadores do remendo estão quebrados (%s).' % ini.strip())
    e = b + len(fim)
    if t[e:e + 1] == '\n': e += 1
    return t[:a] + novo + t[e:]

def inserir_depois(t, ancora, novo, nome):
    if t.count(ancora) != 1: parar('a âncora "%s" não aparece exatamente uma vez no index.html.' % nome)
    p = t.find(ancora) + len(ancora); return t[:p] + novo + t[p:]

def remendar(t):
    r = trocar_bloco(t, BOT_INI, BOT_FIM, BOT)
    t = r if r is not None else inserir_depois(t, ANCORA_BOT, BOT, 'fl-sub (cabeçalho da ficha da reunião)')
    r = trocar_bloco(t, AG_INI, AG_FIM, AG)
    t = r if r is not None else inserir_depois(t, ANCORA_AG, AG, '📇 Ver ficha do lead (menu do evento da Agenda)')
    r = trocar_bloco(t, JS_INI, JS_FIM, JS)
    if r is None:
        p = t.rfind('</body>')
        if p < 0 or t.rfind('</html>') < p: parar('não achei o </body> do fim da página.')
        r = t[:p] + JS + t[p:]
    return r

def tirar(t):
    for ini, fim in ((BOT_INI, BOT_FIM), (AG_INI, AG_FIM), (JS_INI, JS_FIM)):
        r = trocar_bloco(t, ini, fim, '')
        if r is not None: t = r
    return t

def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith('--'): print(__doc__); sys.exit(1)
    arq = sys.argv[1]; so_conferir = '--conferir' in sys.argv; tira = '--tirar' in sys.argv
    with open(arq, encoding='utf-8') as f: antes = f.read()
    if len(RX_VERSAO.findall(antes)) != 1: parar('não achei a versão do dash (VERSAO_DASH) uma vez só.')
    depois = tirar(antes) if tira else remendar(antes)
    o_que = 'tirar o botão "🎤 Abrir a apresentação deste lead"' if tira else 'o botão "🎤 Abrir a apresentação deste lead" (ficha da reunião + menu da Agenda)'
    if depois == antes:
        print('remendo do botão do lead: %s (nada mudou; versão %s)' % ('não estava aplicado' if tira else 'já estava aplicado', RX_VERSAO.search(antes).group(1))); return
    if not tira:
        if remendar(depois) != depois: parar('o remendo não ficou estável (aplicado de novo mudaria).')
        for x in (BOT_INI, AG_INI, JS_INI, 'id="fl-apres"', 'window.apsAbrirLead'):
            if depois.count(x) != 1: parar('o remendo ficou duplicado (%s).' % x)
    elif tirar(depois) != depois or any(x in depois for x in (BOT_INI, AG_INI, JS_INI)):
        parar('não consegui tirar tudo.')
    v = datetime.datetime.now().strftime('%Y-%m-%d-%H%M')
    if v == RX_VERSAO.search(antes).group(1): v += 'a'
    depois = RX_VERSAO.sub("var VERSAO_DASH = '%s';" % v, depois, count=1)
    mudou = len(depois) - len(antes)
    if so_conferir:
        print('remendo do botão do lead: aplicaria %s (%+d caracteres) e subiria a versão para %s' % (o_que, mudou, v)); return
    os.makedirs(COPIAS, exist_ok=True)
    copia = os.path.join(COPIAS, 'index-antes-lead-%s.html' % datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    shutil.copy2(arq, copia)
    tmp = arq + '.tmp-lead'
    with open(tmp, 'w', encoding='utf-8') as f: f.write(depois)
    os.replace(tmp, arq)
    with open(os.path.join(os.path.dirname(os.path.abspath(arq)), 'versao.txt'), 'w') as f: f.write(v)
    print('remendo do botão do lead: %s · versão %s · cópia do antes: %s' % (o_que, v, copia))

if __name__ == '__main__':
    main()
