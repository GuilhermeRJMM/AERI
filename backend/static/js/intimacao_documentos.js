import {requisicaoAeri} from './api.js?v=20260902-arquivo-v1';
import {escaparHtml} from './util.js';

const SIGNATARIO_PADRAO = 'Guilherme Richard Jesus Morais Medeiros';
const MESES = ['janeiro','fevereiro','março','abril','maio','junho','julho','agosto','setembro','outubro','novembro','dezembro'];
let intimacaoAtual = null;
let leituraAtual = null;
let htmlAtual = '';
let prepararRtd = null;
let leituraEmCurso = false;
let versaoJanela = 0;

const campo = id => document.getElementById(`doc-int-${id}`);
const valor = id => campo(id).value.trim();
const digitos = texto => String(texto || '').replace(/\D/g, '');
const seguro = texto => escaparHtml(String(texto || ''));

function dataPorExtenso(data) {
    const partes = String(data || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (!partes || !MESES[Number(partes[2]) - 1]) return data;
    return `${Number(partes[1])} de ${MESES[Number(partes[2]) - 1]} de ${partes[3]}`;
}

function dataBrValida(data) {
    const partes = String(data || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (!partes) return false;
    const dia = Number(partes[1]);
    const mes = Number(partes[2]);
    const ano = Number(partes[3]);
    const conferida = new Date(Date.UTC(ano, mes - 1, dia));
    return conferida.getUTCFullYear() === ano && conferida.getUTCMonth() === mes - 1
        && conferida.getUTCDate() === dia;
}

function numeroComPontos(numero) {
    const limpo = digitos(numero);
    return limpo ? limpo.replace(/\B(?=(\d{3})+(?!\d))/g, '.') : String(numero || '');
}

function cpfFormatado(cpf) {
    const limpo = digitos(cpf);
    return limpo.length === 11
        ? `${limpo.slice(0,3)}.${limpo.slice(3,6)}.${limpo.slice(6,9)}-${limpo.slice(9)}`
        : cpf;
}

function cnpjFormatado(cnpj) {
    const limpo = digitos(cnpj);
    return limpo.length === 14
        ? `${limpo.slice(0,2)}.${limpo.slice(2,5)}.${limpo.slice(5,8)}/${limpo.slice(8,12)}-${limpo.slice(12)}`
        : cnpj;
}

function pessoasDoFormulario() {
    return valor('devedores').split(/\r?\n/).map(linha => {
        const [nome = '', cpf = ''] = linha.split('|');
        return {nome:nome.trim(), cpf:digitos(cpf)};
    }).filter(pessoa => pessoa.nome || pessoa.cpf);
}

function enderecosDoFormulario() {
    return valor('enderecos').split(/\r?\n/).map(linha => linha.trim()).filter(Boolean);
}

function atualizarSeletorDevedor() {
    const seletor = campo('devedor-alvo');
    const anterior = seletor.value;
    seletor.replaceChildren();
    pessoasDoFormulario().forEach((pessoa, indice) => {
        const opcao = document.createElement('option');
        opcao.value = String(indice);
        opcao.textContent = pessoa.nome || `Devedor ${indice + 1}`;
        seletor.append(opcao);
    });
    if ([...seletor.options].some(opcao => opcao.value === anterior)) seletor.value = anterior;
}

function abrirDocumentosIntimacao(item) {
    versaoJanela += 1;
    intimacaoAtual = item;
    leituraAtual = null;
    htmlAtual = '';
    document.getElementById('documentos-intimacao-contexto').textContent =
        `IN ${item.protocolo}: selecione o ofício do credor e a planilha de projeção deste processo.`;
    document.getElementById('documentos-intimacao-oficio').value = '';
    document.getElementById('documentos-intimacao-projecao').value = '';
    document.getElementById('documentos-intimacao-titulo-registrado').value = '';
    document.getElementById('documentos-intimacao-confirmar-origem').checked = false;
    document.getElementById('documentos-intimacao-status').textContent = '';
    document.getElementById('documentos-intimacao-editor').hidden = true;
    document.getElementById('documentos-intimacao-previa').hidden = true;
    campo('signatario').value = SIGNATARIO_PADRAO;
    document.getElementById('modal-documentos-intimacao').classList.add('aberta');
}

function fecharDocumentosIntimacao() {
    versaoJanela += 1;
    document.getElementById('modal-documentos-intimacao').classList.remove('aberta');
    document.getElementById('documentos-intimacao-oficio').value = '';
    document.getElementById('documentos-intimacao-projecao').value = '';
    document.getElementById('documentos-intimacao-titulo-registrado').value = '';
    document.getElementById('documentos-intimacao-previa-conteudo').replaceChildren();
    intimacaoAtual = null;
    leituraAtual = null;
    htmlAtual = '';
}

function mostrarLeitura(resultado) {
    leituraAtual = resultado;
    campo('processo').value = resultado.processoCredor || '';
    campo('numero-oficio').value = '';
    campo('protocolo-tri7').value = resultado.protocoloTri7 || '';
    campo('data-protocolo').value = resultado.dataProtocolo || '';
    campo('matricula').value = resultado.matricula || '';
    campo('registro-garantia').value = resultado.registroGarantia || '';
    campo('credor').value = resultado.credor?.nome?.includes('�') && intimacaoAtual?.credor
        ? intimacaoAtual.credor : resultado.credor?.nome || '';
    campo('cnpj').value = resultado.credor?.cnpj || '';
    campo('titulo').value = resultado.titulo || '';
    campo('contrato').value = resultado.contrato?.numero || '';
    campo('data-contrato').value = resultado.contrato?.data || '';
    campo('devedores').value = (resultado.devedores || []).map(p => `${p.nome} | ${p.cpf || ''}`).join('\n');
    campo('endereco-imovel').value = resultado.enderecoImovel || '';
    campo('enderecos').value = (resultado.enderecos || []).join('\n');
    campo('data-projecao').value = resultado.projecao?.data || '';
    campo('valor-projecao').value = resultado.projecao?.valor || '';
    campo('valor-extenso').value = resultado.projecao?.extenso || '';
    campo('signatario').value = SIGNATARIO_PADRAO;
    atualizarSeletorDevedor();
    const avisos = [...(resultado.avisos || []),
        ...(resultado.protocoloIN === 'IN01688738C'
            ? ['Neste IN de teste, confira o signatário: o material enviado foi assinado por Matheus Antônio Alves dos Santos. O padrão dos demais INs continua Guilherme.'] : []),
        ...(resultado.credor?.nome?.includes('�') && intimacaoAtual?.credor
            ? ['O nome do credor veio ilegível do PDF; o campo foi preenchido com o cadastro deste IN no AERI. Confirme a grafia no documento.'] : []),
        'Confirme o CEP atualizado, a descrição do título, o registro da garantia, a data do protocolo e o número sequencial do ofício.'];
    document.getElementById('documentos-intimacao-avisos').innerHTML = avisos.map(aviso => `<p>${seguro(aviso)}</p>`).join('');
    document.getElementById('documentos-intimacao-editor').hidden = false;
    document.getElementById('documentos-intimacao-previa').hidden = true;
    htmlAtual = '';
    document.getElementById('documentos-intimacao-status').textContent =
        `Leitura concluída para ${resultado.protocoloIN}. Confira os campos antes de preparar cada texto.`;
}

async function lerDocumentos() {
    if (!intimacaoAtual) return;
    const oficio = document.getElementById('documentos-intimacao-oficio').files?.[0];
    const projecao = document.getElementById('documentos-intimacao-projecao').files?.[0];
    const status = document.getElementById('documentos-intimacao-status');
    const tituloRegistrado = document.getElementById('documentos-intimacao-titulo-registrado').files?.[0];
    if (!oficio || !projecao || [oficio, projecao, tituloRegistrado].filter(Boolean).some(arquivo => arquivo.size > 8_000_000)) {
        status.textContent = 'Selecione o ofício e a planilha em PDF, cada um com até 8 MB.';
        return;
    }
    if (!document.getElementById('documentos-intimacao-confirmar-origem').checked) {
        status.textContent = 'Confira se os documentos pertencem ao IN selecionado e marque a confirmação de origem.';
        return;
    }
    if (oficio.size + projecao.size + (tituloRegistrado?.size || 0) > 4_000_000) {
        status.textContent = 'Os PDFs selecionados passam de 4 MB no total. Use a leitura da pasta pelo executor ou selecione apenas o ofício e a projeção.';
        return;
    }
    const botao = document.getElementById('btn-analisar-documentos-intimacao');
    const dados = new FormData();
    dados.set('oficio', oficio, oficio.name);
    dados.set('projecao', projecao, projecao.name);
    if (tituloRegistrado) dados.set('titulo_registrado', tituloRegistrado, tituloRegistrado.name);
    botao.disabled = true;
    status.textContent = 'Lendo os dois documentos…';
    try {
        const resultado = await requisicaoAeri(
            `/api/intimacoes/${intimacaoAtual.id}/preparar-documentos`,
            {method:'POST', body:dados},
        );
        mostrarLeitura(resultado);
    } catch (erro) {
        leituraAtual = null;
        document.getElementById('documentos-intimacao-editor').hidden = true;
        status.textContent = erro.message;
    } finally {
        botao.disabled = false;
    }
}

async function lerDocumentosDaRede() {
    if (!intimacaoAtual || leituraEmCurso) return;
    const versao = versaoJanela;
    leituraEmCurso = true;
    const botao = document.getElementById('btn-ler-documentos-intimacao-rede');
    const status = document.getElementById('documentos-intimacao-status');
    botao.disabled = true;
    status.textContent = 'Solicitando ao executor a leitura dos PDFs na pasta deste IN…';
    try {
        const base = `/api/intimacoes/${intimacaoAtual.id}/preparar-documentos-rede`;
        const trabalho = await requisicaoAeri(base, {method:'POST'});
        for (let tentativa = 0; tentativa < 60; tentativa += 1) {
            if (versao !== versaoJanela) return;
            await new Promise(resolve => setTimeout(resolve, 2000));
            if (versao !== versaoJanela) return;
            const resposta = await requisicaoAeri(`${base}/${trabalho.id}`, {background:true});
            if (resposta.estado === 'PRONTO') {
                mostrarLeitura(resposta.dados);
                return;
            }
            if (resposta.estado === 'ERRO') throw new Error(resposta.erro || 'Não foi possível ler a pasta do IN.');
            status.textContent = `Lendo a pasta do IN no executor… (${tentativa + 1}/60)`;
        }
        throw new Error('A leitura demorou mais de dois minutos. Confira o executor e tente novamente.');
    } catch (erro) {
        if (versao === versaoJanela) status.textContent = erro.message;
    } finally {
        leituraEmCurso = false;
        botao.disabled = false;
    }
}

function centrar(texto) {
    return `<p style="text-align:center;margin:0 0 10pt">${texto}</p>`;
}

function paragrafo(texto) {
    return `<p style="text-align:justify;margin:0 0 10pt">${texto}</p>`;
}

function titulo(texto) {
    return centrar(`<strong>${texto}</strong>`);
}

function moeda(valorBruto) {
    const texto = String(valorBruto || '').trim();
    const numero = Number(texto.includes(',') ? texto.replace(/\./g, '').replace(',', '.') : texto);
    return Number.isFinite(numero) && numero >= 0
        ? `R$${numero.toLocaleString('pt-BR', {minimumFractionDigits:2, maximumFractionDigits:2})}` : '';
}

function lerDados() {
    const pessoas = pessoasDoFormulario();
    const enderecos = enderecosDoFormulario();
    const alvo = pessoas[Number(campo('devedor-alvo').value)] || pessoas[0] || null;
    return {
        in: leituraAtual?.protocoloIN || intimacaoAtual?.protocolo || '',
        dataGeracao: leituraAtual?.dataGeracao || '',
        processo: valor('processo'), oficio: valor('numero-oficio'),
        protocolo: valor('protocolo-tri7'), dataProtocolo: valor('data-protocolo'),
        matricula: numeroComPontos(valor('matricula')), registro: valor('registro-garantia'),
        credor: valor('credor'), cnpj: cnpjFormatado(valor('cnpj')),
        titulo: valor('titulo'), contrato: valor('contrato'), dataContrato: valor('data-contrato'),
        pessoas, alvo, enderecoImovel: valor('endereco-imovel'), enderecos,
        dataProjecao: valor('data-projecao'), valorProjecao: moeda(valor('valor-projecao')),
        valorExtenso: valor('valor-extenso'),
        signatario: valor('signatario'),
    };
}

function pendencias(tipo, dados) {
    const campos = [
        ['processo do credor', dados.processo], ['protocolo Tri7', dados.protocolo],
        ['data do protocolo', dataBrValida(dados.dataProtocolo)], ['matrícula', dados.matricula],
        ['credor', dados.credor], ['CNPJ do credor', digitos(dados.cnpj).length === 14],
        ['descrição do título', dados.titulo], ['número do contrato', dados.contrato],
        ['data do contrato', dataBrValida(dados.dataContrato)], ['endereço do imóvel', dados.enderecoImovel],
        ['escrevente', dados.signatario], ['devedores com nome e CPF', dados.pessoas.length && dados.pessoas.every(pessoa => pessoa.nome && pessoa.cpf.length === 11)],
    ];
    if (tipo === 'oficio') campos.push(
        ['número sequencial do ofício no formato INT/AAAA/NNN',
            new RegExp(`^INT/${dados.dataGeracao.slice(-4)}/\\d{3}$`, 'i').test(dados.oficio)],
        ['registro da garantia', dados.registro],
        ['valor da projeção', dados.valorProjecao], ['data da projeção', dataBrValida(dados.dataProjecao)],
        ['valor por extenso', dados.valorExtenso],
        ['projeção na data da minuta', dados.dataProjecao === dados.dataGeracao],
        ['endereço em Morrinhos', dados.enderecos.some(endereco => /MORRINHOS/i.test(endereco))],
        ['CEP de cada endereço de Morrinhos', dados.enderecos.filter(endereco => /MORRINHOS/i.test(endereco))
            .every(endereco => /\bCEP\s*:?\s*\d{2}\.?\d{3}[-.]?\d{3}\b/i.test(endereco))],
    );
    if (tipo === 'convocacao') campos.push(['registro da garantia', dados.registro]);
    if (tipo === 'autuacao') campos.push(['endereço de intimação', dados.enderecos.length]);
    if ([dados.credor, dados.titulo, dados.enderecoImovel, ...dados.enderecos,
        ...dados.pessoas.map(pessoa => pessoa.nome)].some(texto => String(texto).includes('�'))) {
        campos.push(['correção dos caracteres ilegíveis extraídos do PDF', false]);
    }
    return campos.filter(([_nome, preenchido]) => !preenchido).map(([nome]) => nome);
}

export function gerarAutuacao(d) {
    const pessoas = d.pessoas.map(p => `${seguro(p.nome)}, CPF n.º ${seguro(cpfFormatado(p.cpf))}`).join('; ');
    const rotulo = d.pessoas.length === 1 ? 'DEVEDOR FIDUCIANTE' : 'DEVEDORES FIDUCIANTES';
    return [
        titulo(`PROCESSO N.º ${seguro(d.processo)}`),
        centrar(`SAEC/ONR - ${seguro(d.in)}`),
        paragrafo('<strong>PROCEDIMENTO:</strong> Intimação, art. 26 da Lei Federal n.º 9.514/1997.'),
        paragrafo(`<strong>TÍTULO:</strong> ${seguro(d.titulo)} n.º ${seguro(d.contrato)}, datado de ${seguro(d.dataContrato)}.`),
        paragrafo(`<strong>CREDORA FIDUCIÁRIA:</strong> ${seguro(d.credor)}.`),
        paragrafo(`<strong>${rotulo}:</strong> ${pessoas}.`),
        paragrafo(`<strong>ENDEREÇO:</strong> ${seguro(d.enderecos.join('; '))}.`),
        titulo('AUTUAÇÃO'),
        paragrafo(`Aos ${seguro(dataPorExtenso(d.dataGeracao))}, nesta cidade e Comarca de Morrinhos, Estado de Goiás, e neste Cartório do 1º Ofício de Notas e Registro de Imóveis, situado na Rua Maestro Vicente José Vieira, n.º 706, Loja 01, Centro, CEP 75.650-082, autuo o requerimento e demais documentos que o acompanham, protocolado em ${seguro(dataPorExtenso(d.dataProtocolo))} sob o n.º ${seguro(numeroComPontos(d.protocolo))}. Eu, ${seguro(d.signatario)}, Escrevente, lavrei o presente termo e assino digitalmente.`),
    ].join('');
}

export function gerarOficio(d) {
    const devedor = `${seguro(d.alvo.nome.toLocaleUpperCase('pt-BR'))}, CPF n.º ${seguro(cpfFormatado(d.alvo.cpf))}`;
    const emMorrinhos = d.enderecos.filter(endereco => /MORRINHOS/i.test(endereco));
    const enderecos = emMorrinhos.map((endereco, indice) => paragrafo(`${indice + 1}) ${seguro(endereco)}.`)).join('');
    return [
        '<section style="page-break-after:always;break-after:page">',
        paragrafo(`Morrinhos-GO, ${seguro(dataPorExtenso(d.dataGeracao))}.`),
        paragrafo(`Ofício n.º <strong>${seguro(d.oficio)}</strong>.`),
        paragrafo(`Protocolo n.º ${seguro(numeroComPontos(d.protocolo))}, datado de ${seguro(dataPorExtenso(d.dataProtocolo))}.<br>Autuação Processo n.º ${seguro(d.processo)} - SAEC/ONR ${seguro(d.in)}.`),
        paragrafo(`Ao Ilmo. Sr. <strong>${devedor}</strong>.`),
        paragrafo('Prezado Senhor,'),
        paragrafo(`Na qualidade de Escrevente do Cartório do 1º Ofício de Notas e Registro de Imóveis do Município e Comarca de Morrinhos-GO, e segundo as atribuições conferidas pelo art. 26 da Lei Federal n.º 9.514/1997, bem como pelo credor do ${seguro(d.titulo)} n.º ${seguro(d.contrato)}, firmado em ${seguro(d.dataContrato)}, garantido por alienação fiduciária registrada sob o ${seguro(d.registro)}, na Matrícula n.º ${seguro(d.matricula)}, deste Cartório, referente ao imóvel situado em ${seguro(d.enderecoImovel)}, venho intimar V.S.ª para cumprimento das obrigações contratuais relativas aos encargos vencidos.`),
        paragrafo(`Informo que o valor desses encargos, posicionado em ${seguro(dataPorExtenso(d.dataProjecao))}, corresponde a <strong>${seguro(d.valorProjecao)} (${seguro(d.valorExtenso)})</strong>, sujeito à atualização monetária, aos juros de mora e às despesas de cobrança até o efetivo pagamento. Acrescem as parcelas que se vencerem no prazo desta intimação, as custas e os emolumentos cartoriais, conforme a planilha de projeção e os comprovantes anexos.`),
        paragrafo(`Assim, procedo à INTIMAÇÃO de V.S.ª para que compareça ao Cartório do 1º Ofício de Notas e Registro de Imóveis, situado na Rua Maestro Vicente José Vieira, n.º 706, Loja 01, Centro, Morrinhos-GO, CEP 75.650-082, de segunda a sexta-feira, das 08h às 17h, a fim de promover a purgação da mora no prazo de 15 dias, contado do recebimento desta intimação, nos termos do art. 26, § 1º, da Lei Federal n.º 9.514/1997.`),
        paragrafo(`Fica V.S.ª ciente de que o não cumprimento da obrigação no prazo legal poderá importar na consolidação da propriedade do imóvel em favor da credora fiduciária ${seguro(d.credor)}, inscrita no CNPJ sob o n.º ${seguro(d.cnpj)}, observadas as exigências legais aplicáveis.`),
        paragrafo('Atenciosamente,'),
        paragrafo(`Assinado digitalmente<br>${seguro(d.signatario)} - Escrevente`),
        '</section><section style="page-break-after:always;break-after:page">',
        titulo('CONTRA-FÉ'),
        paragrafo('Declaro que, nesta data de ____/____/_______, às ______ horas, recebi o ofício retro.'),
        paragrafo('________________________________________'),
        titulo('CERTIDÃO'),
        paragrafo('Certifico e dou fé, na qualidade de Escrevente responsável pelas diligências da intimação retro, que:'),
        paragrafo('(  ) Compareci ao local indicado pela credora fiduciária em três dias e horários alternados: ____/____/_______, às ______; ____/____/_______, às ______; e ____/____/_______, às ______. Não encontrei o fiduciante nem seu representante, não havendo suspeita motivada de ocultação. Deixei uma via de inteiro teor da notificação na caixa de correspondências e uma convocação para comparecimento ao Cartório no prazo de 15 dias corridos, contado da última diligência.'),
        paragrafo('(  ) No dia ____/____/_______, às ______, intimei pessoalmente o Sr. _______________________________________, conforme a contra-fé acima.'),
        paragrafo('(  ) No dia ____/____/_______, às ______, comuniquei ao Sr. _______________________________________ o retorno ao endereço em ____/____/_______, às ______, para proceder à intimação por hora certa, solicitando que informasse o devedor.'),
        paragrafo('(  ) No dia ____/____/_______, às ______, retornei ao endereço combinado, mas não encontrei o fiduciante nem seu representante. Deixei uma via de inteiro teor da notificação na caixa de correspondências do imóvel.'),
        paragrafo('(  ) No dia ____/____/_______, às ______, retornei ao endereço combinado e, havendo suspeita motivada de ocultação, não encontrei o fiduciante nem seu representante. Deixei uma via de inteiro teor da notificação na caixa de correspondências do imóvel.'),
        paragrafo('(  ) No dia ____/____/_______, às ______, intimei pessoalmente o devedor, que se recusou a receber o ofício acompanhado das planilhas e a dar contra-fé.'),
        paragrafo('(  ) Compareci ao endereço indicado e não intimei pessoalmente o devedor por se encontrar em local ignorado ou incerto, após três tentativas em dias e horários alternados: ____/____/_______, às ______; ____/____/_______, às ______; e ____/____/_______, às ______.'),
        '</section><section>',
        paragrafo('Concluídas as diligências, devolvo a documentação ao Escrevente encarregado do procedimento de intimação.'),
        paragrafo('Morrinhos-GO, ____ de ____________________ de ______.'),
        paragrafo('________________________________________<br>Escrevente'),
        paragrafo('<strong>Endereços para notificação nesta primeira remessa em Morrinhos:</strong>'),
        enderecos,
        paragrafo('<strong>OBSERVAÇÕES:</strong>'),
        '</section>',
    ].join('');
}

export function gerarConvocacao(d) {
    return [
        titulo('CONVOCAÇÃO'),
        paragrafo('Ilmo Sr.'),
        paragrafo(`<strong>${seguro(d.alvo.nome.toLocaleUpperCase('pt-BR'))}, CPF n.º ${seguro(cpfFormatado(d.alvo.cpf))}</strong>`),
        paragrafo(`Pelo presente, após tentativa pessoal em seu domicílio, convoco V.S.ª a comparecer neste Cartório, situado na Rua Maestro Vicente José Vieira, n.º 706, Loja 01, Centro, Morrinhos-GO, CEP 75.650-082, no período das 08h às 17h, a fim de tratar de assunto de seu interesse relacionado ao ${seguro(d.titulo)} n.º ${seguro(d.contrato)}, datado de ${seguro(d.dataContrato)}, registrado sob o ${seguro(d.registro)} na Matrícula n.º ${seguro(d.matricula)}, deste Cartório, referente ao imóvel situado em ${seguro(d.enderecoImovel)}.`),
        paragrafo('Atenciosamente,'),
        paragrafo(`Assinado digitalmente<br>${seguro(d.signatario)} - Escrevente`),
    ].join('');
}

function prepararDocumento(tipo) {
    if (!leituraAtual) return;
    const d = lerDados();
    const hoje = new Intl.DateTimeFormat('pt-BR', {timeZone:'America/Sao_Paulo'}).format(new Date());
    const faltando = d.dataGeracao === hoje ? pendencias(tipo, d) : ['nova leitura dos documentos na data de hoje'];
    const status = document.getElementById('documentos-intimacao-status');
    if (faltando.length) {
        status.textContent = `Complete antes de preparar: ${faltando.join(', ')}.`;
        return;
    }
    const geradores = {autuacao:gerarAutuacao, oficio:gerarOficio, convocacao:gerarConvocacao};
    const rotulos = {autuacao:'Autuação', oficio:'Ofício Contra-Fé', convocacao:'Convocação'};
    htmlAtual = geradores[tipo](d);
    document.getElementById('documentos-intimacao-previa-conteudo').innerHTML = htmlAtual;
    document.getElementById('documentos-intimacao-previa-titulo').textContent = `Prévia: ${rotulos[tipo]}`;
    document.getElementById('documentos-intimacao-previa').hidden = false;
    status.textContent = tipo === 'oficio'
        ? 'Prévia para conferência: compare a redação jurídica, cláusulas específicas do contrato, selo, CEP e páginas 2 e 3 com o modelo da Tri7 antes de salvar. Confira se o PDF final tem três páginas.'
        : 'Confira a prévia e cole no modelo correspondente na aba Texto da Tri7.';
    document.getElementById('documentos-intimacao-previa').scrollIntoView({block:'nearest'});
}

async function copiarDocumento() {
    if (!htmlAtual) return;
    const texto = document.getElementById('documentos-intimacao-previa-conteudo').innerText;
    const status = document.getElementById('documentos-intimacao-status');
    try {
        if (navigator.clipboard?.write && globalThis.ClipboardItem) {
            await navigator.clipboard.write([new ClipboardItem({
                'text/html':new Blob([htmlAtual], {type:'text/html'}),
                'text/plain':new Blob([texto], {type:'text/plain'}),
            })]);
        } else {
            await navigator.clipboard.writeText(texto);
        }
        status.textContent = 'Texto copiado. Cole no modelo correspondente da Tri7 e confira o PDF gerado.';
    } catch (_) {
        status.textContent = 'O navegador não permitiu a cópia. Selecione a prévia e copie manualmente.';
    }
}

function enderecoParaRtd(original) {
    const cepMatch = original.match(/\bCEP\s*:?\s*(\d{5})[-.]?(\d{3})\b/i);
    const semCep = (cepMatch ? original.slice(0, cepMatch.index) : original).replace(/[,;\s]+$/, '');
    const cidadeMatch = semCep.match(/,\s*([^,]+?)\s*[/\-]\s*([A-Za-z]{2})$/);
    const antesCidade = cidadeMatch ? semCep.slice(0, cidadeMatch.index) : semCep;
    const numeroMatch = antesCidade.match(/(?:,\s*|\s+n[ºo°.]?\s*)(\d{1,6}[A-Za-z]?(?:[-/][A-Za-z0-9]+)?)\b/i);
    const logradouro = numeroMatch ? antesCidade.slice(0, numeroMatch.index).replace(/,\s*/g, ' ').trim() : '';
    const restante = numeroMatch ? antesCidade.slice(numeroMatch.index + numeroMatch[0].length).replace(/^,\s*/, '') : '';
    const partes = restante.split(',').map(parte => parte.trim()).filter(Boolean);
    return {
        CEP:cepMatch ? `${cepMatch[1]}${cepMatch[2]}` : '',
        Logradouro:logradouro, Numero:numeroMatch?.[1] || '',
        Complemento:partes.length > 1 ? partes.slice(0,-1).join(', ') : '',
        Bairro:partes.length ? partes.at(-1) : '',
        Cidade:cidadeMatch?.[1]?.trim() || '', UF:cidadeMatch?.[2]?.toUpperCase() || '',
    };
}

export function montarParesRtd(pessoas, enderecos) {
    return pessoas.flatMap(pessoa => enderecos
        .filter(endereco => /MORRINHOS/i.test(endereco))
        .map(original => ({pessoa, endereco:enderecoParaRtd(original)})));
}

function prepararNotificacoes() {
    if (!leituraAtual || !intimacaoAtual || !prepararRtd) return;
    const pessoas = pessoasDoFormulario();
    const enderecos = enderecosDoFormulario().filter(endereco => /MORRINHOS/i.test(endereco));
    const status = document.getElementById('documentos-intimacao-status');
    if (!pessoas.length || !enderecos.length) {
        status.textContent = 'Informe devedores com CPF e ao menos um endereço de Morrinhos para esta primeira remessa.';
        return;
    }
    const pares = montarParesRtd(pessoas, enderecos);
    if (pares.length > 20 || pares.some(par => par.pessoa.cpf.length !== 11)) {
        status.textContent = 'Revise os CPFs e limite esta preparação a 20 notificações individuais.';
        return;
    }
    if (pares.some(par => !par.pessoa.nome || par.endereco.Cidade.toLocaleUpperCase('pt-BR') !== 'MORRINHOS'
        || par.endereco.UF !== 'GO')) {
        status.textContent = 'Revise os nomes e separe somente os endereços de Morrinhos-GO nesta primeira remessa.';
        return;
    }
    if ([valor('credor'), ...pessoas.map(pessoa => pessoa.nome), ...enderecos].some(texto => texto.includes('�'))) {
        status.textContent = 'Corrija os caracteres ilegíveis extraídos do PDF antes de preparar as notificações.';
        return;
    }
    const itemId = intimacaoAtual.id;
    const credor = valor('credor');
    const cnpj = digitos(valor('cnpj'));
    fecharDocumentosIntimacao();
    prepararRtd(itemId, pares, {credor, cnpj});
}

export function iniciarDocumentosIntimacao(abrirRtdComPares) {
    prepararRtd = abrirRtdComPares;
    document.getElementById('btn-fechar-documentos-intimacao').addEventListener('click', fecharDocumentosIntimacao);
    document.getElementById('modal-documentos-intimacao').addEventListener('click', evento => {
        if (evento.target.id === 'modal-documentos-intimacao') fecharDocumentosIntimacao();
    });
    document.getElementById('btn-analisar-documentos-intimacao').addEventListener('click', lerDocumentos);
    document.getElementById('btn-ler-documentos-intimacao-rede').addEventListener('click', lerDocumentosDaRede);
    document.getElementById('doc-int-devedores').addEventListener('input', atualizarSeletorDevedor);
    document.getElementById('documentos-intimacao-editor').addEventListener('input', evento => {
        if (!evento.target.matches('input,textarea,select')) return;
        if (evento.target.id === 'doc-int-valor-projecao') campo('valor-extenso').value = '';
        htmlAtual = '';
        document.getElementById('documentos-intimacao-previa').hidden = true;
    });
    document.getElementById('documentos-intimacao-editor').addEventListener('click', evento => {
        const tipo = evento.target.closest('[data-documento-intimacao]')?.dataset.documentoIntimacao;
        if (tipo) prepararDocumento(tipo);
    });
    document.getElementById('btn-copiar-documento-intimacao').addEventListener('click', copiarDocumento);
    document.getElementById('btn-preparar-rtd-dados-intimacao').addEventListener('click', prepararNotificacoes);
}

export {abrirDocumentosIntimacao};
