const SEQUENCIA = ['ArrowUp', 'ArrowDown', 'Digit6', 'Digit7'];
const TEMPO_LIMITE_MS = 1800;

function elementoEmEdicao(alvo) {
    return alvo instanceof HTMLElement && (
        alvo.matches('input, textarea, select') || alvo.isContentEditable
    );
}

function melhorJogada(tabuleiro) {
    const livres = tabuleiro
        .map((valor, indice) => valor ? -1 : indice)
        .filter(indice => indice >= 0);
    const linhas = [
        [0, 1, 2], [3, 4, 5], [6, 7, 8],
        [0, 3, 6], [1, 4, 7], [2, 5, 8],
        [0, 4, 8], [2, 4, 6],
    ];
    const vencedor = estado => {
        for (const [a, b, c] of linhas) {
            if (estado[a] && estado[a] === estado[b] && estado[a] === estado[c]) return estado[a];
        }
        return estado.every(Boolean) ? 'EMPATE' : null;
    };
    const avaliar = (estado, vezDoRobo, profundidade) => {
        const resultado = vencedor(estado);
        if (resultado === 'O') return 10 - profundidade;
        if (resultado === 'X') return profundidade - 10;
        if (resultado === 'EMPATE') return 0;

        const notas = estado
            .map((valor, indice) => valor ? null : indice)
            .filter(indice => indice !== null)
            .map(indice => {
                estado[indice] = vezDoRobo ? 'O' : 'X';
                const nota = avaliar(estado, !vezDoRobo, profundidade + 1);
                estado[indice] = '';
                return nota;
            });
        return vezDoRobo ? Math.max(...notas) : Math.min(...notas);
    };

    let maiorNota = -Infinity;
    let candidatas = [];
    for (const indice of livres) {
        tabuleiro[indice] = 'O';
        const nota = avaliar(tabuleiro, false, 0);
        tabuleiro[indice] = '';
        if (nota > maiorNota) {
            maiorNota = nota;
            candidatas = [indice];
        } else if (nota === maiorNota) {
            candidatas.push(indice);
        }
    }
    return candidatas[Math.floor(Math.random() * candidatas.length)];
}

