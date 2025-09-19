(function () {
  const qs = new URLSearchParams(window.location.search);
  const redirectTo = qs.get('redirect') || '/web/search.html';

  const statusEl = document.getElementById('login-status');
  const googleBtn = document.getElementById('btn-google');
  const anonymousBtn = document.getElementById('btn-anonymous');

  const setButtonsDisabled = (disabled) => {
    [googleBtn, anonymousBtn].forEach((btn) => {
      if (!btn) return;
      btn.disabled = disabled;
      btn.setAttribute('aria-disabled', String(disabled));
    });
  };

  const showStatus = (message, isError) => {
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.classList.toggle('text-rose-500', !!isError);
    statusEl.classList.toggle('text-slate-500', !isError);
  };

  const errorMessage = (err) => {
    if (!err) return '不明なエラーが発生しました。';
    if (err.code === 'auth/popup-closed-by-user') return 'ポップアップが閉じられました。もう一度お試しください。';
    if (err.code === 'auth/cancelled-popup-request') return '別のポップアップ処理が進行中です。数秒後に再度お試しください。';
    if (err.code === 'auth/operation-not-allowed') return 'Firebase コンソールで対象のサインイン方法を有効化してください。';
    return err.message || String(err);
  };

  const goNext = () => {
    window.location.href = redirectTo;
  };

  const waitForHelper = () => new Promise((resolve, reject) => {
    const existing = window.firebaseAuthHelper;
    if (existing && existing.auth) {
      resolve(existing);
      return;
    }
    const onReady = (ev) => {
      cleanup();
      if (ev && ev.detail && ev.detail.helper && ev.detail.helper.auth) {
        resolve(ev.detail.helper);
      } else if (window.firebaseAuthHelper && window.firebaseAuthHelper.auth) {
        resolve(window.firebaseAuthHelper);
      } else {
        reject(new Error(window.firebaseInitError || 'Firebase の初期化に失敗しました。設定を確認してください。'));
      }
    };
    const checkError = () => {
      if (window.firebaseAuthHelper && window.firebaseAuthHelper.auth) {
        cleanup();
        resolve(window.firebaseAuthHelper);
        return;
      }
      if (window.firebaseInitError) {
        cleanup();
        reject(new Error(window.firebaseInitError));
      }
    };
    const cleanup = () => {
      document.removeEventListener('firebase-auth-ready', onReady);
      clearInterval(intervalId);
      clearTimeout(timeoutId);
    };
    document.addEventListener('firebase-auth-ready', onReady);
    const intervalId = setInterval(checkError, 200);
    const timeoutId = setTimeout(() => {
      cleanup();
      if (window.firebaseAuthHelper && window.firebaseAuthHelper.auth) {
        resolve(window.firebaseAuthHelper);
      } else {
        reject(new Error(window.firebaseInitError || 'Firebase の初期化がタイムアウトしました。'));
      }
    }, 5000);
  });

  const boot = async () => {
    showStatus('Firebase を初期化しています…', false);
    setButtonsDisabled(true);
    try {
      const helper = await waitForHelper();
      showStatus('ログイン方法を選択してください。', false);
      setButtonsDisabled(false);

      let hasNavigated = false;
      let anonymousFlowActive = false;
      let clearingAnonymousSession = false;

      helper.auth.onAuthStateChanged((user) => {
        if (hasNavigated) return;
        if (user) {
          if (user.isAnonymous && !anonymousFlowActive) {
            if (!clearingAnonymousSession) {
              clearingAnonymousSession = true;
              helper.signOut().finally(() => {
                clearingAnonymousSession = false;
                setButtonsDisabled(false);
                showStatus('ゲストとして利用するには下のボタンを押してください。', false);
              });
            }
            return;
          }
          setButtonsDisabled(true);
          const message = user.isAnonymous
            ? 'ゲストとしてログインしました。ページへ移動します…'
            : 'ログインに成功しました。ページへ移動します…';
          showStatus(message, false);
          hasNavigated = true;
          setTimeout(goNext, 600);
        } else {
          setButtonsDisabled(false);
          showStatus('ログイン方法を選択してください。', false);
        }
      });

      googleBtn?.addEventListener('click', async () => {
        setButtonsDisabled(true);
        showStatus('Google で認証中です…', false);
        try {
          const user = await helper.signInWithGoogle({ usePopup: true });
          if (!user) {
            // リダイレクトフロー
            showStatus('Google の認証ページへ移動します…', false);
          }
        } catch (err) {
          console.error('[login] Google sign-in failed', err);
          showStatus(errorMessage(err), true);
          setButtonsDisabled(false);
        }
      });

      anonymousBtn?.addEventListener('click', async () => {
        setButtonsDisabled(true);
        showStatus('ゲストとしてログイン中です…', false);
        anonymousFlowActive = true;
        try {
          await helper.signInAnonymously();
          showStatus('ゲストとしてログインしました。ページへ移動します…', false);
        } catch (err) {
          console.error('[login] Anonymous sign-in failed', err);
          showStatus(errorMessage(err), true);
        } finally {
          if (!hasNavigated) {
            anonymousFlowActive = false;
            setButtonsDisabled(false);
          }
        }
      });
    } catch (err) {
      console.error('[login] Firebase helper wait failed', err);
      showStatus(err.message || 'Firebase の初期化に失敗しました。設定を確認してください。', true);
      setButtonsDisabled(true);
    }
  };

  document.addEventListener('DOMContentLoaded', boot);
})();
