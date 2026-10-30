// Transcrição dos modelos fornecidos em 30/10/2026. Sem assinatura, selo ou ato automático.
import {escaparHtml} from './util.js';
const e = v => escaparHtml(String(v ?? ''));
const MESES = ['janeiro','fevereiro','março','abril','maio','junho','julho','agosto','setembro','outubro','novembro','dezembro'];
export function dataExtenso(v) {
    const m = String(v || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    return m && MESES[+m[2]-1] ? `${+m[1]} de ${MESES[+m[2]-1]} de ${m[3]}` : String(v || '');
}
export function proximoOficio(ultimo, ano) {
    const m = String(ultimo).trim().match(/^(?:INT\/(\d{4})\/)?(\d{1,6})$/i);
    if (!m || !/^\d{4}$/.test(String(ano)) || (m[1] && m[1] !== String(ano)) || +m[2] >= 999999) {
        throw new Error('Informe o último ofício como 52 ou INT/AAAA/052, com o ano da preparação.');
    }
    return `INT/${ano}/${String(+m[2]+1).padStart(Math.max(3,m[2].length),'0')}`;
}
const cpf = n => String(n || '').replace(/\D/g,'').replace(/(\d{3})(\d{3})(\d{3})(\d{2})/,'$1.$2.$3-$4');
const numero = n => String(n || '').replace(/\D/g,'').replace(/\B(?=(\d{3})+(?!\d))/g,'.');
const p = (s,css='') => `<p style="margin:0 0 10pt;text-align:justify;${css}">${s}</p>`;
const centro = s => p(s,'text-align:center;');
const titulo = (s,tamanho=12) => centro(`<strong style="font-size:${tamanho}pt"><u>${s}</u></strong>`);
const moldura = (s,tamanho,altura,espaco=0) => `<div style="width:165mm;max-width:100%;margin:0 auto;font-family:Arial,sans-serif;font-size:${tamanho}pt;line-height:${altura};color:#000;background:#fff">${s.replaceAll('margin:0 0 10pt;',`margin:0 0 ${espaco}pt;`)}</div>`;
const alvo = d => `${e(d.alvo?.nome?.toLocaleUpperCase('pt-BR'))}(CPF: ${e(cpf(d.alvo?.cpf))}).`;

export function gerarAutuacao(d) {
    return moldura([
        titulo(`PROCESSO N.° ${e(d.processo)}`,15),
        titulo(`SAEC/ONR - ${e(d.in)}`,15),
        p('<strong><u>PROCEDIMENTO</u>:</strong> Intimação (art.26 - Lei Federal n.º 9.514/1997).','margin-top:22pt;'),
        p(`<strong><u>TÍTULO</u>:</strong> ${e(d.titulo)}${/\bn[.º°o\s]*$/i.test(d.titulo)?'':' n.°'} ${e(d.contrato)}, datado de ${e(d.dataTituloAutuacao)}.`,'margin-top:20.76pt;'),
        p(`<strong><u>CREDOR(A) FIDUCIÁRIO(A)</u>:</strong> ${e(d.credor)}.`,'margin-top:18pt;'),
        p(`<strong><u>DEVEDOR(A)(ES) FIDUCIANTE(S)</u>:</strong> ${d.pessoas.map(x=>`${e(x.nome)}, (CPF: ${e(cpf(x.cpf))})`).join('; ')}.`,'margin-top:18pt;'),
        p(`<strong><u>ENDEREÇO</u>:</strong> ${e(d.enderecoImovel)}.`,'margin-top:18pt;'),
        p('<strong style="font-size:18pt">AUTUAÇÃO</strong>','text-align:center;margin-top:20.76pt;'),
        p(`Aos ${e(dataExtenso(d.dataGeracao))}, nesta cidade e Comarca de Morrinhos, Estado de Goiás, e neste Cartório do 1º Ofício de Notas e Registro de Imóveis, situado na Rua Maestro Vicente José Vieira, 706, Loja 01, centro, CEP: 75.650-082, <strong>autuo o requerimento e demais documentos que o acompanham</strong>, protocolado em ${e(dataExtenso(d.dataProtocolo))} sob o n.º ${e(numero(d.protocolo))}. Eu, ${e(d.signatario)}, Escrevente, lavrei o presente termo, e assino digitalmente.`,'margin-top:24pt;'),
    ].join(''),12,1.73);
}

export function gerarOficio(d) {
    const certidoes = [
        '(   ) Compareci ao local indicado pelo(a) credor(a) fiduciário(a) em 03 (três) dias e horas alternadas, a saber: dia ___/___/_____, às ___:___ horas; dia ___/___/_____, às ___:___ horas; e, dia ___/___/_____, às ___:___ horas e <strong>não encontrei o(a) fiduciante, nem seu representante; razão porque restou frustrada sua intimação pessoal, não havendo nenhuma suspeita motivada de ocultação, onde: foi deixada uma via de inteiro teor da notificação na caixa de correspondências, bem como uma convocação para que a parte compareça no Cartório no prazo de 15 (quinze) dias corridos, contados da data da última diligência.</strong>',
        '(   ) No dia ___/___/_____, às ___:___ horas, <strong>intimei pessoalmente</strong> o(a) Sr.(a) __________________________________________________, conforme contra-fé supra.',
        '(   ) No dia ___/___/_____, às ___:___ horas, <strong>intimei pessoalmente</strong> o(a) Sr.(a) ___________________________________________________________, dando ciência da consequência da situação, no qual se comprometeu à informar o(a) devedor(a) sobre o compromisso, afim de retornar no endereço/local no dia ___/___/_____, às ___:___ horas para proceder com a intimação por hora certa.',
        '(  ) No dia ___/___/_____, às ___:___ horas, retornei ao endereço/local combinado com o(a) senhor(a)________________________________________________, afim de proceder com a intimação, conforme combinado, e <strong>não encontrei o(a) fiduciante nem seu representante; razão porque restou frustrada sua intimação pessoa, onde: foi deixada uma via de inteiro teor da notificação na caixa de correspondências do imóvel.</strong>',
        '(  ) No dia ___/___/_____, às ___:___ horas, retornei ao endereço/local combinado com o(a) senhor(a)________________________________________________, afim de proceder com a intimação, conforme combinado, e <strong>não encontrei o(a) fiduciante nem seu representante; havendo suspeita motivada de ocultação, razão porque restou frustrada sua intimação pessoa, onde: foi deixada uma via de inteiro teor da notificação na caixa de correspondências do imóvel.</strong>',
        '(    ) No dia ___/___/_____, às ___:___ horas, intimei pessoalmente o(a) devedor(a), que se recusou a receber o ofício retro acompanhado das respectivas planilhas, bem como se recusou a dar a sua contra-fé.',
    ];
    return moldura([
        '<section style="page-break-after:always;break-after:page">',
        p(`Morrinhos-GO, ${e(dataExtenso(d.dataGeracao))}.`,'text-align:right;margin-bottom:0;'),
        p(`Ofício n.º ${e(d.oficio)}`),
        p(`Protocolo n.º ${e(numero(d.protocolo))}, datado de ${e(dataExtenso(d.dataProtocolo))}<br>Autuação Processo n.º ${e(d.processo)} - SAEC/ONR ${e(d.in)}<br><strong>Ao Ilmo(a) Sr(a). ${alvo(d)}</strong>`),
        p('Prezado(a) Senhor(a),','text-indent:25mm;margin-bottom:15pt;'),
        p(`Na qualidade de Escrevente do Cartório do 1º Ofício de Notas e Registro de Imóveis do Município e Comarca de Morrinhos-GO, e segundo atribuições conferidas pelo art. 26, da Lei Federal n.º 9.514/1997, bem como pelo(a) Credor(a) do ${e(d.titulo)} de financiamento imobiliário n.º ${e(d.contrato)}, garantido por Alienação Fiduciária, firmado em ${e(d.dataContrato)}, registrado sob o ${e(d.registro)}, na Matrícula n.º ${e(d.matricula)}, deste Cartório, referente ao imóvel situado na ${e(d.enderecoImovel)}, com saldo devedor de responsabilidade de V.S.ª, <strong>venho intimar-lhe</strong> para fins de cumprimento das obrigações contratuais relativas aos encargos.`,'text-indent:25mm;'),
        p(`Informo, que o valor destes encargos, posicionado em ${e(dataExtenso(d.dataProjecao))}, <strong><u>corresponde a ${e(d.valorProjecao)} (${e(d.valorExtenso)})</u></strong>, estando sujeitos à atualização monetária, aos juros de mora e às despesas de cobrança até a data do efetivo pagamento, somando-se também os encargos que vencerem no prazo desta intimação, além das despesas de custas e emolumentos cartoriais, conforme prova demonstrativo de débitos decorrente das prestações vencidas apresentadas pelo interessado, bem como recibo das despesas inerentes à intimação expedido pelo CRI. competente até a presente data, anexos.`,'text-indent:25mm;'),
        p(`Comunico, conforme Cláusula contida do contrato <strong>"${e(d.clausula)}"</strong>, os devedores se declararam solidariamente responsáveis pelas obrigações assumidas perante a credora fiduciária e constituíram-se procuradores recíprocos, com poderes para receber intimações, dentre outros.`,'text-indent:25mm;'),
        p('Assim, <strong>procedo à INTIMAÇÃO de V.S.ª</strong> para que se dirija a este Ofício de Registro de Imóveis, situado na Rua Maestro Vicente José Vieira, 706, Loja 01, centro, nesta cidade de Morrinhos-GO, CEP: 75.650-082, que funciona de segunda a sexta-feira das 08:00 às 17:00 horas, a fim de promover a <strong>purgação do débito acima discriminado, no prazo improrrogável de 15 (quinze) dias</strong>, contados a partir do recebimento desta intimação, nos termos do §1º do art. 26 da Lei Federal nº 9.514/1997.','text-indent:25mm;'),
        p(`Portanto, fica V.S.ª <strong>cientificada</strong> de que o não cumprimento da obrigação referida, no prazo ora estipulado, importará na consolidação da propriedade do imóvel em favor do(a) credor(a) fiduciário(a) ${e(d.credorEncerramento || d.credor)} (CNPJ: ${e(d.cnpj)}), nos termos do art. 26, §7º, da Lei Federal n.º 9.514/1997. Esclareço, ainda, que, tratando-se de financiamento destinado à aquisição ou construção de imóvel residencial (excetuadas as operações de consórcio regidas pela Lei nº 11.795/2008), é assegurado ao devedor ou ao terceiro fiduciante, até a data da averbação da consolidação da propriedade fiduciária (a qual ocorre 30 dias após o término do prazo para purga da mora), o direito de quitar as parcelas vencidas e as despesas previstas no inciso II do §3º do art. 27 da supracitada Lei. Selo: ${e(d.selo)}, consulte em http://extrajudicial.tjgo.jus.br/selo.`,'text-indent:25mm;'),
        p('Atenciosamente,','text-indent:25mm;'),
        centro(`Assinado Digitalmente<br>${e(d.signatario)} - Escrevente`),
        '</section><section style="page-break-after:always;break-after:page">',
        '<table style="width:100%;border-collapse:collapse;border:0.5pt solid #000"><tbody><tr><td>',
        titulo('CONTRA-FÉ',11.04),
        p('Declaro que, nesta data de ____/____/_______, às ___________ horas, recebi o ofício retro.'),
        p('_________________________________________________.'),
        titulo('CERTIDÃO',11.04),
        p('Certifico e dou fé, na qualidade de Escrevente responsável pelas diligências da intimação retro, que:'),
        ...certidoes.map(s=>p(s)),
        p('(   ) Compareci no endereço indicado e <strong>deixei de intimar pessoalmente</strong> o(a) devedor(a); eis que evidenciado que o(a) mesmo(a) encontra-se em local ignorado ou incerto; isto depois de frustradas 03 (três) tentativas feitas nos seguintes dias e horários alternados: 1ª tentativa: dia ___/___/_____, às'),
        '</td></tr></tbody></table></section><section>',
        '<table style="width:100%;border-collapse:collapse;border:0.5pt solid #000"><tbody><tr><td>',
        p('___:___ horas; 2ª tentativa: dia ___/___/_____, às ___:___ horas; 3ª tentativa: dia ___/___/_____, às ___:___ horas.'),
        p('Concluída a(s) diligência(s), devolvo a presente documentação ao Escrevente encarregado do procedimento de intimação.'),
        centro('Morrinhos-GO, ___ de _______________ de _____.<br><br>________________________________<br>Escrevente'),
        '</td></tr><tr><td><strong>Endereço para notificação:</strong><br>',
        d.enderecos.map((s,i)=>`${i+1}) ${e(s)}.`).join('<br>'),
        '</td></tr><tr><td style="height:135mm;vertical-align:top">',
        centro('<strong style="font-size:12pt"><u>OBSERVAÇÕES:</u></strong>'),
        '</td></tr></tbody></table></section>',
    ].join(''),9.96,1.3253,3);
}

export function gerarConvocacao(d) {
    return moldura([
        titulo('CONVOCAÇÃO',15),
        p('Ilmo(a) Sr(a).'),
        p(`<strong>${alvo(d)}</strong>`),
        p(`Pelo presente, após tentativa pessoal em seu domicílio, convoco V.S.ª a comparecer neste Cartório, no endereço Rua Maestro Vicente José Vieira, 706, Loja 01, centro, CEP: 75.650-082, no período de 08:00 às 17:00 horas, a fim de tratar de assunto de seu interesse relacionado ao ${e(d.titulo)} n.º ${e(d.contrato)}, datado de ${e(d.dataContrato)}, registrado sob o ${e(d.registro)}, na Matrícula n.º ${e(d.matricula)}, deste Cartório, referente ao imóvel situado na ${e(d.enderecoImovel)}.`,'margin-top:32pt;'),
        centro('Atenciosamente,'),
        centro(`Assinado Digitalmente<br>${e(d.signatario)} - Escrevente`),
    ].join(''),12,1.15,13.8);
}
