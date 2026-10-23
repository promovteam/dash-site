#!/bin/bash
# 🎤 Publica a APRESENTAÇÃO DO CLOSER (Spark) no site do dash (SEM SENHA desde 22/10: Bruno escolheu) e o link "🎤 Apresentação do closer"
# no menu do dash (Bruno 22/10/2026: "quero dentro do dash, com um link" · "põe só o link inicialmente").
#   Endereço: https://promovteam.github.io/dash-site/apresentacao-spark/
#
# Quem roda é o Bruno (Run). O script:
#   1. pede a SENHA do time duas vezes (não aparece enquanto digita; não fica gravada em lugar nenhum);
#   2. gera a página com a senha a partir da apresentação ATUAL (~/promov-apresentacao/spark-trab) — gerar.py;
#   3. mostra o tamanho e a lista do que vai subir e o que muda no dash;
#   4. pergunta "Confirma publicar? (s/n)"; só com "s": copia para dash-site/apresentacao-spark/, põe o link no
#      menu do dash (remendo-dash.py, por âncora, pode rodar quantas vezes quiser) e faz git add / commit / push.
#
# Para TROCAR A SENHA ou levar uma versão nova da apresentação: rodar de novo.
# uso:  bash publicar.sh              publica (pergunta antes)
#       bash publicar.sh --ensaio     faz tudo numa pasta temporária, mostra e para (não mexe no site)
#       bash publicar.sh --desfazer   tira do ar a última publicação da apresentação (git revert)
#       bash publicar.sh --com-senha  volta a pôr a tela de senha (pede a senha 2x)
set -u
# 22/10: o dash-site do ~/Documents fica preso no iCloud (arquivos "dataless"); a apresentação sobe por uma cópia fora dele
S="${SITE:-$HOME/promov-apresentacao/site-publicar}"; [ -d "$S/.git" ] || S="$HOME/Documents/teste/dash-site"
AQUI="$(cd "$(dirname "$0")" && pwd)"
ORIGEM="${ORIGEM:-$HOME/promov-apresentacao/spark-trab}"
URL="https://promovteam.github.io/dash-site/apresentacao-spark/"
MSG_COMMIT="Apresentação do closer (Spark)"
G()  { perl -e 'alarm 120; exec @ARGV' git -C "$S" "$@"; }        # git com limite de tempo (iCloud pode travar)
GL() { perl -e 'alarm 1800; exec @ARGV' git -C "$S" "$@"; }       # o envio leva os vídeos (~340 MB): até 30 min
parar() { echo; echo "PAREI: $1"; echo "Nada foi publicado."; exit 1; }
livre_mb() { df -m "$S" | awk 'NR==2{print $4}'; }

# o iCloud tira do Mac arquivos do dash-site (ficam "dataless") e o git trava ao lê-los: pede para baixar e espera
traz() {
  local n i=0
  n=$(find "$@" -type f -flags +dataless 2>/dev/null | wc -l | tr -d ' ')
  [ "$n" = "0" ] && return 0
  echo "   baixando do iCloud $n arquivo(s) do site (o git precisa deles)…"
  find "$@" -type f -flags +dataless -print0 2>/dev/null | xargs -0 -n 40 brctl download 2>/dev/null
  while [ "$n" != "0" ]; do
    i=$((i+1)); [ $i -gt 180 ] && return 1          # até 15 min
    sleep 5
    n=$(find "$@" -type f -flags +dataless 2>/dev/null | wc -l | tr -d ' ')
    [ $((i % 6)) -eq 0 ] && echo "   … faltam $n"
  done
  return 0
}

[ -d "$S/.git" ] || parar "não achei o repositório do site em $S."
command -v python3 >/dev/null || parar "não achei o python3 neste Mac."
[ -f "$AQUI/gerar.py" ] && [ -f "$AQUI/remendo-dash.py" ] || parar "faltam gerar.py / remendo-dash.py ao lado deste script ($AQUI)."

if [ "${1:-}" = "--desfazer" ]; then
  traz "$S/.git" "$S/index.html" "$S/versao.txt" || parar "o iCloud não devolveu os arquivos do site a tempo."
  H=$(G log -1 --format=%H --grep="^$MSG_COMMIT") || true
  [ -n "$H" ] || parar "não achei publicação da apresentação para desfazer."
  G revert --no-edit "$H" >/dev/null || parar "o git não conseguiu desfazer."
  GL push -q origin main || { echo "ATENÇÃO: desfiz aqui, mas o envio para o GitHub falhou. Rode de novo ou avise o Claude."; exit 2; }
  echo "PRONTO: a última publicação da apresentação foi desfeita (o site atualiza em 1 ou 2 minutos)."; exit 0
