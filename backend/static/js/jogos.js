import {requisicaoAeri} from './api.js';
import {escaparHtml} from './util.js';

const INTERVALO_PRESENCA = 10_000;
const INTERVALO_PARTIDA = 1_500;
const PALAVRAS = ['FOLIO', 'SELAR', 'LIVRO', 'NOTAS', 'FIRMA', 'TERMO', 'RURAL', 'CIVIL'];

let hospedeiroAtual = null;

function estilos() {
    return `<style>
        :host{position:fixed;inset:0;z-index:2147483647;font-family:Outfit,system-ui,sans-serif;color:#f8fafc}
        *{box-sizing:border-box}button,input{font:inherit}.fundo{position:absolute;inset:0;background:rgba(2,6,23,.93);backdrop-filter:blur(15px);display:grid;place-items:center;padding:18px}
        .janela{position:relative;width:min(1100px,100%);height:min(720px,95vh);overflow:hidden;border:1px solid rgba(99,102,241,.35);border-radius:26px;background:linear-gradient(145deg,#0f172a,#172036);box-shadow:0 35px 110px #000a}
        .fechar{position:absolute;z-index:4;top:14px;right:14px;width:36px;height:36px;border:1px solid #ffffff20;border-radius:11px;background:#0f172acc;color:#cbd5e1;font-size:21px;cursor:pointer}
        .acesso{height:100%;display:grid;place-items:center;padding:24px}.acesso-card{width:min(390px,100%);padding:34px;border:1px solid #ffffff16;border-radius:22px;background:#0b1222aa;text-align:center}
        .marca{display:inline-flex;padding:6px 10px;border-radius:999px;background:#34d39918;color:#6ee7b7;font-size:11px;font-weight:800;letter-spacing:.12em}.acesso h2{margin:15px 0 6px;font-size:29px}.suave{color:#94a3b8;font-size:13px}
        .campo{width:100%;margin-top:18px;padding:13px 14px;border:1px solid #334155;border-radius:12px;background:#0f172a;color:#fff;outline:none}.campo:focus{border-color:#6366f1}.primario{border:0;border-radius:11px;background:#5b4bea;color:#fff;padding:12px 16px;font-weight:800;cursor:pointer}.acesso .primario{width:100%;margin-top:11px}.erro{min-height:20px;color:#fca5a5;font-size:12px;margin-top:10px}
        .salao{height:100%;display:grid;grid-template-columns:minmax(0,1fr) 280px}.principal{min-width:0;display:flex;flex-direction:column}.topo{padding:22px 62px 14px 25px;border-bottom:1px solid #ffffff12}.topo h2{margin:4px 0;font-size:27px}.abas{display:flex;gap:8px;margin-top:15px}.aba{border:1px solid #ffffff18;border-radius:10px;background:#ffffff08;color:#cbd5e1;padding:9px 14px;font-weight:700;cursor:pointer}.aba.ativa{background:#5b4bea;border-color:#7669f3;color:#fff}
        .conteudo{flex:1;overflow:auto;padding:24px}.lateral{border-left:1px solid #ffffff12;background:#0a1020aa;padding:22px 16px;overflow:auto}.lateral h3{font-size:14px;margin:0 0 12px}.online,.convites{display:grid;gap:8px;margin-bottom:24px}.pessoa,.convite{padding:11px;border:1px solid #ffffff12;border-radius:12px;background:#ffffff06}.pessoa strong,.convite strong{display:block;font-size:13px}.ponto{display:inline-block;width:8px;height:8px;border-radius:50%;background:#34d399;margin-right:7px;box-shadow:0 0 10px #34d39988}.mini{margin-top:8px;border:1px solid #6366f188;border-radius:8px;background:#4f46e522;color:#c7d2fe;padding:7px 9px;font-size:11px;font-weight:700;cursor:pointer}.vazio{color:#64748b;font-size:12px}.convite-acoes{display:flex;gap:6px}.recusar{border-color:#ef444466;background:#ef444414;color:#fca5a5}.senha-sala{margin-top:7px;width:100%;padding:8px;border:1px solid #334155;border-radius:8px;background:#0f172a;color:#fff}
        .jogo-centro{max-width:680px;margin:0 auto;text-align:center}.jogo-centro h3{font-size:24px;margin:4px 0}.grade-termo{display:grid;gap:6px;width:max-content;margin:22px auto}.linha-termo{display:flex;gap:6px}.letra{width:47px;height:47px;display:grid;place-items:center;border:1px solid #475569;border-radius:8px;font-size:20px;font-weight:900}.letra.certa{background:#15803d}.letra.tem{background:#a16207}.letra.nao{background:#334155}.termo-input{width:180px;text-align:center;text-transform:uppercase;letter-spacing:.2em}.snake-wrap{display:grid;place-items:center;gap:14px}.snake-canvas{width:min(100%,520px);height:auto;border:1px solid #334155;border-radius:14px;background:#070b14}.placar{font-weight:800;color:#6ee7b7}
        .dupla-espera{max-width:560px;margin:30px auto;text-align:center;padding:28px;border:1px solid #ffffff14;border-radius:18px;background:#ffffff05}.form-sala{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:18px 0}.form-sala .campo{margin:0}.tabuleiro{display:grid;grid-template-columns:repeat(3,95px);gap:8px;width:max-content;margin:22px auto}.casa{width:95px;height:95px;border:1px solid #475569;border-radius:15px;background:#0f172acc;color:#fff;font-size:38px;font-weight:900;cursor:pointer}.casa.x{color:#6ee7b7}.casa.o{color:#a5b4fc}.casa:disabled{cursor:default}.jogadores{display:flex;justify-content:center;gap:24px;color:#cbd5e1}.status{min-height:22px;font-weight:800}.oculto{display:none!important}@media(max-width:760px){.salao{grid-template-columns:1fr}.lateral{display:none}.janela{height:96vh}.tabuleiro{grid-template-columns:repeat(3,78px)}.casa{width:78px;height:78px}.form-sala{grid-template-columns:1fr}}
    </style>`;
}

