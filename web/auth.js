// Minimal Firebase Auth bootstrap and fetch interceptor
// - Loads config from one of:
//   1) <script id="firebase-config">...</script> JSON
//   2) /web/firebase-config.json
//   3) /firebase-config.json
// - Signs in anonymously (if not already signed in)
// - Attaches ID token to Authorization header for all requests to /v1/*

(function(){
  const loadConfig = async () => {
    try {
      const el = document.getElementById('firebase-config');
      if (el && el.textContent) {
        return JSON.parse(el.textContent);
      }
    } catch (_) {}
    const tryFetch = async (url) => {
      try {
        const r = await fetch(url, {cache: 'no-store'});
        if (r.ok) return await r.json();
      } catch (_) {}
      return null;
    };
    return (await tryFetch('/web/firebase-config.json'))
        || (await tryFetch('/firebase-config.json'))
        || null;
  };

  const init = async () => {
    if (!(window.firebase && firebase.app)) {
      console.error('[auth] Firebase SDK not loaded');
      return;
    }
    const cfg = await loadConfig();
    if (!cfg) {
      console.error('[auth] Firebase config not found');
      return;
    }
    if (!firebase.apps.length) firebase.initializeApp(cfg);
    const auth = firebase.auth();

    // Ensure a user session (anonymous by default)
    try {
      await new Promise((resolve) => {
        const unsub = auth.onAuthStateChanged(async (u) => {
          unsub();
          if (!u) {
            try { await auth.signInAnonymously(); } catch(_) {}
          }
          resolve();
        });
      });
    } catch(_) {}

    // Expose a promise for readiness
    window.firebaseReady = (async () => {
      return await new Promise((resolve) => {
        const off = auth.onAuthStateChanged((u) => { off(); resolve(u); });
      });
    })();

    // Wrap fetch to attach ID token for API calls
    const origFetch = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      const url = (typeof input === 'string') ? input : (input && input.url) || '';
      init = init || {};
      // Only attach for relative /v1/* or */v1/* on same origin
      const attach = url.startsWith('/v1/') || (url.includes('/v1/') && !/^https?:\/\//.test(url));
      if (attach) {
        try {
          const user = firebase.auth().currentUser || await window.firebaseReady;
          const token = user ? await user.getIdToken(/* forceRefresh= */ false) : null;
          const headers = new Headers(init.headers || {});
          if (token) headers.set('Authorization', 'Bearer ' + token);
          // Preserve caller-provided headers, but don't force Content-Type on GET
          if (!headers.has('Content-Type') && (!init.method || init.method.toUpperCase() !== 'GET')) {
            headers.set('Content-Type', 'application/json');
          }
          init.headers = headers;
        } catch(_) {}
      }
      return origFetch(input, init);
    };
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