fi

ENSAIO=""; COM_SENHA=""
for x in "$@"; do case "$x" in --ensaio) ENSAIO=1;; --com-senha) COM_SENHA=1;; *) parar "não conheço a opção $x";; esac; done
if [ -n "$COM_SENHA" ]; then MODO="com senha"; else MODO="sem senha (abre direto pelo link)"; fi
echo "== Apresentação do closer (Spark) · $MODO =="
echo "   apresentação de origem: $ORIGEM"
[ -f "$ORIGEM/apresentacao-completa.html" ] || parar "não achei $ORIGEM/apresentacao-completa.html."
[ "$(livre_mb)" -gt 1000 ] || parar "o disco do Mac está quase cheio ($(livre_mb) MB livres; precisa de 1 GB). Libere espaço e rode de novo."
TMP=$(mktemp -d "${TMPDIR:-/tmp}/apresentacao-spark.XXXXXX") || parar "não consegui criar a pasta temporária."
trap 'rm -rf "$TMP"' EXIT
if [ -z "$COM_SENHA" ]; then
  echo; echo "1/4 · montando a apresentação (sem senha)…"
  python3 -I "$AQUI/gerar.py" --sem-senha --origem "$ORIGEM" --destino "$TMP/apresentacao-spark" \
    || parar "o gerador não terminou (veja a mensagem acima)."
else
python3 -I "$AQUI/gerar.py" --autoteste >/dev/null || parar "a conferência da criptografia falhou."

# 1) a senha (2x)
echo
read -r -s -p "Digite a SENHA que o time vai usar (não aparece enquanto digita): " SENHA < /dev/tty || parar "não consegui ler a senha: rode este comando no Terminal."; echo
read -r -s -p "Repita a senha: " SENHA2 < /dev/tty || parar "não consegui ler a senha: rode este comando no Terminal."; echo
[ "$SENHA" = "$SENHA2" ] || { unset SENHA SENHA2; parar "as duas senhas não são iguais."; }
unset SENHA2
[ ${#SENHA} -ge 6 ] || { unset SENHA; parar "a senha precisa ter pelo menos 6 caracteres."; }

# 2) gera numa pasta temporária (mesmo disco: os vídeos entram como "clone", sem ocupar espaço a mais)
echo; echo "1/4 · gerando a apresentação com a senha…"
printf '%s' "$SENHA" | python3 -I "$AQUI/gerar.py" --senha-stdin --origem "$ORIGEM" --destino "$TMP/apresentacao-spark" \
  || { unset SENHA; parar "o gerador não terminou (veja a mensagem acima)."; }
unset SENHA
fi

# 3) mostra o que vai subir
echo; echo "2/4 · o que vai para o site ($URL):"
( cd "$TMP/apresentacao-spark" && echo "   index.html (a apresentação, $MODO) · $(du -h index.html | cut -f1 | tr -d ' ')"
  find css fontes img video -type d 2>/dev/null | sort | while read -r d; do
    n=$(find "$d" -maxdepth 1 -type f | wc -l | tr -d ' '); [ "$n" -gt 0 ] && printf "   %-30s %4s arquivo(s)  %s\n" "$d/" "$n" "$(find "$d" -maxdepth 1 -type f -exec stat -f %z {} + | awk '{s+=$1} END{printf "%.1f MB", s/1e6}')"
  done
  echo "   + gerar.py, publicar.sh, remendo-dash.py (os scripts, para publicar de novo)"
  echo "   TOTAL: $(find . -type f -exec stat -f %z {} + | awk '{s+=$1} END{printf "%.0f MB", s/1e6}') · $(find . -type f | wc -l | tr -d ' ') arquivos" )
traz "$S/index.html" "$S/versao.txt" || parar "o iCloud não devolveu o index.html do dash a tempo."
cp "$S/index.html" "$TMP/dash-index.html"
echo "   no dash: $(python3 -I "$AQUI/remendo-dash.py" "$TMP/dash-index.html" --conferir 2>&1 | sed 's/^remendo do dash: //')"

if [ -n "$ENSAIO" ]; then echo; echo "ENSAIO: tudo conferido. Parei antes de mexer no site."; exit 0; fi

# 4) confirmação
echo
read -r -p "Confirma publicar? (s/n) " R < /dev/tty
case "$R" in s|S|sim|Sim|SIM|pode|Pode|PODE) ;; *) echo "Ok, não publiquei nada."; exit 0;; esac