function telaAcesso(raiz) {
    raiz.innerHTML = `${estilos()}<div class="fundo"><section class="janela">
        <button class="fechar" type="button" aria-label="Fechar">&times;</button>
        <div class="acesso"><form class="acesso-card">
            <span class="marca">ACESSO RESERVADO</span><h2>Depois do expediente</h2>
            <p class="suave">Informe o código para continuar.</p>
            <input class="campo codigo" type="password" inputmode="numeric" maxlength="20" autocomplete="off" required aria-label="Código">
            <button class="primario" type="submit">Entrar</button><p class="erro" role="alert"></p>
        </form></div></section></div>`;
}

function montarSalao(raiz, fechar) {
    raiz.innerHTML = `${estilos()}<div class="fundo"><section class="janela">
        <button class="fechar" type="button" aria-label="Fechar">&times;</button>
        <div class="salao"><main class="principal"><header class="topo">
            <span class="marca">DEPOIS DO EXPEDIENTE</span><h2>Sala de descanso</h2>
            <nav class="abas"><button class="aba ativa" data-jogo="termo">Termo</button><button class="aba" data-jogo="snake">Snake</button><button class="aba" data-jogo="dupla">Duelo</button></nav>
        </header><section class="conteudo"></section></main><aside class="lateral">
            <h3><span class="ponto"></span>Quem está por aqui</h3><div class="online"><p class="vazio">Procurando…</p></div>
            <h3>Convites</h3><div class="convites"><p class="vazio">Nenhum convite.</p></div>
        </aside></div></section></div>`;

    const estado = {jogo: 'termo', salaId: '', sala: null, presencaTimer: null, partidaTimer: null, snakeTimer: null, snakeTecla: null};
    const conteudo = raiz.querySelector('.conteudo');

    function pararJogoLocal() {
        if (estado.snakeTimer) clearInterval(estado.snakeTimer);
        if (estado.snakeTecla) window.removeEventListener('keydown', estado.snakeTecla);
        estado.snakeTimer = null;
        estado.snakeTecla = null;
    }

    function selecionar(jogo) {
        pararJogoLocal();
        estado.jogo = jogo;
        raiz.querySelectorAll('.aba').forEach(b => b.classList.toggle('ativa', b.dataset.jogo === jogo));
        if (jogo === 'termo') renderTermo();
        if (jogo === 'snake') renderSnake();
        if (jogo === 'dupla') renderDupla();
    }

    function renderTermo() {
        const palavra = PALAVRAS[Math.floor(Date.now() / 86_400_000) % PALAVRAS.length];
        let tentativas = [];
        conteudo.innerHTML = `<div class="jogo-centro"><h3>Termo do Cartório</h3><p class="suave">Uma palavra de cinco letras. Seis tentativas.</p><div class="grade-termo"></div><form><input class="campo termo-input" maxlength="5" autocomplete="off" required><button class="primario" type="submit">Testar</button></form><p class="status"></p></div>`;
        const grade = conteudo.querySelector('.grade-termo');
        const status = conteudo.querySelector('.status');
        const input = conteudo.querySelector('.termo-input');
        const normalizar = valor => valor.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
        function desenhar() {
            grade.innerHTML = tentativas.map(tentativa => `<div class="linha-termo">${[...tentativa].map((letra, i) => {
                const classe = letra === palavra[i] ? 'certa' : palavra.includes(letra) ? 'tem' : 'nao';
                return `<span class="letra ${classe}">${escaparHtml(letra)}</span>`;
            }).join('')}</div>`).join('');
        }
        conteudo.querySelector('form').addEventListener('submit', evento => {
            evento.preventDefault();
            const tentativa = normalizar(input.value);
            if (!/^[A-Z]{5}$/.test(tentativa) || tentativas.length >= 6) return;
            tentativas.push(tentativa); desenhar(); input.value = '';
            if (tentativa === palavra) { status.textContent = 'Registrado sem exigências!'; input.disabled = true; }
            else if (tentativas.length === 6) { status.textContent = `A palavra era ${palavra}.`; input.disabled = true; }
        });
        input.focus();
    }

    function renderSnake() {
        conteudo.innerHTML = `<div class="jogo-centro snake-wrap"><h3>Snake</h3><p class="suave">Use as setas. O processo fica mais longo a cada ponto.</p><canvas class="snake-canvas" width="520" height="360"></canvas><div class="placar">Pontos: <span>0</span></div><button class="primario iniciar">Iniciar</button></div>`;
        const canvas = conteudo.querySelector('canvas'); const ctx = canvas.getContext('2d');
        const placar = conteudo.querySelector('.placar span');
        let cobra, comida, direcao, proxima, pontos;
        const celula = 20, colunas = 26, linhas = 18;
        function sortear() { let p; do { p={x:Math.floor(Math.random()*colunas),y:Math.floor(Math.random()*linhas)}; } while(cobra.some(c=>c.x===p.x&&c.y===p.y)); return p; }
        function desenhar() { ctx.fillStyle='#070b14';ctx.fillRect(0,0,520,360);ctx.fillStyle='#fb7185';ctx.fillRect(comida.x*celula+3,comida.y*celula+3,14,14);cobra.forEach((c,i)=>{ctx.fillStyle=i?'#34d399':'#a7f3d0';ctx.fillRect(c.x*celula+1,c.y*celula+1,18,18);}); }
        function iniciar() { if(estado.snakeTimer)clearInterval(estado.snakeTimer);cobra=[{x:8,y:9},{x:7,y:9},{x:6,y:9}];direcao={x:1,y:0};proxima=direcao;pontos=0;placar.textContent='0';comida=sortear();desenhar();estado.snakeTimer=setInterval(passo,110); }
        function passo(){direcao=proxima;const h={x:cobra[0].x+direcao.x,y:cobra[0].y+direcao.y};if(h.x<0||h.y<0||h.x>=colunas||h.y>=linhas||cobra.some(c=>c.x===h.x&&c.y===h.y)){clearInterval(estado.snakeTimer);estado.snakeTimer=null;return;}cobra.unshift(h);if(h.x===comida.x&&h.y===comida.y){pontos++;placar.textContent=String(pontos);comida=sortear();}else cobra.pop();desenhar();}
        estado.snakeTecla = evento => { const mapa={ArrowUp:{x:0,y:-1},ArrowDown:{x:0,y:1},ArrowLeft:{x:-1,y:0},ArrowRight:{x:1,y:0}};const d=mapa[evento.key];if(!d)return;if(d.x!==-direcao.x||d.y!==-direcao.y)proxima=d;evento.preventDefault(); };
        window.addEventListener('keydown', estado.snakeTecla); conteudo.querySelector('.iniciar').addEventListener('click', iniciar); iniciar();
    }

    function renderDupla() {
        if (estado.sala) return desenharSala();
        const online = raiz.querySelectorAll('.pessoa').length;
        conteudo.innerHTML = `<div class="dupla-espera"><h3>Duelo da Velha</h3><p class="suave">Crie uma sala protegida e convide alguém que esteja aqui agora.</p><div class="form-sala"><input class="campo nome-sala" maxlength="50" placeholder="Nome da sala"><input class="campo senha-nova-sala" type="password" minlength="4" maxlength="64" placeholder="Senha da sala"></div><p class="status">${online ? 'Escolha alguém na lista ao lado.' : 'Aguardando outro jogador entrar…'}</p></div>`;
    }

    function desenharSala() {
        const sala = estado.sala;
        const aguardando = sala.estado === 'AGUARDANDO';
        const nomeAdversario = sala.simbolo === 'X' ? sala.jogadorO?.nome : sala.jogadorX?.nome;
        let mensagem = sala.estado === 'ABANDONADA' ? 'A sala foi encerrada.'
            : aguardando ? 'Convite enviado. Aguardando a outra pessoa e a senha da sala…'
            : sala.vencedor === 'EMPATE' ? 'Empate: nenhuma exigência.'
            : sala.vencedor ? (sala.vencedor === sala.simbolo ? 'Você venceu!' : `${nomeAdversario || 'Adversário'} venceu.`)
            : sala.vez === sala.simbolo ? 'Sua vez.' : `Vez de ${nomeAdversario || 'adversário'}.`;
        conteudo.innerHTML = `<div class="jogo-centro"><h3>${escaparHtml(sala.nome)}</h3><div class="jogadores"><span>❎ ${escaparHtml(sala.jogadorX.nome)}</span><span>⭕ ${escaparHtml(sala.jogadorO?.nome || 'aguardando…')}</span></div><div class="tabuleiro">${sala.tabuleiro.map((valor,i)=>`<button class="casa ${valor.toLowerCase()}" data-i="${i}" ${valor||aguardando||sala.vencedor||sala.vez!==sala.simbolo?'disabled':''}>${escaparHtml(valor)}</button>`).join('')}</div><p class="status">${escaparHtml(mensagem)}</p>${sala.vencedor?'<button class="primario revanche">Revanche</button>':''}</div>`;
        conteudo.querySelectorAll('.casa').forEach(botao => botao.addEventListener('click', async () => {
            botao.disabled = true;
            try { estado.sala = await requisicaoAeri(`/api/jogos/salas/${estado.salaId}/jogar`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({indice:Number(botao.dataset.i)})}); desenharSala(); }
            catch(erro){ await atualizarSala(); }
        }));
        conteudo.querySelector('.revanche')?.addEventListener('click', async()=>{ estado.sala=await requisicaoAeri(`/api/jogos/salas/${estado.salaId}/reiniciar`,{method:'POST'});desenharSala(); });
    }

    async function atualizarSala() {
        if (!estado.salaId) return;
        try { const nova=await requisicaoAeri(`/api/jogos/salas/${estado.salaId}`,{background:true}); const mudou=!estado.sala||nova.versao!==estado.sala.versao;estado.sala=nova;if(estado.jogo==='dupla'&&mudou)desenharSala(); }
        catch(_erro){ estado.salaId='';estado.sala=null;if(estado.jogo==='dupla')renderDupla(); }
    }

    async function convidar(usuario) {
        const nome = conteudo.querySelector('.nome-sala')?.value.trim();
        const senha = conteudo.querySelector('.senha-nova-sala')?.value;
        const status = conteudo.querySelector('.status');
        if (!nome || !senha || senha.length < 4) { if(status)status.textContent='Informe o nome e uma senha de pelo menos 4 caracteres.'; return; }
        try { const dados=await requisicaoAeri('/api/jogos/salas',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nome,senha,convidado:usuario})});estado.salaId=dados.salaId;await atualizarSala(); }
        catch(erro){ if(status)status.textContent=erro.message; }
    }

    function renderSocial(dados) {
        const online = raiz.querySelector('.online');
        online.innerHTML = dados.online.length ? dados.online.map(p=>`<div class="pessoa"><strong><span class="ponto"></span>${escaparHtml(p.nome)}</strong><button class="mini convidar" data-usuario="${escaparHtml(p.usuario)}">Convidar para duelo</button></div>`).join('') : '<p class="vazio">Só você está aqui agora.</p>';
        online.querySelectorAll('.convidar').forEach(botao=>botao.addEventListener('click',()=>{if(estado.jogo!=='dupla')selecionar('dupla');convidar(botao.dataset.usuario);}));
        const convites = raiz.querySelector('.convites');
        const senhasDigitadas = new Map([...convites.querySelectorAll('.convite')].map(card => [
            card.dataset.id, card.querySelector('input')?.value || '',
        ]));
        convites.innerHTML = dados.convites.length ? dados.convites.map(c=>`<div class="convite" data-id="${c.id}"><strong>${escaparHtml(c.remetenteNome)}</strong><span class="suave">Sala: ${escaparHtml(c.sala)}</span><input class="senha-sala" type="password" placeholder="Senha da sala"><div class="convite-acoes"><button class="mini aceitar">Entrar</button><button class="mini recusar">Recusar</button></div></div>`).join('') : '<p class="vazio">Nenhum convite.</p>';
        convites.querySelectorAll('.convite').forEach(card=>{card.querySelector('input').value=senhasDigitadas.get(card.dataset.id)||'';card.querySelector('.aceitar').addEventListener('click',async()=>{try{estado.sala=await requisicaoAeri(`/api/jogos/convites/${card.dataset.id}/aceitar`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({senha:card.querySelector('input').value})});estado.salaId=estado.sala.id;selecionar('dupla');}catch(erro){card.querySelector('input').value='';card.querySelector('input').placeholder=erro.message;}});card.querySelector('.recusar').addEventListener('click',async()=>{await requisicaoAeri(`/api/jogos/convites/${card.dataset.id}/recusar`,{method:'POST'});await atualizarPresenca();});});
    }

    async function atualizarPresenca() {
        try { const dados=await requisicaoAeri('/api/jogos/presenca',{method:'POST',background:true});if(!estado.salaId&&dados.salaAtual){estado.sala=dados.salaAtual;estado.salaId=estado.sala.id;if(estado.jogo==='dupla')desenharSala();}renderSocial(dados);await atualizarSala(); }
        catch(_erro) { fechar(); }
    }

    raiz.querySelectorAll('.aba').forEach(botao=>botao.addEventListener('click',()=>selecionar(botao.dataset.jogo)));
    raiz.querySelector('.fechar').addEventListener('click', fechar);
    raiz.querySelector('.fundo').addEventListener('click',evento=>{if(evento.target===evento.currentTarget)fechar();});
    estado.presencaTimer=setInterval(atualizarPresenca,INTERVALO_PRESENCA);
    estado.partidaTimer=setInterval(atualizarSala,INTERVALO_PARTIDA);
    hospedeiroAtual._encerrar=()=>{clearInterval(estado.presencaTimer);clearInterval(estado.partidaTimer);pararJogoLocal();};
    selecionar('termo'); atualizarPresenca();
}

