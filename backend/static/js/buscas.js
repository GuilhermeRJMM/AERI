import {requisicaoAeri} from './api.js?v=20260824-csrf-v1';
import {mostrarPagina} from './navegacao.js?v=20260820-robustez-v1';
import {escaparHtml} from './util.js';

let estadoAtual = null;
let indexando = false;
let revisando = false;
let reprocessandoPendencias = false;
let buscaAtual = {termo:'', pagina:1, totalPaginas:0};

const CABECALHO_PESQUISA = 'Cartório do 1º Ofício de Notas e Registro de Imóveis de Morrinhos-GO';

const UNIDADES = ['zero', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove',
    'dez', 'onze', 'doze', 'treze', 'quatorze', 'quinze', 'dezesseis', 'dezessete', 'dezoito', 'dezenove'];
const DEZENAS = ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa'];
const CENTENAS = ['', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos',
    'seiscentos', 'setecentos', 'oitocentos', 'novecentos'];

// Por extenso até 999: o texto da pesquisa qualificada escreve a quantidade
// de imóveis em algarismo e por extenso -- "3 (três) imóveis".
function porExtenso(numero) {
    const n = Number(numero) || 0;
    if (n < 20) return UNIDADES[n];
    if (n < 100) {
        const dezena = Math.floor(n / 10);
        const resto = n % 10;
        return resto ? `${DEZENAS[dezena]} e ${UNIDADES[resto]}` : DEZENAS[dezena];
    }
    if (n === 100) return 'cem';
    if (n < 1000) {
        const centena = Math.floor(n / 100);
        const resto = n % 100;
        return resto ? `${CENTENAS[centena]} e ${porExtenso(resto)}` : CENTENAS[centena];
    }
    return String(n);
}

// "12.345, 12.346 e 12.347"
function listarComE(itens) {
    if (itens.length === 1) return itens[0];
    return `${itens.slice(0, -1).join(', ')} e ${itens[itens.length - 1]}`;
}

function documentoFormatado(valor) {
    const digitos = String(valor || '').replace(/\D/g, '');
    if (digitos.length === 11) return digitos.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, '$1.$2.$3-$4');
    if (digitos.length === 14) return digitos.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, '$1.$2.$3/$4-$5');
    return String(valor || '').trim();
}

function formatarNumero(valor) {
    return new Intl.NumberFormat('pt-BR').format(Number(valor || 0));
}

function registrarEvento(mensagem, tipo = 'info') {
    const lista = document.getElementById('buscas-log-lista');
    if (!lista) return;
    const item = document.createElement('li');
    item.dataset.tipo = tipo;
    const horario = new Intl.DateTimeFormat('pt-BR', {timeStyle:'medium'}).format(new Date());
    item.textContent = `${horario} - ${mensagem}`;
    lista.prepend(item);
    while (lista.children.length > 12) lista.lastElementChild?.remove();
}

function atualizarStatus(estado) {
    estadoAtual = estado;
    const progresso = Math.min(100, Number(estado.progressoInicial || 0));
    // 'existentes' e não 'total': o total inclui número sondado que
    // não existe, e chamar isso de matrícula analisada inflava a
    // conta em centenas.
    document.getElementById('buscas-total-indexadas').textContent = formatarNumero(estado.matriculasExistentes);
    document.getElementById('buscas-total-sondados').textContent = formatarNumero(estado.numerosSondados);
    document.getElementById('buscas-total-revisar').textContent = formatarNumero(estado.semClassificacao);
    document.getElementById('buscas-total-ativas').textContent = formatarNumero(estado.matriculasAtivas);
    document.getElementById('buscas-total-encerradas').textContent = formatarNumero(estado.matriculasEncerradas);
    document.getElementById('buscas-total-proprietarios').textContent = formatarNumero(estado.proprietariosAtuais);
    document.getElementById('buscas-auditoria-total').textContent = formatarNumero(estado.auditoriaTotal);
    document.getElementById('buscas-auditoria-validadas').textContent = formatarNumero(estado.auditoriaValidadas);
    document.getElementById('buscas-auditoria-revisar').textContent = formatarNumero(estado.auditoriaRevisar);
    document.getElementById('buscas-auditoria-criticas').textContent = formatarNumero(estado.auditoriaCriticas);
    document.getElementById('buscas-progresso-texto').textContent = `${progresso.toLocaleString('pt-BR')}%`;
    document.getElementById('buscas-progresso-barra').style.width = `${progresso}%`;
    document.getElementById('buscas-proximo').textContent = estado.cargaInicialConcluida
        ? `Última matrícula localizada: ${formatarNumero(estado.ultimoConhecido)} · Busca sondou até ${formatarNumero(estado.ultimoSondadoNovos || estado.ultimoConhecido)}`
        : `Próxima matrícula: ${formatarNumero(estado.proximoInicial)} de ${formatarNumero(estado.limiteInicial)}`;
    const documentosPendentes = Number(estado.documentosPendentesReindexacao || 0);
    if (documentosPendentes) {
        document.getElementById('buscas-proximo').textContent += ` · ${formatarNumero(documentosPendentes)} documento(s) aguardando reindexação segura`;
    }
    const motorPendente = Number(estado.motorPendenteReindexacao || 0);
    if (motorPendente) {
        document.getElementById('buscas-proximo').textContent += ` · ${formatarNumero(motorPendente)} matrícula(s) com análise desatualizada`;
    }
    document.getElementById('buscas-limite').value = estado.limiteInicial;
    document.getElementById('buscas-atualizado').textContent = estado.ultimaSincronizacao
        ? `Última atualização: ${new Intl.DateTimeFormat('pt-BR', {dateStyle:'short', timeStyle:'short'}).format(new Date(estado.ultimaSincronizacao))}`
        : 'A indexação ainda não foi iniciada.';
    const admin = ['ADMIN', 'SUBSTITUTO'].includes(document.body.dataset.perfil);
    const podeAuditar = admin || Boolean(window.aeriPermissoes?.revisar_auditoria);
    const erros = Number(estado.errosPendentes || 0);
    document.getElementById('btn-buscas-erros').hidden = !admin || !erros;
    document.getElementById('btn-buscas-reprocessar').hidden = !admin || !erros;
    if (!erros) document.getElementById('buscas-erros-painel').hidden = true;
    const pendencias = Number(estado.auditoriaRevisar || 0);
    document.getElementById('btn-buscas-pendencias').hidden = !podeAuditar || !pendencias;
    document.getElementById('btn-buscas-reprocessar-pendencias').hidden = !podeAuditar || !pendencias;
    if (!pendencias) {
        document.getElementById('buscas-pendencias-painel').hidden = true;
        document.getElementById('btn-buscas-pendencias').textContent = 'Ver pendências';
    }
}

