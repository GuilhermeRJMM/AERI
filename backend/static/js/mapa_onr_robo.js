const etapas = [
    ['CONECTANDO AO MAPA', 'Calibrando coordenadas e ignorando atalhos suspeitos do Eduardo.'],
    ['VARRENDO O CARTÓRIO', 'Analisando corredores, balcões e a rota mais curta até a cafeteira.'],
    ['SINAL ENCONTRADO', 'Um padrão de movimentação altamente compatível com o Eduardo foi detectado.'],
];

let temporizador = null;

function concluirVarredura(elementos) {
    window.clearInterval(temporizador);
    temporizador = null;
    elementos.barra.style.width = '100%';
    elementos.status.textContent = 'EDUARDO LOCALIZADO';
    elementos.status.classList.add('localizado');
    elementos.mensagem.textContent = 'Alvo encontrado com sucesso!';
    elementos.detalhe.textContent = 'Eduardo detectado trabalhando intensamente. O robô achou prudente não interromper.';
    elementos.sinal.textContent = 'Excelente';
    elementos.cafe.textContent = '87%';
    elementos.produtividade.textContent = 'Incalculável';
    elementos.botao.disabled = false;
    elementos.botao.querySelector('span').textContent = 'Rodar novamente';
    document.querySelector('.mapa-robo-console')?.classList.remove('varrendo');
    document.querySelector('.mapa-robo-console')?.classList.add('encontrado');
}

function iniciarVarredura(elementos) {
    if (temporizador) return;
    let progresso = 0;
    elementos.botao.disabled = true;
    elementos.status.classList.remove('localizado');
    elementos.status.textContent = etapas[0][0];
    elementos.mensagem.textContent = 'Iniciando protocolo secreto...';
    elementos.detalhe.textContent = etapas[0][1];
    elementos.sinal.textContent = 'Procurando';
    elementos.cafe.textContent = 'Calculando';
    elementos.produtividade.textContent = 'Auditando';
    elementos.barra.style.width = '0%';
    document.querySelector('.mapa-robo-console')?.classList.remove('encontrado');
    document.querySelector('.mapa-robo-console')?.classList.add('varrendo');

    temporizador = window.setInterval(() => {
        progresso = Math.min(100, progresso + 2);
        elementos.barra.style.width = `${progresso}%`;
        const etapa = progresso < 36 ? 0 : progresso < 74 ? 1 : 2;
        elementos.status.textContent = etapas[etapa][0];
        elementos.detalhe.textContent = etapas[etapa][1];
        if (progresso >= 100) concluirVarredura(elementos);
    }, 55);
}

export function iniciarMapaOnrRobo() {
    const botao = document.getElementById('btn-mapa-robo');
    if (!botao) return;
    const elementos = {
        botao,
        status: document.getElementById('mapa-robo-status'),
        mensagem: document.getElementById('mapa-robo-mensagem'),
        detalhe: document.getElementById('mapa-robo-detalhe'),
        barra: document.getElementById('mapa-robo-progresso-barra'),
        sinal: document.getElementById('mapa-robo-sinal'),
        cafe: document.getElementById('mapa-robo-cafe'),
        produtividade: document.getElementById('mapa-robo-produtividade'),
    };
    botao.addEventListener('click', () => iniciarVarredura(elementos));
}
