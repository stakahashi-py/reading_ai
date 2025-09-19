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
      window.firebaseInitError = 'Firebase SDK が読み込まれていません。ネットワークやアドブロッカーをご確認ください。';
      return;
    }
    const cfg = await loadConfig();
    if (!cfg) {
      console.error('[auth] Firebase config not found');
      window.firebaseInitError = 'Firebase 設定ファイルが取得できません。ファイルの配置とパスを確認してください。';
      return;
    }
    try {
      if (!firebase.apps.length) firebase.initializeApp(cfg);
    } catch (e) {
      console.error('[auth] Firebase initializeApp failed', e);
      window.firebaseInitError = `Firebase 初期化時にエラーが発生しました: ${e && e.message ? e.message : e}`;
      return;
    }
    window.firebaseInitError = null;
    const auth = firebase.auth();

    // Auth mode: 'auto' (default) | 'anonymous' | 'google' | 'manual'
    // - auto: try anonymous; if disallowed, fallback to Google redirect
    // - manual: expose helper functions but skip automatic sign-in
    const elCfg = document.getElementById('firebase-config');
    const dataAttrMode = elCfg && elCfg.getAttribute('data-auth-mode');
    const rawMode = (window.AUTH_MODE || dataAttrMode || 'auto').toLowerCase();
    const MODE = ['auto', 'anonymous', 'google', 'manual'].includes(rawMode) ? rawMode : 'auto';

    const onceAuthState = () => new Promise((resolve) => {
      const off = auth.onAuthStateChanged((u) => { off(); resolve(u); });
    });

    const waitForUser = () => new Promise((resolve) => {
      const existing = auth.currentUser;
      if (existing) {
        resolve(existing);
        return;
      }
      const off = auth.onAuthStateChanged((u) => {
        if (u) {
          off();
          resolve(u);
        }
      });
    });

    const signInWithGoogle = async ({ usePopup = false } = {}) => {
      const provider = new firebase.auth.GoogleAuthProvider();
      if (usePopup && auth.signInWithPopup) {
        try {
          const res = await auth.signInWithPopup(provider);
          return res.user;
        } catch (e) {
          if (e && (e.code === 'auth/popup-blocked' || e.code === 'auth/operation-not-supported-in-this-environment')) {
            // ブロックされた場合のみリダイレクトにフォールバック
            await auth.signInWithRedirect(provider);
            return null;
          }
          throw e;
        }
      }
      await auth.signInWithRedirect(provider);
      return null;
    };

    const signInAnonymously = async () => {
      await auth.signInAnonymously();
      return await waitForUser();
    };

    const ensureSignedIn = async () => {
      const current = auth.currentUser || await onceAuthState();
      if (current) return current;

      if (MODE === 'manual') {
        return null;
      }

      if (MODE === 'google') {
        try {
          await signInWithGoogle({ usePopup: false });
          return await waitForUser();
        } catch (e) {
          console.error('[auth] Google sign-in redirect failed:', e);
          return null;
        }
      }

      // anonymous or auto
      try {
        await signInAnonymously();
        return await waitForUser();
      } catch (e) {
        // Anonymous disabled → fallback to Google on auto
        if (MODE === 'auto' && (e && (e.code === 'auth/operation-not-allowed' || e.code === 'auth/admin-restricted-operation'))) {
          try {
            await signInWithGoogle({ usePopup: false });
            return await waitForUser();
          } catch (ge) {
            console.error('[auth] Google sign-in redirect failed:', ge);
            return null;
          }
        }
        console.warn('[auth] Anonymous sign-in failed:', e);
        return null;
      }
    };

    if (MODE !== 'manual') {
      await ensureSignedIn();
    }

    // Expose a promise for readiness
    window.firebaseReady = waitForUser();

    const helper = window.firebaseAuthHelper || {};
    helper.mode = MODE;
    helper.auth = auth;
    helper.ensureSignedIn = ensureSignedIn;
    helper.signInWithGoogle = signInWithGoogle;
    helper.signInAnonymously = signInAnonymously;
    helper.waitForUser = waitForUser;
    helper.onceAuthState = onceAuthState;
    helper.signOut = () => auth.signOut();
    helper.getIdToken = async (forceRefresh = false) => {
      const user = auth.currentUser || await waitForUser();
      return user ? await user.getIdToken(forceRefresh) : null;
    };
    helper.getConfig = () => cfg;
    window.firebaseAuthHelper = helper;
    try {
      document.dispatchEvent(new CustomEvent('firebase-auth-ready', { detail: { helper } }));
    } catch (_) {}

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
