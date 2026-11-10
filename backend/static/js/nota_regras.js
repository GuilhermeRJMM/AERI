export function perfisDoTitulo(titulo,regras) {
    const normal = t => ` ${String(t||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim()} `;
    const texto=normal(titulo);
    return (regras?.perfis||[]).filter(p=>p.termos.some(termo=>texto.includes(normal(termo))));
}

export function pertinenteAoTitulo(item,perfis) {
    return !perfis.length || (item.contextos||[]).includes('*')
        || perfis.some(p=>(item.contextos||[]).includes(p.id));
}

export function numeroDigitado(valor) {
    if (/^[0-9]{0,12}$/.test(valor)) return valor;
    if (/^[0-9]{1,3}(?:\.[0-9]{3})+$/.test(valor) && valor.replace(/\./g,'').length<=12)
        return valor.replace(/\./g,'');
    return null;
}

export function listaMatriculas(valor) {
    if (Array.isArray(valor)) return valor.length ? [...valor] : [''];
    if (!valor) return [''];
    return String(valor).split(/\s+e\s+|\s*[,;]\s*/).map(v=>numeroDigitado(v.trim())??'');
}