echo; echo "3/4 · preparando o site…"
traz "$S/.git" "$S/index.html" "$S/versao.txt" "$S/apresentacao-spark" || parar "o iCloud não devolveu os arquivos do site a tempo. Tente de novo mais tarde."
G rev-parse --git-dir >/dev/null 2>&1 || parar "o git não conseguiu abrir o repositório do site."
G diff --quiet -- index.html versao.txt || parar "o index.html do dash tem mudanças de outro trabalho que ainda não foram publicadas. Publique ou desfaça essas antes."
G fetch -q origin || parar "não consegui falar com o GitHub (internet?)."
L=$(G rev-parse HEAD); O=$(G rev-parse origin/main)
if [ "$L" != "$O" ]; then
  if G merge-base --is-ancestor "$L" "$O"; then
    G merge -q --ff-only origin/main || parar "não consegui trazer a versão do GitHub."
  elif G merge-base --is-ancestor "$O" "$L" && [ -z "$(G log --format=%s origin/main..HEAD | grep -v "^$MSG_COMMIT")" ]; then
    echo "   (uma publicação anterior da apresentação ficou gravada aqui sem subir: vai junto agora)"
  else
    parar "o site aqui e o do GitHub estão diferentes (alguém publicou por outro lugar). Avise o Claude."
  fi
fi
D="$S/apresentacao-spark"; mkdir -p "$D"
for x in index.html css fontes img video js; do rm -rf "$D/$x"; done
for x in "$TMP/apresentacao-spark/"*; do b=$(basename "$x"); rm -rf "$D/$b"; mv "$x" "$D/" || parar "não consegui copiar $b para o site."; done
if [ ! "$AQUI" -ef "$D" ]; then cp "$AQUI/gerar.py" "$AQUI/remendo-dash.py" "$AQUI/publicar.sh" "$D/" || parar "não consegui copiar os scripts."; fi
python3 -I "$AQUI/remendo-dash.py" "$S/index.html" || parar "o remendo do dash não entrou (o dash não foi mexido)."
V=$(tr -d ' \n' < "$S/versao.txt")

echo; echo "4/4 · gravando e enviando para o GitHub (os vídeos são grandes: pode levar alguns minutos)…"
ADD=(apresentacao-spark/index.html apresentacao-spark/css apresentacao-spark/fontes apresentacao-spark/img apresentacao-spark/video
     apresentacao-spark/gerar.py apresentacao-spark/publicar.sh apresentacao-spark/remendo-dash.py index.html versao.txt)
G add -A -- "${ADD[@]}" || parar "o git não conseguiu juntar os arquivos."
if G diff --cached --quiet; then echo "nada mudou desde a última publicação."; else
  G commit -q -m "$MSG_COMMIT $MODO + link no menu do dash ($(date '+%d/%m/%Y %H:%M') · versão do dash $V)" || parar "o git não conseguiu gravar."
fi
if [ -n "$(G log --format=%h origin/main..HEAD)" ]; then   # envia também o que ficou gravado sem subir numa vez anterior
  if [ -n "${SEM_ENVIO:-}" ]; then echo "TESTE (SEM_ENVIO): gravei, mas não enviei ao GitHub."; exit 0; fi
  echo "   enviando $(G log --format=%h origin/main..HEAD | wc -l | tr -d ' ') registro(s) para o GitHub…"
  GL push -q origin main || { echo "ATENÇÃO: gravei aqui, mas o envio para o GitHub falhou (internet?). Rode de novo: ele continua de onde parou."; exit 2; }
fi
echo "   esperando o site atualizar (até uns 5 minutos)…"
for i in $(seq 1 30); do
  sleep 10
  A=$(curl -sL --max-time 20 "${URL}?x=$i" | grep -cE 'id="aps-dados"|name="aps-publicacao"')
  W=$(curl -sL --max-time 20 "https://promovteam.github.io/dash-site/versao.txt?x=$i" | tr -d ' \n')
  if [ "$A" -ge 1 ] && [ "$W" = "$V" ]; then
    echo; echo "PRONTO: $URL"
    echo "No dash, o item \"🎤 Apresentação do closer\" aparece no menu para administradores e closers (versão $V)."
    echo "Tamanho no site: $(find "$D" -type f -exec stat -f %z {} + | awk '{s+=$1} END{printf "%.0f MB", s/1e6}')"; exit 0
  fi
done
echo "Enviei, mas o site ainda não mostrou a versão nova. Costuma levar mais alguns minutos: abra $URL daqui a pouco."