function atualizarBotao() {
    const botao = document.getElementById('btn-buscas-indexar');
    botao.textContent = indexando ? 'Pausar indexação' : 'Iniciar indexação';
    botao.classList.toggle('pausar', indexando);
}

export async function carregarBuscas(opcoes = {}) {
    const autorizado = ['ADMIN', 'SUBSTITUTO'].includes(document.body.dataset.perfil)
        || Boolean(window.aeriPermissoes?.acessar_buscas);
    if (!autorizado) return;
    const admin = ['ADMIN', 'SUBSTITUTO'].includes(document.body.dataset.perfil);
    const podeAuditar = admin || Boolean(window.aeriPermissoes?.revisar_auditoria);
    document.getElementById('buscas-sincronizacao').hidden = !podeAuditar;
    document.querySelectorAll('[data-buscas-admin]').forEach(elemento => { elemento.hidden = !admin; });
    document.querySelectorAll('[data-buscas-revisao]').forEach(elemento => { elemento.hidden = !podeAuditar; });
    try {
        atualizarStatus(await requisicaoAeri(
            '/api/buscas/status',
            {background:Boolean(opcoes.background)},
        ));
    } catch (erro) {
        document.getElementById('buscas-atualizado').textContent = erro.message;
    }
}

export function limparBuscas() {
    indexando = false;
    revisando = false;
    reprocessandoPendencias = false;
    estadoAtual = null;
    buscaAtual = {termo:'', pagina:1, totalPaginas:0};
    atualizarBotao();
    document.getElementById('buscas-pendencias-painel').hidden = true;
    document.getElementById('buscas-paginacao').hidden = true;
    document.getElementById('btn-buscas-pendencias').textContent = 'Ver pendências';
    document.getElementById('buscas-resultados').innerHTML = '<tr><td colspan="8" class="rotina-vazio">Entre novamente para pesquisar.</td></tr>';
}

function atualizarBotaoPendencias() {
    const botao = document.getElementById('btn-buscas-reprocessar-pendencias');
    botao.textContent = reprocessandoPendencias ? 'Pausar reprocessamento' : 'Reprocessar pendências';
    botao.classList.toggle('pausar', reprocessandoPendencias);
}

async function alternarReprocessamentoPendencias() {
    if (reprocessandoPendencias) {
        reprocessandoPendencias = false;
        atualizarBotaoPendencias();
        registrarEvento('Pausa solicitada para a fila de auditoria.');
        return;
    }
    reprocessandoPendencias = true;
    atualizarBotaoPendencias();
    let apos = 0;
    let total = 0;
    let validadas = 0;
    let falhasConsecutivas = 0;
    registrarEvento('Reprocessamento da fila de auditoria iniciado.');
    while (reprocessandoPendencias) {
        try {
            const resultado = await requisicaoAeri('/api/buscas/auditoria/reprocessar', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({apos, tamanho:60}),
            });
            falhasConsecutivas = 0;
            atualizarStatus(resultado.estado);
            total += Number(resultado.processados || 0);
            validadas += Number(resultado.validadas || 0);
            apos = Number(resultado.proximo || apos);
            const mensagem = `${formatarNumero(total)} reprocessadas · ${formatarNumero(validadas)} liberadas da fila · até a matrícula ${formatarNumero(apos)}`;
            document.getElementById('buscas-status-operacao').textContent = mensagem;
            registrarEvento(mensagem, resultado.falhas ? 'erro' : 'sucesso');
            if (resultado.falha) throw new Error(resultado.falha);
            if (resultado.concluido || !resultado.processados) {
                reprocessandoPendencias = false;
                registrarEvento('Fila de auditoria reprocessada por completo.', 'sucesso');
                await carregarBuscas();
                break;
            }
        } catch (erro) {
            falhasConsecutivas += 1;
            registrarEvento(`Falha temporária na auditoria: ${erro.message}`, 'erro');
            if ([401, 403, 409].includes(erro.status) || falhasConsecutivas >= 3) {
                reprocessandoPendencias = false;
                document.getElementById('buscas-status-operacao').textContent = `Reprocessamento interrompido: ${erro.message}`;
                break;
            }
            await new Promise(resolve => setTimeout(resolve, 2500 * falhasConsecutivas));
        }
    }
    atualizarBotaoPendencias();
}

