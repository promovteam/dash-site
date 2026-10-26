#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Remendo do dash (dash-site/index.html): item "🎤 Apresentação do closer" no menu lateral, logo abaixo de
Treinamentos, que abre apresentacao-spark/ (sem senha desde 22/10) numa aba nova. Bruno 22/10/2026: "quero dentro do dash,
com um link" · "põe só o link inicialmente".

- Aparece para administradores (ehAdm) e closers (lista CLOSERS do dash). Os outros acessos não veem o item;
  a senha protege o conteúdo de qualquer forma.
- Por âncora e IDEMPOTENTE: os blocos ficam entre marcadores "apresentacao-spark:…"; rodar de novo só troca o
  que está entre eles (e, se nada mudou, não mexe no arquivo nem na versão).
- Quando muda o arquivo, sobe a versão do dash (VERSAO_DASH + versao.txt), como os outros remendos, para quem
  está com o dash aberto receber o aviso de versão nova.

Uso:  python3 remendo-dash.py CAMINHO/index.html            aplica (e acerta versao.txt ao lado)
      python3 remendo-dash.py CAMINHO/index.html --conferir  só diz o que faria
"""
import datetime, os, re, sys

NAV_INI, NAV_FIM = '<!-- 🎤 apresentacao-spark:menu:inicio -->', '<!-- apresentacao-spark:menu:fim -->'
JS_INI, JS_FIM = '<!-- 🎤 apresentacao-spark:script:inicio -->', '<!-- apresentacao-spark:script:fim -->'

NAV = NAV_INI + '''
  <a class="nav-item" id="nav-apres-spark" href="apresentacao-spark/" target="_blank" rel="noopener" style="display:none;text-decoration:none;" title="Abre a apresentação do closer (Spark) numa aba nova"><span class="nav-icon" aria-hidden="true">🎤</span><span class="nav-label">Apresentação do closer</span></a>
  <a class="nav-item" id="nav-acervo-cases" href="apresentacao-spark/?acervo" target="_blank" rel="noopener" style="display:none;text-decoration:none;" title="Abre o acervo de cases (perfil, prints e depoimentos, com o link para copiar e mandar ao lead) numa aba nova"><span class="nav-icon" aria-hidden="true">📚</span><span class="nav-label">Acervo de cases</span></a>
  ''' + NAV_FIM

JS = JS_INI + '''
<script>
// 🎤 APRESENTAÇÃO DO CLOSER (Bruno 22/10/2026: "quero dentro do dash, com um link" · "põe só o link inicialmente"):
// o item do menu abre apresentacao-spark/ (a apresentação do Spark) numa aba nova.
// Aparece para administradores e closers (lista CLOSERS).
(function () {
  function pode() {
    try {
      if (typeof ehAdm === 'function' && ehAdm()) return true;
      var lg = localStorage.getItem('v2Login'); if (!lg) return false;
      var p = String(lg).toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').split(/\\s+/)[0];
      return typeof CLOSERS !== 'undefined' && CLOSERS.some(function (c) { return c.key === p; });
    } catch (e) { return false; }
  }
  // 📚 ACERVO DE CASES (Bruno 26/10/2026: "coloca à disposição dos SDRs esse acervo de cases" · "só o acervo"):
  // abre a apresentação no modo só acervo (?acervo). Para administradores, closers, SDRs e social selling (RL_FUNCOES).
  function podeAcervo() {
    try {
      if (pode()) return true;
      var lg = localStorage.getItem('v2Login'); if (!lg) return false;
      var p = String(lg).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').split(/\s+/)[0];
      var f = (typeof RL_FUNCOES !== 'undefined' && RL_FUNCOES[p]) || [];
      return f.indexOf('sdr') >= 0 || f.indexOf('ss') >= 0 || f.indexOf('closer') >= 0;
    } catch (e) { return false; }
  }
  function apsMenu() {
    var it = document.getElementById('nav-apres-spark'), ac = document.getElementById('nav-acervo-cases');
    if (it) { if (location.protocol === 'file:') it.href = 'https://promovteam.github.io/dash-site/apresentacao-spark/'; it.style.display = pode() ? '' : 'none'; }
    if (ac) { if (location.protocol === 'file:') ac.href = 'https://promovteam.github.io/dash-site/apresentacao-spark/?acervo'; ac.style.display = podeAcervo() ? '' : 'none'; }
  }
  window.apsMenu = apsMenu;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', apsMenu); else apsMenu();
  setTimeout(apsMenu, 1500);
  window.addEventListener('storage', function (e) { if (!e || e.key === 'v2Login') apsMenu(); });
})();
</script>
''' + JS_FIM + '\n'

ANCORA_NAV = re.compile(r'^[ \t]*<div class="nav-item" data-s="treinos">.*$', re.M)   # depois de Treinamentos
ANCORA_NAV_2 = '<div class="sidebar-foot">'                                              # reserva: antes do rodapé do menu
RX_VERSAO = re.compile(r"var VERSAO_DASH = '([^']*)';")

def parar(m):
    sys.stderr.write('PAREI (remendo do dash): ' + m + ' Nada foi mudado.\n'); sys.exit(3)

def trocar_bloco(t, ini, fim, novo):
    a, b = t.find(ini), t.find(fim)
    if a < 0 and b < 0: return None
    if a < 0 or b < 0 or b < a or t.count(ini) != 1 or t.count(fim) != 1: parar('marcadores do remendo estão quebrados (%s).' % ini)
    return t[:a] + novo + t[b + len(fim):]

def remendar(t):
    # 1) o item do menu
    r = trocar_bloco(t, NAV_INI, NAV_FIM, NAV)
    if r is None:
        ms = list(ANCORA_NAV.finditer(t))
        if len(ms) == 1:
            p = ms[0].end(); r = t[:p] + '\n  ' + NAV + t[p:]
        elif t.count(ANCORA_NAV_2) == 1:
            p = t.find(ANCORA_NAV_2); r = t[:p] + NAV + '\n  ' + t[p:]
        else:
            parar('não achei o lugar do menu (item Treinamentos nem o rodapé do menu).')
    t = r
    # 2) o script (antes do último </body>)
    r = trocar_bloco(t, JS_INI, JS_FIM + '\n', JS)
    if r is None:
        p = t.rfind('</body>')
        if p < 0 or t.rfind('</html>') < p: parar('não achei o </body> do fim da página.')
        r = t[:p] + JS + t[p:]
    return r

def main():
    if len(sys.argv) < 2: print(__doc__); sys.exit(1)
    arq = sys.argv[1]; so_conferir = '--conferir' in sys.argv
    with open(arq, encoding='utf-8') as f: antes = f.read()
    if len(RX_VERSAO.findall(antes)) != 1: parar('não achei a versão do dash (VERSAO_DASH) uma vez só.')
    depois = remendar(antes)
    if depois == antes:
        print('remendo do dash: já estava aplicado (nada mudou; versão %s)' % RX_VERSAO.search(antes).group(1)); return
    # confere de novo: aplicado 2x dá o mesmo
    if remendar(depois) != depois: parar('o remendo não ficou estável (aplicado de novo mudaria).')
    if depois.count('id="nav-apres-spark"') != 1 or depois.count(JS_INI) != 1: parar('o remendo ficou duplicado.')
    v = datetime.datetime.now().strftime('%Y-%m-%d-%H%M')
    if v == RX_VERSAO.search(antes).group(1): v += 'a'
    depois = RX_VERSAO.sub("var VERSAO_DASH = '%s';" % v, depois, count=1)
    if so_conferir:
        print('remendo do dash: aplicaria os itens "🎤 Apresentação do closer" e "📚 Acervo de cases" e subiria a versão para %s' % v); return
    tmp = arq + '.tmp-aps'
    with open(tmp, 'w', encoding='utf-8') as f: f.write(depois)
    os.replace(tmp, arq)
    with open(os.path.join(os.path.dirname(os.path.abspath(arq)), 'versao.txt'), 'w') as f: f.write(v)
    print('remendo do dash: itens "🎤 Apresentação do closer" e "📚 Acervo de cases" no menu · versão %s' % v)

if __name__ == '__main__':
    main()
