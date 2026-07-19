import { setCsrfToken } from "./api.js";

export function initAuth({ api, openModal, closeModal, onAuthenticated }) {
  const gate = document.querySelector("#auth-gate");
  const loginForm = document.querySelector("#login-form");
  const loginError = document.querySelector("#login-error");
  const userList = document.querySelector("#user-list");
  const userListError = document.querySelector("#user-list-error");
  let passwordChangeRequired = false;

  const formatCreatedAt = (timestamp) => {
    if (!timestamp) return "未知时间";
    return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" })
      .format(new Date(Number(timestamp) * 1000));
  };
  const renderUsers = (users) => {
    if (!userList) return;
    userList.replaceChildren();
    if (!users.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "暂无用户";
      userList.append(empty);
      return;
    }
    users.forEach((user) => {
      const item = document.createElement("div");
      item.className = "user-list-item";
      const name = document.createElement("strong");
      name.textContent = user.username;
      const meta = document.createElement("span");
      meta.textContent = `管理员 · 创建于 ${formatCreatedAt(user.created_at)}`;
      item.append(name, meta);
      userList.append(item);
    });
  };
  const loadUsers = async () => {
    if (userListError) userListError.textContent = "";
    try {
      const data = await api("GET", "/api/auth/users");
      renderUsers(data.users || []);
    } catch (error) {
      if (userListError) userListError.textContent = error.message || "加载用户列表失败";
    }
  };
  const openUserCreate = () => {
    const form = document.querySelector("#user-create-form");
    form?.reset();
    const password = document.querySelector("#new-password");
    const toggle = document.querySelector("#btn-toggle-new-password");
    if (password) password.type = "password";
    if (toggle) {
      toggle.textContent = "显示";
      toggle.setAttribute("aria-label", "显示密码");
      toggle.setAttribute("aria-pressed", "false");
    }
    document.querySelector("#user-create-error").textContent = "";
    openModal("modal-user-create");
  };
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
  document.querySelector("#btn-user-manage")?.addEventListener("click", async () => {
    openModal("modal-user-manage");
    await loadUsers();
  });
  document.querySelector("#btn-reload-users")?.addEventListener("click", loadUsers);
  document.querySelector("#btn-open-user-create")?.addEventListener("click", openUserCreate);
  document.querySelector("#btn-toggle-new-password")?.addEventListener("click", () => {
    const password = document.querySelector("#new-password");
    const toggle = document.querySelector("#btn-toggle-new-password");
    const visible = password.type === "password";
    password.type = visible ? "text" : "password";
    toggle.textContent = visible ? "隐藏" : "显示";
    toggle.setAttribute("aria-label", visible ? "隐藏密码" : "显示密码");
    toggle.setAttribute("aria-pressed", String(visible));
  });
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
      await loadUsers();
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