function atualizarBotaoRevisao() {
    const botao = document.getElementById('btn-buscas-revisar-indice');
    botao.textContent = revisando ? 'Pausar revisão' : 'Revisar índice';
    botao.classList.toggle('pausar', revisando);
}

function renderizarResultados(dados) {
    const itens = dados.itens || [];
    const total = Number(dados.total ?? itens.length);
    const pagina = Number(dados.pagina || 1);
    const totalPaginas = Number(dados.totalPaginas || 0);
    const inicio = total ? ((pagina - 1) * Number(dados.porPagina || 50)) + 1 : 0;
    const fim = total ? inicio + itens.length - 1 : 0;
    buscaAtual = {termo:String(dados.termo || buscaAtual.termo), pagina, totalPaginas};
    // O texto da pesquisa qualificada existe nos dois casos: com imóveis
    // (positivo) e sem nenhum (negativo).
    document.getElementById('btn-buscas-texto').hidden = !buscaAtual.termo;
    document.getElementById('buscas-texto-aviso').hidden = true;
    document.getElementById('buscas-total-resultados').textContent = total
        ? `${inicio}–${fim} de ${formatarNumero(total)} resultados`
        : '0 resultados';
    const paginacao = document.getElementById('buscas-paginacao');
    paginacao.hidden = totalPaginas <= 1;
    document.getElementById('buscas-pagina-atual').textContent = `Página ${pagina} de ${totalPaginas || 1}`;
    document.getElementById('btn-buscas-anterior').disabled = pagina <= 1;
    document.getElementById('btn-buscas-proxima').disabled = pagina >= totalPaginas;
    document.getElementById('buscas-resultados').innerHTML = itens.map(item => {
        const correspondencia = item.correspondencia === 'DOCUMENTO_EXATO' ? 'CPF/CNPJ exato'
            : item.correspondencia === 'NOME_EXATO' ? 'Nome exato' : 'Nome parcial';
        const situacao = String(item.situacao || 'REVISAR').toUpperCase();
        return `<tr>
            <td data-label="Matrícula"><strong class="buscas-matricula">${formatarNumero(item.matricula)}</strong><small class="buscas-situacao" data-situacao="${escaparHtml(situacao)}">${escaparHtml(situacao)}</small></td>
            <td data-label="Proprietário"><strong>${escaparHtml(item.nome)}</strong><small>Confiança ${escaparHtml(item.confianca.toLowerCase())}</small></td>
            <td data-label="Documento">${escaparHtml(item.tipoDocumento || '')} ${escaparHtml(item.documento || 'Não informado')}</td>
            <td data-label="Proporção"><span class="buscas-proporcao">${escaparHtml(item.proporcao)}</span></td>
            <td data-label="Origem">${escaparHtml(item.origem)}</td>
            <td data-label="Correspondência"><span class="buscas-correspondencia" data-tipo="${escaparHtml(item.correspondencia)}">${correspondencia}</span></td>
            <td data-label="Atualização">${new Intl.DateTimeFormat('pt-BR').format(new Date(item.consultadoEm))}</td>
            <td data-label="Ação"><button type="button" class="rotina-btn-secondary buscas-analisar" data-matricula="${item.matricula}">Analisar</button></td>
        </tr>`;
    }).join('') || '<tr><td colspan="8" class="rotina-vazio">Nenhuma matrícula foi encontrada para essa pesquisa.</td></tr>';
}

async function executarPesquisa(pagina = 1) {
    const botao = document.getElementById('btn-buscas-pesquisar');
    const termo = buscaAtual.termo || document.getElementById('buscas-termo').value.trim();
    botao.disabled = true;
    document.getElementById('btn-buscas-anterior').disabled = true;
    document.getElementById('btn-buscas-proxima').disabled = true;
    document.getElementById('buscas-resultados').innerHTML = '<tr><td colspan="8" class="rotina-vazio">Pesquisando titulares no índice registral…</td></tr>';
    try {
        renderizarResultados(await requisicaoAeri(`/api/buscas?termo=${encodeURIComponent(termo)}&pagina=${pagina}&limite=50`));
    } catch (erro) {
        document.getElementById('buscas-resultados').innerHTML = `<tr><td colspan="8" class="rotina-vazio">${escaparHtml(erro.message)}</td></tr>`;
    } finally {
        botao.disabled = false;
    }
}

async function pesquisar(evento) {
    evento.preventDefault();
    buscaAtual = {termo:document.getElementById('buscas-termo').value.trim(), pagina:1, totalPaginas:0};
    await executarPesquisa(1);
}

async function coletarTodosOsItens(termo) {
    const dados = await requisicaoAeri(
        `/api/buscas/exportacao?termo=${encodeURIComponent(termo)}`);
    return dados.itens || [];
}

