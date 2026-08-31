// Teste PostgreSQL isolado em memória. Não lê .env nem conecta ao banco real.
import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const {PGlite}=await import('../tmp/teste-postgres/node_modules/@electric-sql/pglite/dist/index.js');
const db=new PGlite();
await db.exec(`CREATE TABLE usuarios_aeri(usuario VARCHAR(80) PRIMARY KEY,perfil VARCHAR(30),
 CONSTRAINT usuarios_aeri_perfil_valido CHECK(perfil IN ('ADMIN','SUPERVISOR','CONFERENTE','AUDITOR')));
 INSERT INTO usuarios_aeri VALUES('ADMIN','ADMIN'),('SUP','SUPERVISOR'),('COMUM','CONFERENTE'),('AUD','AUDITOR');`);
const ler=nome=>readFile(new URL('../backend/app/migrations/'+nome,import.meta.url),'utf8');
await db.exec((await ler('038_permissoes_relacionais.sql')).split('INSERT INTO usuarios_permissoes_aeri')[0]);
await db.exec(`INSERT INTO perfis_permissoes_aeri VALUES('CONFERENTE','acessar_buscas');
 INSERT INTO usuarios_permissoes_aeri(usuario,permissao,concedida) VALUES('SUP','acessar_buscas',TRUE);`);
await db.exec(await ler('041_setores_e_paineis.sql'));
await db.exec(await ler('042_contratos_minutas.sql'));
const backup=(await db.query("SELECT * FROM backups_acessos_aeri WHERE versao='antes_setores_20260831'")).rows[0];
assert.equal(backup.cargos.length,4);
assert.equal(backup.concessoes.length,1);
assert.equal(backup.concessoes[0].permissao,'acessar_buscas');
assert(!backup.catalogo.some(p=>p.chave==='acessar_contratos'),'fotografia deve anteceder a migração');
assert(!JSON.stringify(backup).includes('senha_hash'),'não copiar credenciais');
const permissoes=async usuario=>(await db.query(`SELECT (
 COALESCE((SELECT jsonb_object_agg(permissao,TRUE) FROM perfis_permissoes_aeri WHERE perfil=u.perfil),'{}'::jsonb)
 || COALESCE((SELECT jsonb_object_agg(permissao,concedida) FROM usuarios_permissoes_aeri WHERE usuario=u.usuario),'{}'::jsonb)
 ) AS p FROM usuarios_aeri u WHERE usuario=$1`,[usuario])).rows[0].p;
assert.equal((await permissoes('SUP')).acessar_buscas,true);
assert.equal((await permissoes('SUP')).acessar_certidao,true);
assert.equal((await permissoes('SUP')).acessar_contratos,false,'não ampliar supervisor antigo');
assert.equal((await permissoes('COMUM')).acessar_certidao,true,'preservar acesso herdado antigo');
await db.exec(`INSERT INTO usuarios_aeri VALUES('NOVO_SUP','SUPERVISOR'),('NOVO','USUARIO');`);
assert.equal((await permissoes('NOVO_SUP')).acessar_contratos,true);
assert.equal((await permissoes('NOVO_SUP')).ver_intimacoes,undefined);
assert.deepEqual(await permissoes('NOVO'),{});
await db.exec(`INSERT INTO usuarios_permissoes_aeri(usuario,permissao,concedida) VALUES('NOVO_SUP','acessar_contratos',FALSE);`);
assert.equal((await permissoes('NOVO_SUP')).acessar_contratos,false);
await db.exec(`INSERT INTO contratos_trabalhos_aeri(id,usuario,protocolo,documento_id)
 VALUES('11111111-1111-1111-1111-111111111111','NOVO','999999','1');`);
const r=await db.query(`INSERT INTO contratos_trabalhos_aeri(id,usuario,protocolo,documento_id)
 VALUES('22222222-2222-2222-2222-222222222222','NOVO','999999','1')
 ON CONFLICT (usuario,protocolo,documento_id) WHERE estado IN ('AGUARDANDO','PROCESSANDO')
 DO UPDATE SET atualizado_em=contratos_trabalhos_aeri.atualizado_em RETURNING id`);
assert.equal(r.rows[0].id,'11111111-1111-1111-1111-111111111111');
const fila=await db.query(`SELECT * FROM contratos_trabalhos_aeri WHERE estado='AGUARDANDO'
 OR (estado='PROCESSANDO' AND trava_ate<NOW()) ORDER BY criado_em FOR UPDATE SKIP LOCKED LIMIT 1`);
assert.equal(fila.rows.length,1);
const agendas=await db.query('SELECT * FROM automacoes_operacionais_aeri');
assert.equal(agendas.rows.length,2);
assert(agendas.rows.every(a=>a.habilitada===false));
await db.close();
console.log('Migrações, defaults, acessos herdados, negação individual e deduplicação da fila: OK (PostgreSQL isolado).');
