import {requisicaoAeri} from './api.js?v=20260902-arquivo-v1';

// Consulta sem guardar dados de partes ou GED. Respostas antigas nunca preenchem.
export function iniciarConsultaProtocoloNota(atualizarPrevia) {
    const protocolo = document.getElementById('gn-protocolo');
    const titulo = document.getElementById('gn-titulo');
    const buscar = document.getElementById('gn-consultar-protocolo');
    const usar = document.getElementById('gn-usar-titulo-tri7');
    const aviso = document.getElementById('gn-protocolo-aviso');
    let permitido = false, identidade = null, sequencia = 0, timer, sugestao = '', preenchido = null, controlador;
    const numero = () => protocolo.value.trim().replace(/\./g, '').replace(/^0+/, '');
    const valido = () => /^(?:[0-9]{1,10}|[0-9]{1,3}(?:\.[0-9]{3}){1,2})$/.test(protocolo.value.trim()) && numero() !== '';
    function invalidar() {
        sequencia++; clearTimeout(timer); controlador?.abort(); controlador = null;
        buscar.disabled = false; usar.hidden = true; sugestao = '';
    }
    function aplicar(valor) {
        titulo.value = valor; preenchido = valor;
        atualizarPrevia();
    }
    async function consultar() {
        if (!permitido) return;
        invalidar();
        if (!valido()) { aviso.textContent = 'Informe um número de protocolo válido.'; return; }
        const atual = sequencia, solicitado = numero();
        controlador = new AbortController();
        const sinal = controlador.signal;
        const limite = setTimeout(() => { if (atual === sequencia) controlador?.abort(); }, 15000);
        buscar.disabled = true; aviso.textContent = 'Consultando o título na Tri7…';
        try {
            const resposta = await requisicaoAeri('/api/gerador-notas/consultar-protocolo', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, signal: sinal,
                body: JSON.stringify({protocolo: protocolo.value.trim()}),
            });
            if (atual !== sequencia || !permitido || numero() !== solicitado) return;
            if (resposta.protocolo !== solicitado || typeof resposta.titulo !== 'string' || resposta.titulo.length > 2000) throw new Error('A consulta não confirmou os dados do protocolo. Nenhum campo foi preenchido.');
            if (!resposta.titulo) { aviso.textContent = 'O protocolo não tem descrição do título na Tri7. Preencha manualmente.'; return; }
            if (!titulo.value.trim() || titulo.value === preenchido) {
                aplicar(resposta.titulo);
                aviso.textContent = 'Título preenchido com a descrição da Tri7. Confira antes de gerar a nota.';
            } else {
                sugestao = resposta.titulo; usar.hidden = false;
                aviso.textContent = `Seu título foi preservado. Na Tri7 consta: ${sugestao}`;
            }
        } catch (erro) {
            if (atual !== sequencia || !permitido) return;
            aviso.textContent = sinal.aborted ? 'A consulta demorou mais que o esperado. Tente novamente ou preencha manualmente.' : (erro.message || 'Consulta indisponível; preencha manualmente.');
        } finally { clearTimeout(limite); if (atual === sequencia) buscar.disabled = false; }
    }
    protocolo.addEventListener('input', () => {
        invalidar(); aviso.textContent = '';
        if (preenchido !== null && titulo.value === preenchido) { titulo.value = ''; atualizarPrevia(); }
        preenchido = null;
        if (permitido && valido()) timer = setTimeout(consultar, 750);
    });
    titulo.addEventListener('input', () => { preenchido = null; });
    buscar.addEventListener('click', consultar);
    usar.addEventListener('click', () => {
        if (!permitido || !sugestao) return;
        aplicar(sugestao); usar.hidden = true; sugestao = '';
        aviso.textContent = 'Descrição da Tri7 aplicada ao título. Confira antes de gerar a nota.';
    });
    return { configurar(acesso, usuario = null) {
        if (!acesso || usuario !== identidade) { invalidar(); aviso.textContent = ''; preenchido = null; }
        identidade = usuario; permitido = Boolean(acesso);
    }};
}