function montarTextoPesquisa(termo, itens) {
    const soDigitos = !/[a-zA-Z]/.test(termo);

    // Só matrícula ATIVA é imóvel em propriedade da pessoa. Encerrada saiu
    // para outra matrícula (desmembramento, remembramento, unificação) e
    // inexistente nunca existiu -- nenhuma das duas pode constar no texto,
    // que é declaração oficial de propriedade. As demais situações
    // (REVISAR, SEM_TEXTO, NAO_ENCONTRADA) são indefinição do índice: ficam
    // de fora e são reportadas para conferência manual.
    const ativos = itens.filter(item => String(item.situacao || '').toUpperCase() === 'ATIVA');
    const descartadas = {};
    for (const item of itens) {
        const situacao = String(item.situacao || 'REVISAR').toUpperCase();
        if (situacao === 'ATIVA') continue;
        descartadas[situacao] = descartadas[situacao] || new Set();
        descartadas[situacao].add(Number(item.matricula));
    }

    // Uma matrícula pode voltar mais de uma vez quando há vários titulares
    // com o nome pesquisado; para o texto interessa o imóvel, não a linha.
    const matriculas = [...new Set(ativos.map(item => Number(item.matricula)))].sort((a, b) => a - b);

    const nome = soDigitos
        ? (itens[0]?.nome || '').trim()
        : termo.trim();
    const documento = soDigitos
        ? documentoFormatado(termo)
        : (itens[0]?.documento || '').trim();

    const solicitados = `Busca por imóveis em nome de ${nome || 'NOME_DA_PESSOA'}, `
        + `inscrito(a) no CPF/CNPJ sob o n.º ${documento || 'xxx.xxx.xxx-xx'}.`;

    const unico = matriculas.length === 1;
    const listadas = matriculas.map(numero => formatarNumero(numero));
    const resultado = matriculas.length
        ? `${unico ? 'Foi encontrado' : 'Foram encontrados'} ${matriculas.length} `
            + `(${porExtenso(matriculas.length)}) ${unico ? 'imóvel' : 'imóveis'} `
            + 'em propriedade da pessoa pesquisada.'
        : 'Não foram encontrados imóveis em propriedade da pessoa pesquisada.';
    const rotuloMatriculas = unico ? 'Matrícula' : 'Matrículas';

    const linhas = [
        CABECALHO_PESQUISA,
        '',
        '1. Dados solicitados:',
        solicitados,
        '2. Resultado:',
        resultado,
    ];
    if (matriculas.length) linhas.push(`2.1 ${rotuloMatriculas}: ${listarComE(listadas)}.`);

    return {
        texto: linhas.join('\n'),
        html: montarHtmlPesquisa({
            solicitados,
            resultado,
            rotuloMatriculas,
            listadas: matriculas.length ? listarComE(listadas) : '',
        }),
        // Buscando por nome só temos o documento mascarado do índice; o texto
        // sai com a máscara e precisa ser completado à mão.
        documentoIncompleto: !soDigitos && documento.includes('*'),
        // Sem resultado e pesquisando por CPF/CNPJ não há de onde tirar o
        // nome: o texto sai com o marcador do modelo para ser preenchido.
        nomeIncompleto: !nome,
        matriculas,
        descartadas: Object.fromEntries(
            Object.entries(descartadas).map(([situacao, numeros]) => [
                situacao,
                [...numeros].sort((a, b) => a - b),
            ]),
        ),
    };
}

// Colar texto puro faz o destino aplicar a própria formatação -- foi assim
// que o texto saiu centralizado no Word. Copiando também como HTML, o
// modelo chega com Arial, alinhado à esquerda e negrito só nos rótulos.
// Arial 12 declarado no <span> de cada trecho, e não só no parágrafo: ao
// colar, o Word costuma herdar a fonte do estilo do destino quando ela não
// vem no nível do texto -- foi assim que o tamanho mudou sozinho.
function montarHtmlPesquisa({solicitados, resultado, rotuloMatriculas, listadas}) {
    const FONTE = 'font-family:Arial,sans-serif;font-size:12.0pt;';
    const P = `margin:0;padding:0;text-align:left;${FONTE}`;

    const trecho = (texto, negrito = false) => {
        const conteudo = escaparHtml(texto);
        return negrito
            ? `<span style="${FONTE}font-weight:bold;"><b>${conteudo}</b></span>`
            : `<span style="${FONTE}">${conteudo}</span>`;
    };
    const vazio = `<p style="${P}">${trecho(' ')}</p>`;

    const partes = [
        `<p style="${P}">${trecho(CABECALHO_PESQUISA, true)}</p>`,
        vazio,
        `<p style="${P}">${trecho('1. Dados solicitados:', true)}</p>`,
        `<p style="${P}">${trecho(solicitados)}</p>`,
        `<p style="${P}">${trecho('2. Resultado:', true)}</p>`,
        `<p style="${P}">${trecho(resultado)}</p>`,
    ];
    if (listadas) {
        partes.push(
            `<p style="${P}">${trecho(`2.1 ${rotuloMatriculas}:`, true)} ${trecho(`${listadas}.`)}</p>`,
        );
    }
    return '<html><head><meta charset="utf-8"></head>'
        + `<body style="${FONTE}">${partes.join('')}</body></html>`;
}

// Copia selecionando um trecho real da página. É o caminho que o Word
// entende melhor, e o único que funciona aqui dentro: o AERI roda em iframe
// no SYNC, e a API assíncrona de clipboard costuma ser bloqueada por
// permissão nesse contexto -- era por isso que só o texto puro chegava.
function copiarSelecionando(html) {
    const area = document.createElement('div');
    area.setAttribute('contenteditable', 'true');
    // Precisa estar renderizado para poder ser selecionado; fica fora da tela.
    area.style.cssText = 'position:fixed;left:-10000px;top:0;opacity:0;white-space:normal;';
    area.innerHTML = html;
    document.body.appendChild(area);
    try {
        const selecao = window.getSelection();
        const intervalo = document.createRange();
        intervalo.selectNodeContents(area);
        selecao.removeAllRanges();
        selecao.addRange(intervalo);
        const copiou = document.execCommand('copy');
        selecao.removeAllRanges();
        return copiou;
    } catch {
        return false;
    } finally {
        area.remove();
    }
}

