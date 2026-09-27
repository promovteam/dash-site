// 🎬 Player das gravações DENTRO do dash, para qualquer pessoa (Bruno 27/09/2026: "quero que abra independente de estar
// logado", "quero que abra dentro do dash").
// O <video> do dash pede  gv-video/<id do vídeo>?robo=<endereço do robô>  — este arquivo (service worker) atende esse
// pedido: cada trecho de bytes que o player pede vira uma chamada ao robô ("videoPedaco"), que lê o pedaço do Drive com o
// login da equipe@ e devolve em texto. Assim o Google não vê ninguém "sem login" e não corta.
// TODO o resto que o dash pede passa direto, sem mexer.
var PEDACO = 4 * 1024 * 1024;          // 4 MB por chamada ao robô (~20-30 s de vídeo)
var GUARDA = 14;                        // pedaços guardados na memória (~56 MB), para voltar sem pedir de novo
var MEM = new Map(), ORDEM = [];

self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (ev) { ev.waitUntil(self.clients.claim()); });
self.addEventListener('fetch', function (ev) {
  var u;
  try { u = new URL(ev.request.url); } catch (e) { return; }
  if (u.origin !== self.location.origin) return;
  var m = u.pathname.match(/\/gv-video\/([A-Za-z0-9_-]{10,})$/);
  if (!m) return;
  ev.respondWith(servir(m[1], u.searchParams.get('robo') || '', ev.request.headers.get('range') || ''));
});

function pedaco(robo, id, idx) {
  var k = id + ':' + idx;
  if (MEM.has(k)) return MEM.get(k);
  var pedido = { action: 'videoPedaco', id: id, ini: idx * PEDACO, fim: (idx + 1) * PEDACO - 1 };
  var p = fetch(robo + '?payload=' + encodeURIComponent(JSON.stringify(pedido)), { redirect: 'follow', cache: 'no-store' })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (!d || !d.success || typeof d.b64 !== 'string') throw new Error((d && d.error) || 'o robô não entregou o vídeo');
      var bin = atob(d.b64), n = bin.length, arr = new Uint8Array(n);
      for (var i = 0; i < n; i++) arr[i] = bin.charCodeAt(i);
      return { tam: +d.tam || 0, mime: d.mime || 'video/mp4', ini: +d.ini || 0, bytes: arr };
    });
  p.catch(function () { MEM.delete(k); });
  MEM.set(k, p); ORDEM.push(k);
  while (ORDEM.length > GUARDA) MEM.delete(ORDEM.shift());
  return p;
}

function servir(id, robo, range) {
  if (!/^https:\/\/script\.google\.com\/macros\/s\/[A-Za-z0-9_-]+\/exec$/.test(robo)) {
    return Promise.resolve(new Response('endereço do robô inválido', { status: 400 }));
  }
  var mm = /bytes=(\d*)-(\d*)/.exec(range);
  var ini = 0, fimPedido = null, sufixo = 0;
  if (mm) {
    if (mm[1] === '' && mm[2] !== '') sufixo = +mm[2];      // "os últimos N bytes"
    else { ini = +mm[1] || 0; if (mm[2] !== '') fimPedido = +mm[2]; }
  }
  var comeco = sufixo ? pedaco(robo, id, 0).then(function (p0) { ini = Math.max(0, p0.tam - sufixo); return pedaco(robo, id, Math.floor(ini / PEDACO)); })
                      : pedaco(robo, id, Math.floor(ini / PEDACO));
  return comeco.then(function (p) {
    var fimP = p.ini + p.bytes.length - 1;
    var fim = fimPedido !== null ? Math.min(fimPedido, fimP) : fimP;
    if (ini > fim) return new Response('', { status: 416, headers: { 'Content-Range': 'bytes */' + p.tam } });
    var corte = p.bytes.subarray(ini - p.ini, fim - p.ini + 1);
    // lê à frente: os dois pedaços seguintes já vão sendo pedidos, para o vídeo não travar
    var idx = Math.floor(p.ini / PEDACO);
    if ((idx + 1) * PEDACO < p.tam) pedaco(robo, id, idx + 1).catch(function () {});
    if ((idx + 2) * PEDACO < p.tam) pedaco(robo, id, idx + 2).catch(function () {});
    return new Response(corte, { status: 206, headers: {
      'Content-Type': p.mime, 'Content-Length': String(corte.length), 'Accept-Ranges': 'bytes',
      'Content-Range': 'bytes ' + ini + '-' + fim + '/' + p.tam, 'Cache-Control': 'no-store' } });
  }).catch(function (e) {
    return new Response(String((e && e.message) || e), { status: 502, headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
  });
}
