import { setCsrfToken } from "./api.js";

export function initAuth({ api, openModal, closeModal, onAuthenticated }) {
  const gate = document.querySelector("#auth-gate");
  const loginForm = document.querySelector("#login-form");
  const loginError = document.querySelector("#login-error");
  let passwordChangeRequired = false;
  const showLogin = () => {
    document.body.classList.add("auth-required");
    gate.hidden = false;
    loginError.textContent = "";
    document.querySelector("#login-password").value = "";
  };
  const setAuthenticated = (data) => {
    setCsrfToken(data.csrf_token);
    document.body.classList.remove("auth-required");
    gate.hidden = true;
    document.querySelector("#auth-user").textContent = data.user.username;
    passwordChangeRequired = Boolean(data.user.must_change_password);
  };
  loginForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    loginError.textContent = "";
    try {
      const data = await api("POST", "/api/auth/login", {
        username: document.querySelector("#login-username").value,
        password: document.querySelector("#login-password").value,
      });
      setAuthenticated(data);
      if (passwordChangeRequired) openModal("modal-password-change");
      else await onAuthenticated();
    } catch (error) {
      loginError.textContent = error.message || "登录失败";
    }
  });
  document.querySelector("#btn-logout")?.addEventListener("click", async () => {
    try { await api("POST", "/api/auth/logout", {}); } catch { /* Session may already be gone. */ }
    setCsrfToken("");
    showLogin();
  });
  document.querySelector("#btn-user-manage")?.addEventListener("click", () => openModal("modal-user-create"));
  document.querySelector("#user-create-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const error = document.querySelector("#user-create-error");
    error.textContent = "";
    try {
      await api("POST", "/api/auth/users", {
        username: document.querySelector("#new-username").value,
        password: document.querySelector("#new-password").value,
      });
      event.target.reset();
      closeModal("modal-user-create");
    } catch (err) {
      error.textContent = err.message || "创建用户失败";
    }
  });
  document.querySelector("#password-change-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const error = document.querySelector("#password-change-error");
    error.textContent = "";
    try {
      await api("POST", "/api/auth/password", {
        old_password: document.querySelector("#current-password").value,
        new_password: document.querySelector("#replacement-password").value,
      });
      passwordChangeRequired = false;
      event.target.reset();
      closeModal("modal-password-change");
      await onAuthenticated();
    } catch (err) {
      error.textContent = err.message || "修改密码失败";
    }
  });
  return { showLogin, setAuthenticated };
}