// Ordem: seleção real (preserva Arial 12 e negrito no Word) -> API rica ->
// texto puro. Devolve se a formatação foi junto.
async function copiarComFormato(texto, html) {
    const corpo = html.replace(/^[\s\S]*<body[^>]*>|<\/body>[\s\S]*$/g, '');
    if (copiarSelecionando(corpo)) return true;

    if (window.ClipboardItem && navigator.clipboard?.write) {
        try {
            await navigator.clipboard.write([new ClipboardItem({
                'text/html': new Blob([html], {type: 'text/html'}),
                'text/plain': new Blob([texto], {type: 'text/plain'}),
            })]);
            return true;
        } catch {
            // sem permissão para o formato rico: cai no texto puro
        }
    }
    await navigator.clipboard.writeText(texto);
    return false;
}

async function gerarTextoPesquisa() {
    const botao = document.getElementById('btn-buscas-texto');
    const aviso = document.getElementById('buscas-texto-aviso');
    const termo = buscaAtual.termo || document.getElementById('buscas-termo').value.trim();
    if (!termo) return;
    const rotulo = botao.textContent;
    botao.disabled = true;
    botao.textContent = 'Gerando…';
    aviso.hidden = true;
    try {
        const itens = await coletarTodosOsItens(termo);
        const {texto, html, documentoIncompleto, nomeIncompleto, matriculas, descartadas} =
            montarTextoPesquisa(termo, itens);
        const comFormato = await copiarComFormato(texto, html);
        botao.textContent = 'Texto copiado!';
        aviso.hidden = false;

        const partes = [];
        if (!comFormato) {
            partes.push('Copiado sem formatação (este navegador não permitiu o formato rico) — ajuste para Arial 12 e alinhamento à esquerda ao colar.');
        } else {
            partes.push(`Texto ${matriculas.length ? 'positivo' : 'negativo'} copiado.`);
        }
        // O texto declara propriedade: quem ficou de fora precisa ser dito,
        // sobretudo quando a pessoa só tinha matrícula encerrada e o texto
        // por isso saiu negativo.
        const excluidas = Object.entries(descartadas);
        if (excluidas.length) {
            partes.push('Fora do texto: ' + excluidas
                .map(([situacao, numeros]) => `${numeros.length} ${situacao.toLowerCase()} (${numeros.map(n => formatarNumero(n)).join(', ')})`)
                .join('; ') + '.');
        }
        if (documentoIncompleto) {
            partes.push('O CPF/CNPJ saiu mascarado porque a pesquisa foi por nome — complete antes de enviar.');
        }
        if (nomeIncompleto) {
            partes.push('Sem resultado, o nome saiu como NOME_DA_PESSOA — preencha antes de enviar.');
        }
        aviso.textContent = partes.join(' ');
    } catch (erro) {
        aviso.hidden = false;
        aviso.textContent = `Não foi possível gerar o texto: ${erro.message}`;
        botao.textContent = rotulo;
    } finally {
        botao.disabled = false;
        window.setTimeout(() => { botao.textContent = rotulo; }, 2600);
    }
}

function paginaAnterior() {
    if (buscaAtual.pagina > 1) executarPesquisa(buscaAtual.pagina - 1);
}

function proximaPagina() {
    if (buscaAtual.pagina < buscaAtual.totalPaginas) executarPesquisa(buscaAtual.pagina + 1);
}

async function executarIndexacaoInicial() {
    indexando = true;
    atualizarBotao();
    const limite = Number(document.getElementById('buscas-limite').value || 39850);
    registrarEvento(`Indexação iniciada até a matrícula ${formatarNumero(limite)}.`);
    let falhasTemporarias = 0;
    while (indexando) {
        try {
            const resultado = await requisicaoAeri('/api/buscas/sincronizar', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({modo:'INICIAL', tamanho:20, limite}),
            });
            falhasTemporarias = 0;
            atualizarStatus(resultado.estado);
            const mensagem = resultado.falha || `Lote: ${resultado.processados} consultadas · ${resultado.ativas} ativas · ${resultado.encerradas} encerradas · ${resultado.auditoriasValidadas} validadas · ${resultado.auditoriasRevisar} para conferir · ${resultado.falhas} falha(s)`;
            document.getElementById('buscas-status-operacao').textContent = mensagem;
            registrarEvento(mensagem, resultado.falha ? 'erro' : 'sucesso');
            if (resultado.falha || resultado.estado.cargaInicialConcluida || resultado.processados === 0) {
                if (resultado.estado.cargaInicialConcluida) registrarEvento('Carga inicial concluída.', 'sucesso');
                break;
            }
            await new Promise(resolve => window.setTimeout(resolve, 180));
        } catch (erro) {
            const mensagem = erro.message || 'Falha temporária na indexação.';
            if (/sess[aã]o expirou|permiss[aã]o|troque sua senha|configura[cç][aã]o de seguran[cç]a ausente/i.test(mensagem)) {
                document.getElementById('buscas-status-operacao').textContent = mensagem;
                registrarEvento(`Indexação interrompida: ${mensagem}`, 'erro');
                break;
            }
            falhasTemporarias += 1;
            const tentativa = `${mensagem} Nova tentativa (${falhasTemporarias}/5).`;
            document.getElementById('buscas-status-operacao').textContent = tentativa;
            registrarEvento(tentativa, 'alerta');
            if (falhasTemporarias >= 5) {
                registrarEvento('Indexação pausada após cinco falhas consecutivas.', 'erro');
                break;
            }
            await new Promise(resolve => window.setTimeout(resolve, 2000 * falhasTemporarias));
        }
    }
    indexando = false;
    atualizarBotao();
}

