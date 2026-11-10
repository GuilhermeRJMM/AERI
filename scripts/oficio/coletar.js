// Executado apenas na aba já preparada pelo operador. Não abre IN nem mensagem.
async (config) => {
    const falha = codigo => ({erro:codigo});
    const hosts = ['oficioeletronico.com.br', 'www.oficioeletronico.com.br'];
    if (location.protocol !== 'https:' || !hosts.includes(location.hostname)
        || location.pathname !== '/Cartorios/Intimacoes') return falha('pagina_incorreta');
    if (document.getElementById('filterCartorio')?.value !== config.cartorio)
        return falha('cartorio_diferente');
    for (const id of ['filterProtocolo','filterDataPedidoDe','filterDataPedidoAte',
        'filterPrenotacao','filterEmolumentos','filterSolicitante']) {
        const campo = document.getElementById(id);
        if (!campo || campo.value.trim()) return {erro:'filtro_ativo_ou_desconhecido',campo:id,presente:Boolean(campo)};
    }
    // Confirmado na listagem real: o portal referencia esse filtro no JS,
    // mas não o renderiza para esta serventia. Ausência não é filtro ativo.
    const edital = document.getElementById('filterAptoEdital');
    if (edital && edital.value.trim()) return {erro:'filtro_ativo_ou_desconhecido',campo:'filterAptoEdital',presente:true};
    for (const id of ['filterStatus','filterIsencao','filterNotificadoPorE-mail']) {
        if (document.getElementById(id)?.value !== '-1') return {erro:'filtro_ativo_ou_desconhecido',campo:id,presente:Boolean(document.getElementById(id))};
    }
    const itens = [], paginas = [], vistos = new Set();
    const inicio = new Date().toISOString();
    let totalPaginas = 1, totalEsperado = config.total ?? null;
    function dataIso(texto) {
        if (['', '-', '—'].includes(texto)) return null;
        const m = texto.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
        if (!m) throw new Error('data_nao_reconhecida');
        return `${m[3]}-${m[2]}-${m[1]}`;
    }
    try {
        for (let pagina = 1; pagina <= totalPaginas; pagina++) {
            let d = document;
            if (pagina > 1) {
                // Única requisição permitida pelo coletor: paginação da listagem.
                const r = await fetch('/Cartorios/Intimacoes?page=' + pagina, {
                    method:'POST', credentials:'same-origin', redirect:'error', cache:'no-store',
                    headers:{'X-Requested-With':'XMLHttpRequest'}, signal:AbortSignal.timeout(15000),
                });
                if (!r.ok) return falha('falha_na_paginacao');
                const texto = await r.text();
                if (texto.length > 5000000) return falha('resposta_excede_limite');
                d = new DOMParser().parseFromString(texto, 'text/html');
            }
            // Resposta de outro contexto/cartório (ou login expirado) é recusada.
            const js = [...d.scripts].filter(s => !s.src).map(s => s.textContent).join('\n');
            const ids = [...new Set([...js.matchAll(/DisableDropConditional\(\s*['"]filterCartorio['"]\s*,\s*(\d+)\s*\)/g)].map(m => m[1]))];
            if (ids.length !== 1 || ids[0] !== config.cartorio) return falha('cartorio_nao_confirmado');
            const info = d.querySelector('.default-pagination')?.textContent.replace(/\s+/g, ' ') || '';
            const m = info.match(/(\d+)\s*Itens\s*Página\s*(\d+)\s*de\s*(\d+)/i);
            if (!m || Number(m[2]) !== pagina || Number(m[1]) < (config.minimo || 1) || Number(m[1]) > 2000)
                return falha('total_ou_pagina_divergente');
            if (pagina === 1) { totalPaginas = Number(m[3]); totalEsperado ??= Number(m[1]); }
            if (Number(m[1]) !== totalEsperado) return falha('total_ou_pagina_divergente');
            if (!totalPaginas || totalPaginas > 100 || Number(m[3]) !== totalPaginas)
                return falha('paginacao_divergente');
            const tabelas = [...d.querySelectorAll('table')].filter(t =>
                [...t.querySelectorAll('th')].some(e => e.textContent.trim() === 'Protocolo'));
            if (tabelas.length !== 1) return falha('tabela_nao_confirmada');
            const tabela = tabelas[0], hs = [...tabela.querySelectorAll('th')].map(e => e.textContent.trim());
            const campos = ['Protocolo','Prenotação','Status','Data Status','Data Pedido','Prazo da Purga'];
            if (campos.some(c => hs.filter(h => h === c).length !== 1)) return falha('colunas_alteradas');
            let quantidade = 0;
            for (const linha of tabela.querySelectorAll('tbody tr')) {
                const cs = [...linha.children].filter(e => e.tagName === 'TD');
                if (cs.length !== hs.length) return falha('linha_incompleta');
                const celula = nome => cs[hs.indexOf(nome)].textContent.trim().replace(/\s+/g, ' ');
                const protocolo = celula('Protocolo');
                if (!/^IN\d{8}[A-Z]$/.test(protocolo) || vistos.has(protocolo)) return falha('in_invalido_ou_duplicado');
                vistos.add(protocolo);
                const prenotacao = celula('Prenotação');
                itens.push({protocolo, prenotacao:['','-','—'].includes(prenotacao) ? '' : prenotacao,
                    status:celula('Status'), dataStatus:dataIso(celula('Data Status')),
                    dataPedido:dataIso(celula('Data Pedido')), prazoPurga:celula('Prazo da Purga')});
                quantidade++;
            }
            if (quantidade < 1 || quantidade > 10 || (pagina < totalPaginas && quantidade !== 10))
                return falha('quantidade_por_pagina_divergente');
            paginas.push({pagina,itens:quantidade});
            if (pagina < totalPaginas) await new Promise(r => setTimeout(r, 400));
        }
        if (itens.length !== totalEsperado) return falha('consulta_incompleta');
        return {versao:1, fonte:'oficioeletronico.com.br', cartorio:config.cartorio,
            consultadoEm:inicio, completo:true, total:totalEsperado, paginas, itens};
    } catch (_) {
        // Nunca retornar HTML, conteúdo de exceções, cabeçalhos ou dados de sessão.
        return falha('consulta_interrompida');
    }
}