export function abrirSalaoJogos() {
    if (hospedeiroAtual) return;
    const hospedeiro=document.createElement('aeri-salao');hospedeiroAtual=hospedeiro;
    const raiz=hospedeiro.attachShadow({mode:'closed'});
    function fechar(){hospedeiro._encerrar?.();requisicaoAeri('/api/jogos/sair',{method:'POST',background:true,keepalive:true}).catch(()=>{});window.removeEventListener('keydown',esc);hospedeiro.remove();hospedeiroAtual=null;}
    function esc(evento){if(evento.key==='Escape')fechar();}
    telaAcesso(raiz);document.body.appendChild(hospedeiro);window.addEventListener('keydown',esc);
    raiz.querySelector('.fechar').addEventListener('click',fechar);
    raiz.querySelector('.fundo').addEventListener('click',evento=>{if(evento.target===evento.currentTarget)fechar();});
    raiz.querySelector('form').addEventListener('submit',async evento=>{evento.preventDefault();const input=raiz.querySelector('.codigo');const erro=raiz.querySelector('.erro');const botao=raiz.querySelector('.primario');botao.disabled=true;erro.textContent='';try{await requisicaoAeri('/api/jogos/entrar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({senha:input.value})});montarSalao(raiz,fechar);}catch(e){input.value='';erro.textContent=e.message;}finally{botao.disabled=false;}});
    raiz.querySelector('.codigo').focus();
}