function alternarIndexacao() {
    if (revisando) {
        document.getElementById('buscas-status-operacao').textContent = 'Pause a revisão antes de iniciar a carga inicial.';
        return;
    }
    if (indexando) {
        indexando = false;
        atualizarBotao();
        document.getElementById('buscas-status-operacao').textContent = 'Pausa solicitada. O lote atual será concluído.';
        registrarEvento('Pausa manual solicitada.', 'alerta');
        return;
    }
    executarIndexacaoInicial();
}

async function executarRevisao() {
    revisando = true;
    atualizarBotaoRevisao();
    const totalEsperado = Number(
        estadoAtual?.reindexacaoPendente || estadoAtual?.matriculasComTexto || 0
    );
    let totalProcessado = 0;
    let falhasTemporarias = 0;
    const migrandoDocumentos = Number(estadoAtual?.documentosPendentesReindexacao || 0) > 0;
    registrarEvento(migrandoDocumentos
        ? `Reindexação segura iniciada para ${formatarNumero(totalEsperado)} matrícula(s).`
        : `Revisão iniciada para ${formatarNumero(totalEsperado)} matrícula(s) com texto.`);
    while (revisando && totalProcessado < totalEsperado) {
        try {
            const resultado = await requisicaoAeri('/api/buscas/sincronizar', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({modo:'REVISAO', tamanho:20}),
            });
            falhasTemporarias = 0;
            totalProcessado += resultado.processados;
            atualizarStatus(resultado.estado);
            const mensagem = `Revisão: ${formatarNumero(totalProcessado)} de ${formatarNumero(totalEsperado)} · ${resultado.alteradas} alteração(ões) · ${resultado.falhas} falha(s).`;
            document.getElementById('buscas-status-operacao').textContent = mensagem;
            registrarEvento(mensagem, resultado.falhas ? 'alerta' : 'sucesso');
            if (resultado.falha || resultado.processados === 0) break;
            await new Promise(resolve => window.setTimeout(resolve, 180));
        } catch (erro) {
            const mensagemErro = erro.message || 'Falha temporária na revisão.';
            if (/configura[cç][aã]o de seguran[cç]a ausente/i.test(mensagemErro)) {
                document.getElementById('buscas-status-operacao').textContent = mensagemErro;
                registrarEvento(`Revisão interrompida: ${mensagemErro}`, 'erro');
                break;
            }
            falhasTemporarias += 1;
            const mensagem = `${mensagemErro} Nova tentativa (${falhasTemporarias}/5).`;
            registrarEvento(mensagem, 'alerta');
            if (falhasTemporarias >= 5) break;
            await new Promise(resolve => window.setTimeout(resolve, 2000 * falhasTemporarias));
        }
    }
    revisando = false;
    atualizarBotaoRevisao();
    if (totalProcessado >= totalEsperado && totalEsperado > 0) registrarEvento('Revisão completa do índice concluída.', 'sucesso');
}

function alternarRevisao() {
    if (indexando) {
        document.getElementById('buscas-status-operacao').textContent = 'Pause a indexação antes de iniciar a revisão.';
        return;
    }
    if (revisando) {
        revisando = false;
        atualizarBotaoRevisao();
        registrarEvento('Pausa da revisão solicitada.', 'alerta');
        return;
    }
    executarRevisao();
}

async function atualizarNovas() {
    const botao = document.getElementById('btn-buscas-novas');
    botao.disabled = true;
    try {
        if (Number(estadoAtual?.errosPendentes || 0)) {
            const erros = await requisicaoAeri('/api/buscas/sincronizar', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({modo:'ERROS', tamanho:30}),
            });
            atualizarStatus(erros.estado);
            registrarEvento(`${erros.processados} falha(s) reprocessada(s).`, erros.falhas ? 'alerta' : 'sucesso');
        }
        const resultado = await requisicaoAeri('/api/buscas/sincronizar', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body:JSON.stringify({modo:'NOVOS', tamanho:30}),
        });
        atualizarStatus(resultado.estado);
        if (resultado.falha) {
            // Falha de autenticação ou configuração da Tri7 cancela o lote
            // inteiro e devolve zero encontradas. Sem esta mensagem, a tela
            // dizia "0 matrícula(s) nova(s)" -- que se lê como "não há nada
            // novo", e não como "não consegui perguntar".
            const aviso = `A consulta à Tri7 falhou: ${resultado.falha}`;
            document.getElementById('buscas-status-operacao').textContent = aviso;
            registrarEvento(aviso, 'erro');
            return;
        }
        const faixa = resultado.sondagemInicio && resultado.sondagemFim
            ? ` ${formatarNumero(resultado.processados)} número(s) conferido(s) entre ${formatarNumero(resultado.sondagemInicio)} e ${formatarNumero(resultado.sondagemFim)}.`
            : '';
        const avancou = Number(resultado.exploradas || 0)
            ? ` A busca avançou por ${formatarNumero(resultado.exploradas)} número(s) ainda não sondado(s).`
            : ' A janela exploratória está completa; os números ausentes foram reconsultados.';
        const mensagem = resultado.encontradas
            ? `${resultado.encontradas} matrícula(s) nova(s) localizada(s); ${resultado.ativas} ativa(s).${faixa}${avancou}`
            : `Nenhuma matrícula nova localizada.${faixa}${avancou}`;
        document.getElementById('buscas-status-operacao').textContent = mensagem;
        registrarEvento(mensagem, 'sucesso');
    } catch (erro) {
        document.getElementById('buscas-status-operacao').textContent = erro.message;
        registrarEvento(erro.message, 'erro');
    } finally {
        botao.disabled = false;
    }
}

