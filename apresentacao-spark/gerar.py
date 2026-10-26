#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Apresentação do closer (Spark) com SENHA — gerador da pasta do site.
Feito em 22/10/2026 para o dash da Promov (pedido do Bruno: "quero dentro do dash, com um link").

O que faz:
  1. lê a apresentação (versão de pasta) em  --origem  (padrão: ~/promov-apresentacao/spark-trab);
  2. junta numa página só o HTML + os preços (dados.js) + o motor (js/deck.js);
  3. CRIPTOGRAFA essa página com a senha (PBKDF2-SHA256 600 mil voltas + AES-256-GCM, sal e IV novos a cada vez),
     no mesmo formato que a WebCrypto do navegador abre (estilo staticrypt);
  4. escreve em  --destino  o index.html com a tela de senha + só os arquivos que a página usa
     (css/, fontes/, img/, video/), copiados como "clone" do APFS (não ocupa disco a mais).

A senha chega pela entrada padrão (--senha-stdin) e não é gravada em lugar nenhum.
Sem a senha, o index.html não tem nenhum preço nem texto dos slides.

Uso:
  printf '%s' "$SENHA" | python3 gerar.py --senha-stdin --destino PASTA [--origem PASTA]
  python3 gerar.py --retrato PASTA [--origem PASTA]     # só copia um retrato da apresentação (sem senha)
  python3 gerar.py --autoteste                          # confere a criptografia com os vetores oficiais (NIST)
