export function escaparHtml(valor) {
    return String(valor).replace(/[&<>'"]/g, caractere => (
        {'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[caractere]
    ));
}

export function hojeLocal() {
    const agora = new Date();
    const ano = agora.getFullYear();
    const mes = String(agora.getMonth() + 1).padStart(2, '0');
    const dia = String(agora.getDate()).padStart(2, '0');
    return `${ano}-${mes}-${dia}`;
}

export function baixarArquivo(conteudo, tipo, nome) {
    const blob = new Blob([conteudo], {type: tipo});
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = nome;
    link.click();
    URL.revokeObjectURL(link.href);
}