async function reprocessarFalhas() {
    const botao = document.getElementById('btn-buscas-reprocessar');
    botao.disabled = true;
    let total = 0;
    try {
        for (let lote = 0; lote < 20 && Number(estadoAtual?.errosPendentes || 0) > 0; lote += 1) {
            const resultado = await requisicaoAeri('/api/buscas/sincronizar', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({modo:'ERROS', tamanho:30}),
            });
            atualizarStatus(resultado.estado);
            total += resultado.processados;
            if (resultado.processados === 0 || resultado.falha) break;
        }
        const mensagem = `${total} matrícula(s) com falha reprocessada(s); ${estadoAtual?.errosPendentes || 0} pendente(s).`;
        document.getElementById('buscas-status-operacao').textContent = mensagem;
        registrarEvento(mensagem, Number(estadoAtual?.errosPendentes || 0) ? 'alerta' : 'sucesso');
    } catch (erro) {
        document.getElementById('buscas-status-operacao').textContent = erro.message;
        registrarEvento(erro.message, 'erro');
    } finally {
        botao.disabled = false;
    }
}

async function revisarNumero() {
    const numero = Number(document.getElementById('buscas-numero-revisar').value);
    if (!Number.isInteger(numero) || numero <= 0) {
        document.getElementById('buscas-status-operacao').textContent = 'Informe um número de matrícula válido.';
        return;
    }
    const botao = document.getElementById('btn-buscas-revisar');
    botao.disabled = true;
    try {
        const resultado = await requisicaoAeri(`/api/buscas/${numero}/revisar`, {method:'POST'});
        atualizarStatus(resultado.estado);
        const mensagem = `Matrícula ${formatarNumero(numero)} revisada: ${resultado.situacao.toLowerCase()}${resultado.alterado ? ', com alteração detectada' : ', sem alteração'}.`;
        document.getElementById('buscas-status-operacao').textContent = mensagem;
        registrarEvento(mensagem, 'sucesso');
        document.getElementById('buscas-numero-revisar').value = '';
    } catch (erro) {
        document.getElementById('buscas-status-operacao').textContent = erro.message;
        registrarEvento(erro.message, 'erro');
    } finally {
        botao.disabled = false;
    }
}

async function alternarErros() {
    const painel = document.getElementById('buscas-erros-painel');
    if (!painel.hidden) {
        painel.hidden = true;
        return;
    }
    const botao = document.getElementById('btn-buscas-erros');
    botao.disabled = true;
    try {
        const erros = await requisicaoAeri('/api/buscas/erros');
        document.getElementById('buscas-erros-tbody').innerHTML = erros.map(item => `<tr>
            <td>${formatarNumero(item.numero)}</td><td>${escaparHtml(item.modo)}</td><td>${item.tentativas}</td>
            <td>${new Intl.DateTimeFormat('pt-BR', {dateStyle:'short', timeStyle:'short'}).format(new Date(item.ultimaTentativaEm))}</td>
            <td>${escaparHtml(item.erro)}</td>
        </tr>`).join('') || '<tr><td colspan="5" class="rotina-vazio">Nenhuma falha pendente.</td></tr>';
        painel.hidden = false;
    } catch (erro) {
        registrarEvento(erro.message, 'erro');
    } finally {
        botao.disabled = false;
    }
}

function rotuloRevisaoComplementar(status) {
    const rotulos = {
        CONCLUIDA: 'Concluída', PENDENTE: 'Pendente', PROCESSANDO: 'Em processamento',
        FALHA: 'Repetir', DESATIVADA: 'Conferência manual', NAO_NECESSARIA: 'Não necessária',
    };
    return rotulos[status] || 'Conferência manual';
}

async function alternarPendencias() {
    const painel = document.getElementById('buscas-pendencias-painel');
    const botao = document.getElementById('btn-buscas-pendencias');
    if (!painel.hidden) {
        painel.hidden = true;
        botao.textContent = 'Ver pendências';
        return;
    }
    painel.hidden = false;
    botao.textContent = 'Ocultar pendências';
    botao.disabled = true;
    document.getElementById('buscas-pendencias-tbody').innerHTML = '<tr><td colspan="8" class="rotina-vazio">Carregando pendências…</td></tr>';
    painel.scrollIntoView({behavior:'smooth', block:'nearest'});
    try {
        const itens = await requisicaoAeri('/api/buscas/auditoria/pendencias?limite=200');
        document.getElementById('buscas-pendencias-tbody').innerHTML = itens.map(item => {
            const alertas = (item.alertas || []).join(', ') || 'Sem alerta detalhado';
            const conclusao = item.diagnosticoComplementar?.conclusao;
            const revisao = conclusao ? `${rotuloRevisaoComplementar(item.analiseComplementar)} · ${conclusao}`
                : rotuloRevisaoComplementar(item.analiseComplementar);
            return `<tr>
                <td><strong>${formatarNumero(item.matricula)}</strong></td>
                <td><span class="buscas-prioridade" data-prioridade="${escaparHtml(item.prioridade)}">${escaparHtml(item.prioridade)}</span></td>
                <td>${escaparHtml(item.confiancaOnus)}</td><td>${escaparHtml(item.confiancaCadeia)}</td>
                <td>${escaparHtml(item.confiancaImovel)}</td><td>${escaparHtml(alertas)}</td>
                <td>${escaparHtml(revisao)}</td>
                <td class="buscas-pendencia-acoes">
                    <button type="button" class="rotina-btn-secondary" data-diagnostico="${item.matricula}">Diagnóstico</button>
                    <button type="button" class="rotina-btn-secondary buscas-analisar" data-matricula="${item.matricula}">Analisar</button>
                </td>
            </tr>`;
        }).join('') || '<tr><td colspan="8" class="rotina-vazio">Nenhuma pendência registral.</td></tr>';
    } catch (erro) {
        registrarEvento(erro.message, 'erro');
        document.getElementById('buscas-pendencias-tbody').innerHTML = `<tr><td colspan="8" class="rotina-vazio">${escaparHtml(erro.message)}</td></tr>`;
    } finally {
        botao.disabled = false;
    }
}