"""
import argparse, base64, gzip, hashlib, json, os, re, secrets, shutil, subprocess, sys, unicodedata

ITERACOES = 600000            # PBKDF2-SHA256 (o pedido era >= 200 mil)
LIMITE_ARQUIVO = 50 * 1000 * 1000   # nenhum arquivo acima de 50 MB
HTML_NOME = 'apresentacao-completa.html'
CHAVE_LOCAL = 'apsSparkChave'        # localStorage (só com "Lembrar neste computador") — guarda a CHAVE, nunca a senha
CHAVE_SESSAO = 'apsSparkChaveSessao' # sessionStorage (esta aba, a janela do apresentador e as prévias)

# ======================================================================================
# AES-256-GCM em Python puro (o python3 do Mac não traz a biblioteca "cryptography")
# Conferido com os vetores oficiais (FIPS-197 e "GCM spec" casos 13–15) em autoteste().
# ======================================================================================
def _xt(a):
    a <<= 1
    return (a ^ 0x11b) if a & 0x100 else a

def _gerar_sbox():
    sb = [0] * 256
    p = q = 1
    while True:
        p = (p ^ ((p << 1) & 0xff) ^ (0x1b if p & 0x80 else 0)) & 0xff
        q ^= (q << 1) & 0xff; q ^= (q << 2) & 0xff; q ^= (q << 4) & 0xff
        if q & 0x80: q ^= 0x09
        r = lambda x, n: ((x << n) | (x >> (8 - n))) & 0xff
        sb[p] = q ^ r(q, 1) ^ r(q, 2) ^ r(q, 3) ^ r(q, 4) ^ 0x63
        if p == 1: break
    sb[0] = 0x63
    return sb

S = _gerar_sbox()
assert S[0] == 0x63 and S[1] == 0x7c and S[0x53] == 0xed
def _rot(w, n): return ((w >> n) | (w << (32 - n))) & 0xffffffff
TE0 = [((_xt(s) & 0xff) << 24) | (s << 16) | (s << 8) | ((_xt(s) ^ s) & 0xff) for s in S]
TE1 = [_rot(x, 8) for x in TE0]
TE2 = [_rot(x, 16) for x in TE0]
TE3 = [_rot(x, 24) for x in TE0]

def _sub(t): return (S[t >> 24] << 24) | (S[(t >> 16) & 255] << 16) | (S[(t >> 8) & 255] << 8) | S[t & 255]

def _expandir(chave):
    nk = len(chave) // 4; nr = nk + 6
    w = [int.from_bytes(chave[4 * i:4 * i + 4], 'big') for i in range(nk)]
    rc = 1
    for i in range(nk, 4 * (nr + 1)):
        t = w[i - 1]
        if i % nk == 0:
            t = _sub(((t << 8) & 0xffffffff) | (t >> 24)) ^ (rc << 24); rc = _xt(rc)
        elif nk > 6 and i % nk == 4:
            t = _sub(t)
        w.append(w[i - nk] ^ t)
    return w, nr

def _bloco(w, nr, s0, s1, s2, s3):
    s0 ^= w[0]; s1 ^= w[1]; s2 ^= w[2]; s3 ^= w[3]
    k = 4
    for _ in range(1, nr):
        t0 = TE0[s0 >> 24] ^ TE1[(s1 >> 16) & 255] ^ TE2[(s2 >> 8) & 255] ^ TE3[s3 & 255] ^ w[k]
        t1 = TE0[s1 >> 24] ^ TE1[(s2 >> 16) & 255] ^ TE2[(s3 >> 8) & 255] ^ TE3[s0 & 255] ^ w[k + 1]
        t2 = TE0[s2 >> 24] ^ TE1[(s3 >> 16) & 255] ^ TE2[(s0 >> 8) & 255] ^ TE3[s1 & 255] ^ w[k + 2]
        t3 = TE0[s3 >> 24] ^ TE1[(s0 >> 16) & 255] ^ TE2[(s1 >> 8) & 255] ^ TE3[s2 & 255] ^ w[k + 3]
        s0, s1, s2, s3 = t0, t1, t2, t3; k += 4
    o0 = ((S[s0 >> 24] << 24) | (S[(s1 >> 16) & 255] << 16) | (S[(s2 >> 8) & 255] << 8) | S[s3 & 255]) ^ w[k]
    o1 = ((S[s1 >> 24] << 24) | (S[(s2 >> 16) & 255] << 16) | (S[(s3 >> 8) & 255] << 8) | S[s0 & 255]) ^ w[k + 1]
    o2 = ((S[s2 >> 24] << 24) | (S[(s3 >> 16) & 255] << 16) | (S[(s0 >> 8) & 255] << 8) | S[s1 & 255]) ^ w[k + 2]
    o3 = ((S[s3 >> 24] << 24) | (S[(s0 >> 16) & 255] << 16) | (S[(s1 >> 8) & 255] << 8) | S[s2 & 255]) ^ w[k + 3]
    return (o0 << 96) | (o1 << 64) | (o2 << 32) | o3

def aes_bloco(chave, b16):
    w, nr = _expandir(chave)
    x = int.from_bytes(b16, 'big')
    return _bloco(w, nr, x >> 96, (x >> 64) & 0xffffffff, (x >> 32) & 0xffffffff, x & 0xffffffff).to_bytes(16, 'big')

_R = 0xE1 << 120
def _tabela_h(h):
    """tabela para multiplicar por H no GF(2^128) do GCM: 16 posições x 256 valores de byte."""
    def mult(x, y):
        z, v = 0, y
        for i in range(127, -1, -1):
            if (x >> i) & 1: z ^= v
            v = (v >> 1) ^ _R if v & 1 else v >> 1
        return z
    bit = [mult(1 << j, h) for j in range(128)]          # H vezes cada bit isolado
    tab = []
    for pos in range(16):                                  # byte 0 = o mais à esquerda
        base = 8 * (15 - pos)
        linha = [0] * 256
        for b in range(1, 256):
            menor = b & (-b); j = menor.bit_length() - 1
            linha[b] = linha[b ^ menor] ^ bit[base + j]
        tab.append(linha)
    return tab

def _ghash(tab, dados):
    y = 0
    for i in range(0, len(dados), 16):
        x = y ^ int.from_bytes(dados[i:i + 16], 'big')
        y = 0
        for pos in range(16):
            y ^= tab[pos][(x >> (8 * (15 - pos))) & 255]
    return y

def gcm_cifrar(chave, iv, texto, aad=b''):
    """AES-GCM com IV de 96 bits. Devolve cifrado + etiqueta (16 bytes), como a WebCrypto."""
    assert len(chave) in (16, 24, 32) and len(iv) == 12
    w, nr = _expandir(chave)
    h = _bloco(w, nr, 0, 0, 0, 0)
    j0 = int.from_bytes(iv, 'big') << 32 | 1
    pref = j0 >> 32 << 32
    n = (len(texto) + 15) // 16
    fluxo = bytearray()
    for i in range(n):
        c = pref | ((j0 + 1 + i) & 0xffffffff)
        fluxo += _bloco(w, nr, c >> 96, (c >> 64) & 0xffffffff, (c >> 32) & 0xffffffff, c & 0xffffffff).to_bytes(16, 'big')
    L = len(texto)
    cif = (int.from_bytes(texto, 'big') ^ int.from_bytes(bytes(fluxo[:L]), 'big')).to_bytes(L, 'big') if L else b''
    tab = _tabela_h(h)
    pad = lambda b: b + b'\0' * ((16 - len(b) % 16) % 16)
    s = _ghash(tab, pad(aad) + pad(cif) + (len(aad) * 8).to_bytes(8, 'big') + (L * 8).to_bytes(8, 'big'))
    ej0 = _bloco(w, nr, j0 >> 96, (j0 >> 64) & 0xffffffff, (j0 >> 32) & 0xffffffff, j0 & 0xffffffff)
    return cif + (s ^ ej0).to_bytes(16, 'big')

def autoteste():
    hx = bytes.fromhex
    assert aes_bloco(hx('000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f'),
                     hx('00112233445566778899aabbccddeeff')).hex() == '8ea2b7ca516745bfeafc49904b496089'
    k0 = bytes(32)
    assert gcm_cifrar(k0, bytes(12), b'').hex() == '530f8afbc74536b9a963b4f1c4cb738b'            # caso 13
    assert gcm_cifrar(k0, bytes(12), bytes(16)).hex() == 'cea7403d4d606b6e074ec5d3baf39d18d0d1c8a799996bf0265b98b5d48ab919'  # caso 14
    k = hx('feffe9928665731c6d6a8f9467308308feffe9928665731c6d6a8f9467308308')
    p = hx('d9313225f88406e5a55909c5aff5269a86a7a9531534f7da2e4c303d8a318a721c3c0c95956809532fcf0e2449a6b525b16aedf5aa0de657ba637b391aafd255')
    assert gcm_cifrar(k, hx('cafebabefacedbaddecaf888'), p).hex() == (
        '522dc1f099567d07f47f37a32a84427d643a8cdcbfe5c0c97598a2bd2555d1aa8cb08e48590dbb3da7b08b1056828838c5f61e6393ba7a0abcc9f662898015ad'
        'b094dac5d93471bdec1a502270e3cc6c')                                                         # caso 15
    a = hx('feedfacedeadbeeffeedfacedeadbeefabaddad2')
    assert gcm_cifrar(k, hx('cafebabefacedbaddecaf888'), p[:60], a).hex().endswith('76fc6ece0f4e1768cddf8853bb2d551b')  # caso 16
    return True

# ======================================================================================
# A apresentação: o que a página usa
# ======================================================================================
EXT = r'(?:mp4|webm|webp|jpg|jpeg|png|gif|svg|avif|woff2?|ttf|otf|css|js|json|mov|m4v|pdf|vtt|mp3|m4a)'
RX_ARQ = re.compile(r'''(?<![A-Za-z0-9_\-])((?:\./)?(?:img|video|fontes)/[^"'()\s,;<>\\?#]+?\.''' + EXT + r')(?![A-Za-z0-9])')
RX_CSS_LINK = re.compile(r'''<link[^>]+href=["'](css/[^"']+\.css)["']''')
RX_URL_CSS = re.compile(r'''url\(\s*['"]?([^'")]+)['"]?\s*\)''')

def ler(p):
    with open(p, encoding='utf-8') as f: return f.read()

def parar(msg, cod=2):
    sys.stderr.write('PAREI: ' + msg + '\n'); sys.exit(cod)

def levantar(origem):
    """lê a apresentação e devolve (html, dados_js, deck_js, css_lista, refs)"""
    ph = os.path.join(origem, HTML_NOME)
    if not os.path.isfile(ph): parar('não achei %s' % ph)
    html = ler(ph)
    if not html.rstrip().endswith('</html>'): parar('o %s parece incompleto (sem </html> no fim) — talvez esteja sendo gerado agora. Espere um pouco e rode de novo.' % HTML_NOME)
    if not re.search(r'<script\s+src=["\']dados\.js["\']\s*>\s*</script>', html): parar('não achei <script src="dados.js"> no HTML (mudou o formato?)')
    if not re.search(r'<script\s+src=["\']js/deck\.js["\']\s*>\s*</script>', html): parar('não achei <script src="js/deck.js"> no HTML (mudou o formato?)')
    dados = ler(os.path.join(origem, 'dados.js'))
    deck = ler(os.path.join(origem, 'js', 'deck.js'))
    css = sorted(set(RX_CSS_LINK.findall(html)))
    refs = set()
    for txt in (html, dados, deck):
        for r in RX_ARQ.findall(txt): refs.add(os.path.normpath(r))
    for c in css:
        refs.add(os.path.normpath(c))
        for u in RX_URL_CSS.findall(ler(os.path.join(origem, c))):
            if u.startswith(('data:', 'http:', 'https:', '#', '%23')): continue
            refs.add(os.path.normpath(os.path.join(os.path.dirname(c), u.split('#')[0].split('?')[0])))
    faltam = sorted(r for r in refs if not os.path.isfile(os.path.join(origem, r)))
    if faltam: parar('a página cita %d arquivo(s) que não existem: %s' % (len(faltam), ', '.join(faltam[:12])))
    fora = sorted(r for r in refs if r.startswith('..') or os.path.isabs(r))
    if fora: parar('arquivos fora da pasta da apresentação: %s' % ', '.join(fora[:5]))
    grandes = [(os.path.getsize(os.path.join(origem, r)), r) for r in refs if os.path.getsize(os.path.join(origem, r)) > LIMITE_ARQUIVO]
    if grandes: parar('arquivo(s) acima de 50 MB: %s' % ', '.join('%s (%.0f MB)' % (r, s / 1e6) for s, r in grandes))
    return html, dados, deck, css, refs

def clonar(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.lexists(dst): os.remove(dst)
    if subprocess.run(['cp', '-c', src, dst], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0: return
    try: os.link(src, dst); return
    except OSError: pass
    shutil.copy2(src, dst)

def _js_inline(js):
    return js.replace('</script', '<\\/script').replace('<!--', '<\\!--')

SAIR = '''
<!-- apresentação com senha: botão "Sair" (apaga a chave guardada neste computador) -->
<style>#aps-sair{position:fixed;right:58px;bottom:14px;z-index:200;height:34px;padding:0 15px;border-radius:17px;border:1px solid rgba(255,255,255,.4);background:rgba(20,16,18,.55);color:#fff;font:500 14px/1 Outfit,system-ui,sans-serif;letter-spacing:.02em;cursor:pointer;opacity:0;pointer-events:none;transition:opacity .4s}
body.aps-mexeu #aps-sair{opacity:.75;pointer-events:auto}#aps-sair:hover,#aps-sair:focus-visible{opacity:1}</style>
<script>(function(){var m=new URLSearchParams(location.search).get('modo');if(m&&m!=='deck')return;
var b=document.createElement('button');b.id='aps-sair';b.type='button';b.tabIndex=-1;b.textContent='Sair';b.title='Sair: este computador volta a pedir a senha';
b.addEventListener('mousedown',function(e){e.preventDefault();});
b.addEventListener('click',function(e){e.stopPropagation();e.preventDefault();if(!confirm('Sair da apresentação?\\nNeste computador ela vai pedir a senha de novo.'))return;
try{localStorage.removeItem('%(L)s');}catch(x){}try{sessionStorage.removeItem('%(S)s');}catch(x){}location.replace(location.pathname);});
document.body.appendChild(b);var t;document.addEventListener('mousemove',function(){document.body.classList.add('aps-mexeu');clearTimeout(t);t=setTimeout(function(){document.body.classList.remove('aps-mexeu');},2500);},{passive:true});})();</script>
''' % {'L': CHAVE_LOCAL, 'S': CHAVE_SESSAO}

def montar_pagina(html, dados, deck, sair=True):
    p = re.sub(r'<script\s+src=["\']dados\.js["\']\s*>\s*</script>', lambda m: '<script>\n' + _js_inline(dados) + '\n</script>', html, count=1)
    p = re.sub(r'<script\s+src=["\']js/deck\.js["\']\s*>\s*</script>', lambda m: '<script>\n' + _js_inline(deck) + '\n</script>', p, count=1)
    i = p.rfind('</body>')
    if i < 0: parar('o HTML não tem </body>')
    return p[:i] + (SAIR if sair else '') + p[i:]

MARCA_SEM_SENHA = '<meta name="robots" content="noindex,nofollow"><meta name="aps-publicacao" content="sem-senha">'

def gerar_sem_senha(origem, destino, html, dados, deck, refs):
    """Bruno 22/10/2026 escolheu SEM SENHA: a página abre direto pelo link (fora do Google: noindex)"""
    pagina = montar_pagina(html, dados, deck, sair=False)
    m = re.search(r'<head[^>]*>', pagina)
    if not m: parar('o HTML não tem <head>')
    pagina = pagina[:m.end()] + '\n' + MARCA_SEM_SENHA + pagina[m.end():]
    with open(os.path.join(destino, 'index.html'), 'w', encoding='utf-8') as f: f.write(pagina)
    for r in sorted(refs): clonar(os.path.join(origem, r), os.path.join(destino, r))
    pd = os.path.join(origem, 'd')      # 25/10: as páginas dos depoimentos para o WhatsApp (d/<slug>.html + d/img/<slug>.jpg)
    if os.path.isdir(pd):
        for r_, _, fs in os.walk(pd):
            for f_ in fs:
                if not f_.endswith('.html'): continue
                a_ = os.path.join(r_, f_); m_ = re.search(r'src="\.\./(?:apresentacao-spark/)?(video/[^"]+)"', ler(a_))
                if m_ and os.path.normpath(m_.group(1)) not in refs: continue      # o vídeo da página tem de estar publicado (as páginas de case não têm vídeo)
                clonar(a_, os.path.join(destino, os.path.relpath(a_, origem)))
                for suf_ in ('.jpg', '-capa.jpg'):      # a prévia do WhatsApp e a capa da página
                    im_ = os.path.join(pd, 'img', f_[:-5] + suf_)
                    if os.path.exists(im_): clonar(im_, os.path.join(destino, 'd', 'img', f_[:-5] + suf_))
        for sub_ in (('f',), ('img', 'w')):      # 26/10: a fonte das páginas de case (d/f) e os prints com a marca "promov" (d/img/w)
            ps_ = os.path.join(pd, *sub_)
            if os.path.isdir(ps_):
                for f_ in os.listdir(ps_):
                    if f_.endswith(('.woff2', '.webp', '.jpg', '.png')): clonar(os.path.join(ps_, f_), os.path.join(destino, 'd', *sub_, f_))

def logo_svg(origem):
    try:
        d = json.load(open(os.path.join(origem, 'img', 'logo-promov-empilhada.json'), encoding='utf-8'))
        e = d.get('empilhado', {}); vb = e.get('vb') or [0, 0, 308.4, 428.8]
        ny = e.get('nome_y', 385)
        return ('<svg class="aps-logo" viewBox="%s" aria-label="Promov" role="img">'
                '<path fill="#fff" fill-rule="evenodd" d="%s"/>'
                '<path fill="#fff" fill-rule="evenodd" transform="translate(%.1f %s)" d="%s"/></svg>') % (
            ' '.join(str(x) for x in vb), d['marca']['d'], (vb[2] - d['nome']['vb'][2]) / 2, ny, d['nome']['d'])
    except Exception:
        return '<div class="aps-logo-txt">Promov</div>'

PORTA = r'''<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<meta name="referrer" content="no-referrer">
<title>Promov · Apresentação do closer</title>
<style>
@font-face{font-family:Outfit;font-style:normal;font-weight:100 900;font-display:swap;src:url(fontes/outfit-latin.woff2) format("woff2")}
:root{--red:#c8102e;--red2:#e0213f;--bg:#0b090a;--ink:#f5f1ee;--ink2:rgba(245,241,238,.64);--ink3:rgba(245,241,238,.38);--line:rgba(255,255,255,.12)}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{background:var(--bg);color:var(--ink);font:400 16px/1.45 Outfit,system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased;overflow-x:hidden}
body::before{content:"";position:fixed;inset:-20%;background:radial-gradient(42% 38% at 50% 32%,rgba(200,16,46,.30),transparent 70%),radial-gradient(30% 30% at 82% 88%,rgba(200,16,46,.12),transparent 70%);pointer-events:none}
.aps{position:relative;min-height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:40px 16px 28px}
.aps-card{width:100%;max-width:420px;padding:40px 36px 30px;border-radius:24px;background:linear-gradient(180deg,rgba(255,255,255,.065),rgba(255,255,255,.025));border:1px solid var(--line);box-shadow:0 30px 80px rgba(0,0,0,.55),inset 0 1px 0 rgba(255,255,255,.06);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);text-align:center}
.aps-logo{width:74px;height:auto;display:block;margin:0 auto 22px;filter:drop-shadow(0 0 22px rgba(200,16,46,.55))}
.aps-logo-txt{font:600 26px/1 Outfit,sans-serif;margin-bottom:22px}
.aps-tag{display:inline-block;font:600 11px/1 Outfit,sans-serif;letter-spacing:.18em;text-transform:uppercase;color:var(--red2);padding:7px 11px;border:1px solid rgba(200,16,46,.45);border-radius:99px;background:rgba(200,16,46,.10);margin-bottom:16px}
h1{font:600 28px/1.15 Outfit,sans-serif;margin:0 0 8px;letter-spacing:-.01em}
.aps-sub{margin:0 0 28px;color:var(--ink2);font-size:15px}
form{text-align:left}
label.aps-rot{display:block;font-size:13px;font-weight:500;color:var(--ink2);margin:0 0 8px 2px}
.aps-campo{position:relative}
.aps-campo input{width:100%;height:52px;padding:0 52px 0 16px;border-radius:14px;border:1px solid rgba(255,255,255,.18);background:rgba(0,0,0,.35);color:var(--ink);font:500 18px/1 Outfit,sans-serif;letter-spacing:.04em;outline:none;transition:border-color .2s,box-shadow .2s}
.aps-campo input:focus{border-color:var(--red);box-shadow:0 0 0 4px rgba(200,16,46,.25)}
.aps-campo input[aria-invalid="true"]{border-color:#ff5a6e}
.aps-olho{position:absolute;right:6px;top:6px;width:40px;height:40px;border:0;border-radius:10px;background:transparent;color:var(--ink3);cursor:pointer;display:grid;place-items:center}
.aps-olho:hover,.aps-olho:focus-visible{color:var(--ink);background:rgba(255,255,255,.06);outline:none}
.aps-olho svg{width:22px;height:22px}
.aps-lembrar{display:flex;align-items:center;gap:10px;margin:16px 2px 22px;font-size:14px;color:var(--ink2);cursor:pointer;user-select:none}
.aps-lembrar input{width:18px;height:18px;margin:0;accent-color:var(--red);cursor:pointer}
.aps-lembrar small{display:block;color:var(--ink3);font-size:12px}
button.aps-entrar{width:100%;height:52px;border:0;border-radius:14px;background:linear-gradient(180deg,var(--red2),var(--red));color:#fff;font:600 17px/1 Outfit,sans-serif;letter-spacing:.02em;cursor:pointer;box-shadow:0 12px 30px rgba(200,16,46,.35);transition:transform .15s,box-shadow .2s,opacity .2s}
button.aps-entrar:hover{transform:translateY(-1px);box-shadow:0 16px 36px rgba(200,16,46,.45)}
button.aps-entrar:focus-visible{outline:3px solid rgba(255,255,255,.7);outline-offset:3px}
button.aps-entrar[disabled]{opacity:.7;cursor:progress;transform:none}
.aps-msg{min-height:22px;margin:14px 2px 0;font-size:14px;color:#ff8191;text-align:center}
.aps-msg.ok{color:var(--ink2)}
.aps-rodape{margin:22px 0 0;font-size:12.5px;color:var(--ink3);text-align:center;max-width:420px}
.treme{animation:treme .42s}
@keyframes treme{20%{transform:translateX(-8px)}40%{transform:translateX(7px)}60%{transform:translateX(-5px)}80%{transform:translateX(3px)}}
.aps-espera .aps-card,.aps-espera .aps-rodape{visibility:hidden}
.aps-girando{position:fixed;left:50%;top:50%;width:34px;height:34px;margin:-17px 0 0 -17px;border-radius:50%;border:3px solid rgba(255,255,255,.12);border-top-color:var(--red);animation:gira .8s linear infinite;display:none}
.aps-espera .aps-girando{display:block}
@keyframes gira{to{transform:rotate(360deg)}}
@media (max-width:480px){.aps-card{padding:32px 22px 24px;border-radius:20px}h1{font-size:24px}}
@media (prefers-reduced-motion:reduce){.treme,.aps-girando{animation:none}button.aps-entrar{transition:none}}
</style>
</head>
<body class="aps-espera">
<div class="aps-girando" aria-hidden="true"></div>
<main class="aps">
  <div class="aps-card" id="aps-card">
    __LOGO__
    <span class="aps-tag">Spark · uso interno</span>
    <h1>Apresentação do closer</h1>
    <p class="aps-sub">Digite a senha do time comercial para abrir.</p>
    <form id="aps-form" novalidate>
      <label class="aps-rot" for="aps-senha">Senha</label>
      <div class="aps-campo">
        <input id="aps-senha" name="senha" type="password" autocomplete="current-password" autocapitalize="off" autocorrect="off" spellcheck="false" required aria-describedby="aps-msg">
        <button type="button" class="aps-olho" id="aps-olho" aria-label="Mostrar a senha" title="Mostrar a senha"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg></button>
      </div>
      <label class="aps-lembrar"><input type="checkbox" id="aps-lembrar"><span>Lembrar neste computador<small>Só no seu computador. Para tirar, use “Sair” na apresentação.</small></span></label>
      <button type="submit" class="aps-entrar" id="aps-entrar">Entrar</button>
      <p class="aps-msg" id="aps-msg" role="status" aria-live="polite"></p>
    </form>
  </div>
  <p class="aps-rodape">Conteúdo protegido: preços e condições só abrem com a senha.</p>
</main>
<script type="application/octet-stream" id="aps-dados">__DADOS__</script>
<script>
(function () {
  'use strict';
  var CFG = __CFG__;
  var KL = '__KL__', KS = '__KS__';
  var $ = function (i) { return document.getElementById(i); };
  var subtle = window.crypto && window.crypto.subtle;
  function b64d(s) { var b = atob(s), u = new Uint8Array(b.length); for (var i = 0; i < b.length; i++) u[i] = b.charCodeAt(i); return u; }
  function b64e(u) { var s = ''; for (var i = 0; i < u.length; i += 32768) s += String.fromCharCode.apply(null, u.subarray(i, i + 32768)); return btoa(s); }
  function guarda(area, k, v) { try { var st = window[area]; if (v == null) st.removeItem(k); else st.setItem(k, v); } catch (e) {} }
  function lida(area, k) { try { return window[area].getItem(k); } catch (e) { return null; } }
  function msg(t, ok) { var m = $('aps-msg'); m.textContent = t || ''; m.className = 'aps-msg' + (ok ? ' ok' : ''); }
  function mostrarPorta(t) {
    document.body.classList.remove('aps-espera');
    if (t) msg(t);
    try { $('aps-senha').focus(); } catch (e) {}
  }
  if (!subtle || !window.DecompressionStream || !window.TextEncoder) {
    mostrarPorta('Este navegador não abre a apresentação. Use o Google Chrome (ou o Safari) atualizado.');
    $('aps-entrar').disabled = true; return;
  }
  var CIF = null;
  function cifrado() { if (!CIF) CIF = b64d($('aps-dados').textContent.replace(/\s+/g, '')); return CIF; }
  function abrir(chave) {
    return subtle.decrypt({ name: 'AES-GCM', iv: b64d(CFG.iv) }, chave, cifrado()).then(function (gz) {
      var fluxo = new Blob([gz]).stream().pipeThrough(new DecompressionStream('gzip'));
      return new Response(fluxo).text();
    });
  }
  function daSenha(senha) {
    return subtle.importKey('raw', new TextEncoder().encode(senha), 'PBKDF2', false, ['deriveKey']).then(function (base) {
      return subtle.deriveKey({ name: 'PBKDF2', salt: b64d(CFG.sal), iterations: CFG.it, hash: 'SHA-256' }, base, { name: 'AES-GCM', length: 256 }, true, ['decrypt']);
    });
  }
  function daGuardada(b64) { return subtle.importKey('raw', b64d(b64), { name: 'AES-GCM' }, true, ['decrypt']); }
  function escrever(html, b64) {
    window.__apsChave = b64;            // a janela do apresentador e as prévias pegam daqui se precisarem
    var vai = function () { document.open(); document.write(html); document.close(); };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', vai); else vai();
  }
  // 1) já entrou nesta aba, marcou "lembrar" ou veio da apresentação (janela do apresentador / prévia)
  var tentativas = [];
  var s1 = lida('sessionStorage', KS); if (s1) tentativas.push({ b: s1, de: 'sessao' });
  var s2 = lida('localStorage', KL); if (s2 && s2 !== s1) tentativas.push({ b: s2, de: 'local' });
  try { var o = window.opener && window.opener.__apsChave; if (o) tentativas.push({ b: o, de: 'janela' }); } catch (e) {}
  try { var pa = window.parent !== window && window.parent.__apsChave; if (pa) tentativas.push({ b: pa, de: 'janela' }); } catch (e) {}
  var mudou = false;
  (function proxima(i) {
    if (i >= tentativas.length) { mostrarPorta(mudou ? 'A senha da apresentação mudou. Digite a senha nova.' : ''); return; }
    var t = tentativas[i];
    daGuardada(t.b).then(abrir).then(function (html) {
      guarda('sessionStorage', KS, t.b);
      escrever(html, t.b);
    }).catch(function () {
      if (t.de === 'local') { guarda('localStorage', KL, null); mudou = true; }
      if (t.de === 'sessao') guarda('sessionStorage', KS, null);
      proxima(i + 1);
    });
  })(0);
  // 2) a porta: senha
  var olho = $('aps-olho'), campo = $('aps-senha');
  olho.addEventListener('click', function () {
    var ver = campo.type === 'password'; campo.type = ver ? 'text' : 'password';
    olho.setAttribute('aria-label', ver ? 'Esconder a senha' : 'Mostrar a senha'); olho.title = olho.getAttribute('aria-label'); campo.focus();
  });
  campo.addEventListener('input', function () { campo.removeAttribute('aria-invalid'); if ($('aps-msg').textContent) msg(''); });
  $('aps-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var senha = (campo.value || '').normalize('NFC').trim();
    if (!senha) { msg('Digite a senha.'); campo.focus(); return; }
    var bt = $('aps-entrar'); bt.disabled = true; bt.textContent = 'Abrindo…'; msg('');
    var chave;
    daSenha(senha).then(function (k) { chave = k; return abrir(k); }).then(function (html) {
      return subtle.exportKey('raw', chave).then(function (raw) {
        var b64 = b64e(new Uint8Array(raw));
        guarda('sessionStorage', KS, b64);
        guarda('localStorage', KL, $('aps-lembrar').checked ? b64 : null);
        msg('Senha certa. Abrindo a apresentação…', true);
        escrever(html, b64);
      });
    }).catch(function () {
      bt.disabled = false; bt.textContent = 'Entrar';
      campo.setAttribute('aria-invalid', 'true');
      msg('Senha incorreta. Confira e tente de novo.');
      var c = $('aps-card'); c.classList.remove('treme'); void c.offsetWidth; c.classList.add('treme');
      campo.select();
    });
  });
})();
</script>
</body>
</html>
'''

def pagina_porta(cifrado, sal, iv, iteracoes, logo):
    cfg = json.dumps({'v': 1, 'it': iteracoes, 'sal': base64.b64encode(sal).decode(), 'iv': base64.b64encode(iv).decode()})
    b64 = base64.b64encode(cifrado).decode()
    linhas = '\n'.join(b64[i:i + 120] for i in range(0, len(b64), 120))
    return (PORTA.replace('__LOGO__', logo).replace('__CFG__', cfg).replace('__KL__', CHAVE_LOCAL)
            .replace('__KS__', CHAVE_SESSAO).replace('__DADOS__', linhas))

# ======================================================================================
def conferir_sem_segredo(destino, dados_js, html):
    """nenhum preço nem texto dos slides em arquivo de texto da pasta pronta"""
    proibidos = {'R$', '1.997', '3.000', '87.500', '23.964', '1.084', '1.197', '1.597', '1.697', '299,70'}
    proibidos |= set(v for v in re.findall(r'"([^"\n]*\d[^"\n]*)"', dados_js) if 'R$' in v)
    try:
        dj = json.loads(re.search(r'<script type="application/json" id="dados-slides">(.*?)</script>', html, re.S).group(1))
        for s in dj.get('slides', [])[:40]:
            for campo in ('titulo', 'fala'):
                t = (s.get(campo) or '').strip()
                if len(t) >= 12: proibidos.add(t[:40])
    except Exception:
        pass
    achados = []
    for dp, _, fs in os.walk(destino):
        for f in fs:
            if not f.lower().endswith(('.html', '.htm', '.css', '.js', '.json', '.txt', '.md', '.svg')): continue
            p = os.path.join(dp, f)
            if f in ('gerar.py', 'publicar.sh', 'remendo-dash.py', 'LEIA.md'): continue
            t = open(p, encoding='utf-8', errors='replace').read()
            for x in proibidos:
                if x and x in t: achados.append('%s: "%s"' % (os.path.relpath(p, destino), x[:30]))
    if achados: parar('texto que devia estar escondido apareceu na pasta: ' + '; '.join(achados[:8]))
    if os.path.exists(os.path.join(destino, 'dados.js')) or os.path.exists(os.path.join(destino, 'js', 'deck.js')):
        parar('dados.js / js/deck.js não podem ir soltos para o site')

def resumo(destino):
    tot, n, maior = 0, 0, (0, '')
    pastas = {}
    for dp, _, fs in os.walk(destino):
        for f in fs:
            p = os.path.join(dp, f); r = os.path.relpath(p, destino)
            if r in ('gerar.py', 'publicar.sh', 'remendo-dash.py', 'LEIA.md'): continue
            s = os.path.getsize(p); tot += s; n += 1
            if s > maior[0]: maior = (s, r)
            top = r.split(os.sep)[0] if os.sep in r else r
            a = pastas.setdefault(top, [0, 0]); a[0] += 1; a[1] += s
    return {'total': tot, 'arquivos': n, 'maior': maior, 'pastas': pastas}

SITE = ('index.html', 'css', 'fontes', 'img', 'video', 'js')

def main():
    ap = argparse.ArgumentParser(description='Apresentação do closer (Spark) com senha')
    ap.add_argument('--origem', default=os.path.expanduser('~/promov-apresentacao/spark-trab'))
    ap.add_argument('--destino')
    ap.add_argument('--senha-stdin', action='store_true')
    ap.add_argument('--sem-senha', action='store_true', help='abre direto pelo link (sem tela de senha)')
    ap.add_argument('--retrato', metavar='PASTA')
    ap.add_argument('--iteracoes', type=int, default=ITERACOES)
    ap.add_argument('--autoteste', action='store_true')
    a = ap.parse_args()
    autoteste()
    if a.autoteste: print('autoteste ok: AES-256 e GCM batem com os vetores oficiais'); return
    origem = os.path.abspath(os.path.expanduser(a.origem))
    html, dados, deck, css, refs = levantar(origem)

    if a.retrato:
        dst = os.path.abspath(a.retrato)
        for r in sorted(refs | {HTML_NOME, 'dados.js', 'js/deck.js', 'img/logo-promov-empilhada.json'}):
            if os.path.isfile(os.path.join(origem, r)): clonar(os.path.join(origem, r), os.path.join(dst, r))
        print('retrato: %d arquivos em %s' % (len(refs) + 3, dst)); return

    if a.sem_senha:
        if not a.destino: parar('use --destino PASTA', 1)
        destino = os.path.abspath(a.destino)
        os.makedirs(destino, exist_ok=True)
        for x in SITE:
            p = os.path.join(destino, x)
            if os.path.isdir(p): shutil.rmtree(p)
            elif os.path.exists(p): os.remove(p)
        gerar_sem_senha(origem, destino, html, dados, deck, refs)
        r = resumo(destino)
        print('OK: pasta pronta em %s (SEM senha)' % destino)
        print('  %d arquivos · %.0f MB no total · maior: %s (%.1f MB)' % (r['arquivos'], r['total'] / 1e6, r['maior'][1], r['maior'][0] / 1e6))
        return
    if not a.destino or not a.senha_stdin: parar('use --destino PASTA e --senha-stdin (ou --sem-senha)', 1)
    senha = unicodedata.normalize('NFC', sys.stdin.read()).strip()
    if len(senha) < 6: parar('a senha precisa ter pelo menos 6 caracteres', 1)
    if a.iteracoes < 200000: parar('use pelo menos 200 mil voltas no PBKDF2', 1)
    destino = os.path.abspath(a.destino)
    os.makedirs(destino, exist_ok=True)
    for x in SITE:                                   # limpa só o que é do site (os scripts ficam)
        p = os.path.join(destino, x)
        if os.path.isdir(p): shutil.rmtree(p)
        elif os.path.exists(p): os.remove(p)

    pagina = montar_pagina(html, dados, deck)
    sal, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    chave = hashlib.pbkdf2_hmac('sha256', senha.encode('utf-8'), sal, a.iteracoes, 32)
    cif = gcm_cifrar(chave, iv, gzip.compress(pagina.encode('utf-8'), 9, mtime=0))
    del senha, chave
    with open(os.path.join(destino, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(pagina_porta(cif, sal, iv, a.iteracoes, logo_svg(origem)))
    for r in sorted(refs): clonar(os.path.join(origem, r), os.path.join(destino, r))

    conferir_sem_segredo(destino, dados, html)
    r = resumo(destino)
    print('OK: pasta pronta em %s' % destino)
    print('  %d arquivos · %.0f MB no total · maior: %s (%.1f MB)' % (r['arquivos'], r['total'] / 1e6, r['maior'][1], r['maior'][0] / 1e6))
    for k in sorted(r['pastas']):
        n, s = r['pastas'][k]
        print('  %-11s %4d arquivo(s) %8.1f MB' % (k, n, s / 1e6))
    print('  index.html criptografado (AES-256-GCM, PBKDF2-SHA256 %d voltas): sem preço e sem texto dos slides' % a.iteracoes)

if __name__ == '__main__':
    main()
