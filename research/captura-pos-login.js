// Captura de sessão pós-login — rodar via `maestri portal evaluate "PDPJ" "<este conteudo>"`
// DEPOIS que o titular completar o login e a página estiver autenticada em
// portaldeservicos.pdpj.jus.br. Não roda nada sozinho; só instala o hook e lê o
// que o app já guardou. Nenhuma credencial é enviada por este script.
//
// Passo 1 (este arquivo): instala o hook e tenta ler o Bearer já presente.
// Passo 2 (o Maestro dispara): com o Bearer, testa a API autenticada H1/H2.

(function () {
  if (window.__trtCap) return JSON.stringify({ status: 'ja instalado', achado: window.__trtBearer ? 'bearer em memoria' : 'sem bearer ainda' });
  window.__trtCap = true;
  window.__trtBearer = null;
  window.__trtReq = [];

  function guarda(v) {
    try {
      if (v && /^bearer\s+/i.test(v)) window.__trtBearer = v.replace(/^bearer\s+/i, '').trim();
    } catch (e) {}
  }

  // Hook em fetch: captura Authorization das chamadas que o app fizer daqui pra frente.
  var of = window.fetch;
  window.fetch = function (input, init) {
    try {
      var h = (init && init.headers) || (input && input.headers);
      if (h) {
        if (h.get) guarda(h.get('authorization') || h.get('Authorization'));
        else guarda(h['authorization'] || h['Authorization']);
      }
      var u = (typeof input === 'string') ? input : (input && input.url);
      if (u && String(u).indexOf('/api/') > -1) window.__trtReq.push(String(u));
    } catch (e) {}
    return of.apply(this, arguments);
  };
  var oo = XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.setRequestHeader = function (k, v) {
    try { if (String(k).toLowerCase() === 'authorization') guarda(v); } catch (e) {}
    return oo.apply(this, arguments);
  };

  // Tenta achar o token já guardado pelo Keycloak (storage) sem esperar chamada nova.
  function varreStorage(store) {
    try {
      for (var i = 0; i < store.length; i++) {
        var chave = store.key(i);
        var val = store.getItem(chave);
        if (!val) continue;
        // Keycloak costuma guardar { token, refreshToken } ou um JWT cru.
        if (/^ey[A-Za-z0-9_-]+\.ey/.test(val)) { guarda('Bearer ' + val); return chave; }
        try {
          var obj = JSON.parse(val);
          if (obj && obj.token && /^ey/.test(obj.token)) { guarda('Bearer ' + obj.token); return chave; }
          if (obj && obj.access_token && /^ey/.test(obj.access_token)) { guarda('Bearer ' + obj.access_token); return chave; }
        } catch (e) {}
      }
    } catch (e) {}
    return null;
  }

  var origem = varreStorage(window.localStorage) || varreStorage(window.sessionStorage);

  return JSON.stringify({
    status: 'hook instalado',
    bearer_encontrado: !!window.__trtBearer,
    origem_storage: origem,
    url: location.href
  });
})();