function renderizarDiagnostico(dados) {
    const proprietarios = (dados.proprietarios || []).map(item => `
        <li><strong>${escaparHtml(item.nome)}</strong> · ${escaparHtml(item.proporcao || 'proporção não informada')}${item.proporcaoIncerta ? ' · proporção presumida' : ''}</li>
    `).join('') || '<li>Nenhum proprietário extraído.</li>';
    const alertas = String(dados.auditoria?.alertas || '').split(';').filter(Boolean);
    const atos = (dados.atos || []).map(ato => `
        <details class="analise-evidencia">
            <summary>${escaparHtml(ato.codigo)} · ${escaparHtml(ato.categoria)} · ${escaparHtml(ato.status)}</summary>
            <blockquote>${escaparHtml(ato.descricao)}</blockquote>
            <small>Tipo: ${escaparHtml(ato.tipoOnus || 'não classificado')}${ato.canceladoPor ? ` · cancelado por ${escaparHtml(ato.canceladoPor)}` : ''}</small>
        </details>
    `).join('');
    document.getElementById('modal-conteudo').innerHTML = `
        <div class="resultado auditoria-diagnostico">
            <span class="eyebrow">DIAGNÓSTICO REGISTRAL MASCARADO</span>
            <h2>Matrícula ${formatarNumero(dados.numero)}</h2>
            <p>${escaparHtml(dados.resultado || '')} · ${escaparHtml(dados.publicidade || '')}</p>
            <section><h3>Alertas</h3><p>${alertas.map(escaparHtml).join(', ') || 'Nenhum alerta.'}</p></section>
            <section><h3>Proprietários extraídos</h3><ul>${proprietarios}</ul></section>
            <details class="analise-evidencia"><summary>Cabeçalho registral</summary><blockquote>${escaparHtml(dados.cabecalho || '')}</blockquote></details>
            <section><h3>Atos</h3>${atos || '<p>Nenhum ato separado.</p>'}</section>
            <p class="buscas-diagnostico-meta">O texto não foi persistido e CPF/CNPJ foram mascarados.</p>
        </div>`;
    document.getElementById('modal-resultado').classList.add('aberta');
}

async function diagnosticarPendencia(botao) {
    const numero = Number(botao.dataset.diagnostico);
    botao.disabled = true;
    const textoOriginal = botao.textContent;
    botao.textContent = 'Consultando…';
    try {
        const dados = await requisicaoAeri(`/api/buscas/auditoria/${numero}/diagnostico`, {
            method:'POST', headers:{'Content-Type':'application/json'}, body:'{}',
        });
        renderizarDiagnostico(dados);
    } catch (erro) {
        registrarEvento(`Diagnóstico ${formatarNumero(numero)}: ${erro.message}`, 'erro');
    } finally {
        botao.disabled = false;
        botao.textContent = textoOriginal;
    }
}

function tratarAcaoPendencia(evento) {
    const diagnostico = evento.target.closest('[data-diagnostico]');
    if (diagnostico) {
        diagnosticarPendencia(diagnostico);
        return;
    }
    abrirAnalise(evento);
}

function abrirAnalise(evento) {
    const botao = evento.target.closest('[data-matricula]');
    if (!botao) return;
    mostrarPagina('onus');
    const campo = document.getElementById('numero-matricula');
    campo.value = botao.dataset.matricula;
    campo.focus();
}

export function iniciarBuscas() {
    document.getElementById('form-buscas').addEventListener('submit', pesquisar);
    document.getElementById('btn-buscas-texto').addEventListener('click', gerarTextoPesquisa);
    document.getElementById('btn-buscas-anterior').addEventListener('click', paginaAnterior);
    document.getElementById('btn-buscas-proxima').addEventListener('click', proximaPagina);
    document.getElementById('btn-buscas-indexar').addEventListener('click', alternarIndexacao);
    document.getElementById('btn-buscas-novas').addEventListener('click', atualizarNovas);
    document.getElementById('btn-buscas-revisar-indice').addEventListener('click', alternarRevisao);
    document.getElementById('btn-buscas-reprocessar').addEventListener('click', reprocessarFalhas);
    document.getElementById('btn-buscas-revisar').addEventListener('click', revisarNumero);
    document.getElementById('btn-buscas-erros').addEventListener('click', alternarErros);
    document.getElementById('btn-buscas-pendencias').addEventListener('click', alternarPendencias);
    document.getElementById('btn-buscas-reprocessar-pendencias').addEventListener('click', alternarReprocessamentoPendencias);
    document.getElementById('buscas-resultados').addEventListener('click', abrirAnalise);
    document.getElementById('buscas-pendencias-tbody').addEventListener('click', tratarAcaoPendencia);
}