function abrirTabuleiro() {
    if (document.querySelector('aeri-tabuleiro')) return;

    const hospedeiro = document.createElement('aeri-tabuleiro');
    const raiz = hospedeiro.attachShadow({mode: 'open'});
    raiz.innerHTML = `
        <style>
            :host { position: fixed; inset: 0; z-index: 2147483647; font-family: Outfit, system-ui, sans-serif; }
            .fundo { position: absolute; inset: 0; display: grid; place-items: center; padding: 20px; background: rgba(2, 6, 23, .88); backdrop-filter: blur(12px); }
            .janela { position: relative; width: min(430px, 100%); padding: 30px; overflow: hidden; border: 1px solid rgba(99, 102, 241, .42); border-radius: 24px; background: linear-gradient(145deg, #111827, #172036); box-shadow: 0 30px 90px rgba(0, 0, 0, .55); color: #f8fafc; text-align: center; }
            .janela::before { content: ''; position: absolute; width: 190px; height: 190px; top: -115px; left: -70px; border-radius: 50%; background: #4f46e5; filter: blur(55px); opacity: .35; }
            .fechar { position: absolute; top: 14px; right: 14px; width: 34px; height: 34px; border: 1px solid rgba(148, 163, 184, .2); border-radius: 10px; background: rgba(15, 23, 42, .7); color: #cbd5e1; font-size: 20px; cursor: pointer; }
            .selo { display: inline-flex; padding: 6px 10px; border-radius: 999px; background: rgba(52, 211, 153, .12); color: #6ee7b7; font-size: 11px; font-weight: 800; letter-spacing: .12em; }
            h2 { margin: 14px 0 4px; font-size: 27px; }
            .subtitulo { margin: 0 0 20px; color: #94a3b8; font-size: 14px; }
            .grade { display: grid; grid-template-columns: repeat(3, 1fr); gap: 9px; width: min(310px, 100%); margin: 0 auto; }
            .casa { aspect-ratio: 1; border: 1px solid rgba(148, 163, 184, .2); border-radius: 16px; background: rgba(15, 23, 42, .72); color: #fff; font: 800 38px/1 Outfit, system-ui, sans-serif; cursor: pointer; transition: transform .15s, border-color .15s, background .15s; }
            .casa:not(:disabled):hover { transform: translateY(-2px); border-color: #6366f1; background: rgba(79, 70, 229, .16); }
            .casa:disabled { cursor: default; }
            .casa.x { color: #6ee7b7; text-shadow: 0 0 20px rgba(52, 211, 153, .35); }
            .casa.o { color: #a5b4fc; text-shadow: 0 0 20px rgba(99, 102, 241, .4); }
            .status { min-height: 22px; margin: 18px 0 12px; color: #cbd5e1; font-weight: 700; }
            .novo { padding: 10px 16px; border: 0; border-radius: 10px; background: #4f46e5; color: #fff; font: 700 13px Outfit, system-ui, sans-serif; cursor: pointer; box-shadow: 0 10px 24px rgba(79, 70, 229, .25); }
        </style>
        <div class="fundo" role="dialog" aria-modal="true" aria-label="Jogo da velha">
            <section class="janela">
                <button class="fechar" type="button" aria-label="Fechar">&times;</button>
                <span class="selo">PROTOCOLO SECRETO</span>
                <h2>Jogo da Velha</h2>
                <p class="subtitulo">Você é X. O Robô do Cartório é O.</p>
                <div class="grade" role="grid" aria-label="Tabuleiro"></div>
                <p class="status" aria-live="polite">Sua vez, humano.</p>
                <button class="novo" type="button">Nova partida</button>
            </section>
        </div>`;

    const grade = raiz.querySelector('.grade');
    const status = raiz.querySelector('.status');
    let tabuleiro = Array(9).fill('');
    let encerrado = false;
    let roboPensando = false;
    const linhas = [
        [0, 1, 2], [3, 4, 5], [6, 7, 8],
        [0, 3, 6], [1, 4, 7], [2, 5, 8],
        [0, 4, 8], [2, 4, 6],
    ];

    function resultado() {
        for (const [a, b, c] of linhas) {
            if (tabuleiro[a] && tabuleiro[a] === tabuleiro[b] && tabuleiro[a] === tabuleiro[c]) {
                return tabuleiro[a];
            }
        }
        return tabuleiro.every(Boolean) ? 'EMPATE' : null;
    }

    function anunciar() {
        const atual = resultado();
        if (!atual) return false;
        encerrado = true;
        status.textContent = atual === 'X'
            ? 'Milagre registral: você venceu o robô!'
            : atual === 'O'
                ? 'Exigência formulada: o robô venceu.'
                : 'Sem exigências: deu empate.';
        grade.querySelectorAll('button').forEach(botao => { botao.disabled = true; });
        return true;
    }

    function desenhar() {
        grade.replaceChildren();
        tabuleiro.forEach((valor, indice) => {
            const casa = document.createElement('button');
            casa.type = 'button';
            casa.className = `casa ${valor.toLowerCase()}`;
            casa.textContent = valor;
            casa.disabled = Boolean(valor) || encerrado || roboPensando;
            casa.setAttribute('aria-label', valor ? `Casa ${indice + 1}: ${valor}` : `Casa ${indice + 1}: vazia`);
            casa.addEventListener('click', () => jogar(indice));
            grade.appendChild(casa);
        });
    }

    function jogar(indice) {
        if (encerrado || roboPensando || tabuleiro[indice]) return;
        tabuleiro[indice] = 'X';
        desenhar();
        if (anunciar()) return;

        roboPensando = true;
        status.textContent = 'O robô está conferindo o título…';
        desenhar();
        window.setTimeout(() => {
            const indiceRobo = melhorJogada(tabuleiro);
            if (indiceRobo !== undefined) tabuleiro[indiceRobo] = 'O';
            roboPensando = false;
            desenhar();
            if (!anunciar()) status.textContent = 'Sua vez, humano.';
        }, 420);
    }

    function reiniciar() {
        tabuleiro = Array(9).fill('');
        encerrado = false;
        roboPensando = false;
        status.textContent = 'Sua vez, humano.';
        desenhar();
    }

    function fechar() {
        hospedeiro.remove();
        window.removeEventListener('keydown', fecharComEsc);
    }

    function fecharComEsc(evento) {
        if (evento.key === 'Escape') fechar();
    }

    raiz.querySelector('.fechar').addEventListener('click', fechar);
    raiz.querySelector('.novo').addEventListener('click', reiniciar);
    raiz.querySelector('.fundo').addEventListener('click', evento => {
        if (evento.target === evento.currentTarget) fechar();
    });
    window.addEventListener('keydown', fecharComEsc);
    document.body.appendChild(hospedeiro);
    desenhar();
    raiz.querySelector('.fechar').focus();
}

export function iniciarAtalhosGlobais() {
    let posicao = 0;
    let ultimaTecla = 0;

    window.addEventListener('keydown', evento => {
        if (evento.repeat || evento.ctrlKey || evento.altKey || evento.metaKey || elementoEmEdicao(evento.target)) return;

        const agora = Date.now();
        if (agora - ultimaTecla > TEMPO_LIMITE_MS) posicao = 0;
        ultimaTecla = agora;

        if (evento.code === SEQUENCIA[posicao]) {
            posicao += 1;
            if (posicao === SEQUENCIA.length) {
                posicao = 0;
                abrirTabuleiro();
            }
            return;
        }
        posicao = evento.code === SEQUENCIA[0] ? 1 : 0;
    });
}
