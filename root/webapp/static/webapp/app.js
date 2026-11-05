/* EslatBot Mini App — bir sahifali ilova (vanilla JS, build kerak emas) */
(function () {
  "use strict";

  const tg = window.Telegram && window.Telegram.WebApp;
  const view = document.getElementById("view");
  const tabbar = document.getElementById("tabbar");
  const fab = document.getElementById("fab");

  // --- Telegram init ---
  if (tg) {
    tg.ready();
    tg.expand();
    try { tg.setHeaderColor("secondary_bg_color"); } catch (e) {}
    try { tg.enableClosingConfirmation && tg.enableClosingConfirmation(); } catch (e) {}
  }

  const INIT = tg ? tg.initData : "";

  // ===== Yordamchilar =====
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function haptic(type) {
    try {
      if (!tg || !tg.HapticFeedback) return;
      if (type === "success" || type === "error" || type === "warning")
        tg.HapticFeedback.notificationOccurred(type);
      else tg.HapticFeedback.impactOccurred(type || "light");
    } catch (e) {}
  }
  function confirmDel(msg, cb) {
    if (tg && tg.showConfirm) tg.showConfirm(msg, (ok) => ok && cb());
    else if (window.confirm(msg)) cb();
  }
  function toast(msg) {
    if (tg && tg.showPopup) { try { tg.showPopup({ message: msg }); return; } catch (e) {} }
    alert(msg);
  }

  async function api(method, path, body) {
    const opts = {
      method,
      headers: {
        "Authorization": "tma " + INIT,
        "Content-Type": "application/json",
      },
    };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch("/app/api/" + path, opts);
    let data = {};
    try { data = await res.json(); } catch (e) {}
    if (!res.ok || data.ok === false) {
      throw new Error(data.error || ("Xatolik (" + res.status + ")"));
    }
    return data;
  }

  function loading() { view.innerHTML = '<div class="spin">Yuklanmoqda…</div>'; }
  function errorView(msg) {
    view.innerHTML =
      '<div class="empty"><div class="ico">⚠️</div><div>' + esc(msg) +
      '</div><br><button class="btn ghost" onclick="location.reload()">Qayta urinish</button></div>';
  }
  function empty(ico, text) {
    return '<div class="empty"><div class="ico">' + ico + '</div>' + esc(text) + '</div>';
  }

  // ===== Bottom sheet (modal forma) =====
  function sheet(title, innerHTML, onMount) {
    const bg = document.createElement("div");
    bg.className = "sheet-bg";
    bg.innerHTML = '<div class="sheet"><h2>' + esc(title) + '</h2>' + innerHTML + '</div>';
    bg.addEventListener("click", (e) => { if (e.target === bg) close(); });
    function close() { bg.remove(); }
    document.body.appendChild(bg);
    if (onMount) onMount(bg.querySelector(".sheet"), close);
    return close;
  }

  // ===== Holat =====
  let currentTab = "home";
  let taskFilter = "open";
  let noteQuery = "";

  const TABS = {
    home: renderHome,
    reminders: renderReminders,
    tasks: renderTasks,
    notes: renderNotes,
    materials: renderMaterials,
    settings: renderSettings,
  };
  // Qaysi tablarda "+" tugma ko'rinadi va nimani ochadi
  const FAB_ACTIONS = {
    reminders: openReminderForm,
    tasks: openTaskForm,
    notes: openNoteForm,
    materials: openMaterialForm,
  };

  function setTab(name) {
    currentTab = name;
    tabbar.querySelectorAll("button").forEach((b) =>
      b.classList.toggle("active", b.dataset.tab === name));
    fab.classList.toggle("hidden", !FAB_ACTIONS[name]);
    window.scrollTo(0, 0);
    TABS[name]();
  }

  tabbar.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-tab]");
    if (b) { haptic("light"); setTab(b.dataset.tab); }
  });
  fab.addEventListener("click", () => {
    const fn = FAB_ACTIONS[currentTab];
    if (fn) { haptic("light"); fn(); }
  });

  // ===== Delegatsiya: kartalardagi amallar =====
  view.addEventListener("click", async (e) => {
    const t = e.target.closest("[data-action]");
    if (!t) return;
    const id = t.dataset.id;
    const action = t.dataset.action;
    try {
      if (action === "toggle-reminder") {
        haptic("light");
        await api("POST", "reminders/" + id, { action: "toggle" });
        renderReminders();
      } else if (action === "del-reminder") {
        confirmDel("Eslatma o'chirilsinmi?", async () => {
          await api("DELETE", "reminders/" + id); haptic("success"); renderReminders();
        });
      } else if (action === "toggle-task") {
        haptic("light");
        await api("POST", "tasks/" + id, { action: "toggle" });
        renderTasks();
      } else if (action === "del-task") {
        confirmDel("Vazifa o'chirilsinmi?", async () => {
          await api("DELETE", "tasks/" + id); haptic("success"); renderTasks();
        });
      } else if (action === "del-note") {
        confirmDel("Qayd o'chirilsinmi?", async () => {
          await api("DELETE", "notes/" + id); haptic("success"); renderNotes();
        });
      } else if (action === "mat-inc" || action === "mat-dec") {
        haptic("light");
        const cur = parseInt(t.dataset.cur || "0", 10);
        const next = action === "mat-inc" ? cur + 1 : Math.max(0, cur - 1);
        await api("POST", "materials/" + id, { current: next });
        renderMaterials();
      } else if (action === "mat-edit") {
        openMaterialEdit(JSON.parse(t.dataset.m));
      } else if (action === "del-material") {
        confirmDel("Material o'chirilsinmi?", async () => {
          await api("DELETE", "materials/" + id); haptic("success"); renderMaterials();
        });
      }
    } catch (err) { haptic("error"); toast(err.message); }
  });

  // ===== 🏠 Bosh sahifa =====
  async function renderHome() {
    loading();
    try {
      const d = await api("GET", "bootstrap");
      const c = d.counts;
      let html = '<div class="header"><h1>Assalomu alaykum, ' +
        esc(d.user.name) + '! 👋</h1><div class="sub">Bugungi holat</div></div>';

      html += '<div class="stat-grid">' +
        stat("accent", c.today, "Bugungi reja") +
        stat("green", c.reminders_active, "Faol eslatma") +
        stat("amber", c.tasks_open, "Ochiq vazifa") +
        stat("", c.habits_today, "Bugun bajarilgan odat") +
        '</div>';

      html += '<div class="section-title">📅 Bugungi reja</div>';
      if (d.today_plan.length === 0) {
        html += '<div class="card center muted">Bugunga reja yo\'q 🌿</div>';
      } else {
        html += d.today_plan.map((r) =>
          '<div class="card item"><div class="grow"><div class="title">' +
          esc(r.text) + '</div><div class="meta"><span class="badge">🕒 ' +
          r.time + '</span><span class="badge">' + esc(r.freq_label) +
          '</span></div></div></div>').join("");
      }
      view.innerHTML = html;
    } catch (err) { errorView(err.message); }
  }
  function stat(cls, val, lbl) {
    return '<div class="stat ' + cls + '"><div class="big">' + val +
      '</div><div class="lbl">' + esc(lbl) + '</div></div>';
  }

  // ===== 🔔 Eslatmalar =====
  async function renderReminders() {
    loading();
    try {
      const d = await api("GET", "reminders");
      let html = '<div class="header"><h1>🔔 Eslatmalar</h1></div>';
      if (d.items.length === 0) {
        html += empty("🔔", "Hali eslatma yo'q. Pastdagi + tugmasi bilan qo'shing.");
      } else {
        html += d.items.map(reminderCard).join("");
      }
      view.innerHTML = html;
    } catch (err) { errorView(err.message); }
  }
  function reminderCard(r) {
    const meta = ['<span class="badge">🕒 ' + r.time + '</span>',
      '<span class="badge">' + esc(r.freq_label) + '</span>'];
    if (r.weekday_label && r.freq === "weekly")
      meta.push('<span class="badge">' + esc(r.weekday_label) + '</span>');
    if (r.monthday && r.freq === "monthly")
      meta.push('<span class="badge">' + r.monthday + '-kun</span>');
    if (r.is_habit && r.streak)
      meta.push('<span class="badge streak">🔥 ' + r.streak + '</span>');
    if (!r.is_active) meta.push('<span class="badge off">⏸ To\'xtatilgan</span>');
    return '<div class="card"><div class="row between">' +
      '<div class="grow"><div class="title' + (r.is_active ? "" : " muted") + '">' +
      esc(r.text) + '</div><div class="meta">' + meta.join("") + '</div></div>' +
      '<label class="switch"><input type="checkbox" data-action="toggle-reminder" data-id="' +
      r.id + '"' + (r.is_active ? " checked" : "") + '><span class="track"></span><span class="knob"></span></label>' +
      '</div><div class="row" style="justify-content:flex-end;margin-top:8px">' +
      '<button class="iconbtn danger" data-action="del-reminder" data-id="' + r.id +
      '">🗑</button></div></div>';
  }

  function openReminderForm() {
    const html =
      '<label class="fld"><span class="cap">Eslatma matni</span>' +
      '<input type="text" id="r-text" placeholder="Masalan: Dori ichish" maxlength="1000"></label>' +
      '<label class="fld"><span class="cap">Takrorlanish</span>' +
      '<select id="r-freq">' +
      '<option value="daily">📅 Har kuni</option>' +
      '<option value="once">📌 Bir marta</option>' +
      '<option value="every2">🔁 Kun ora</option>' +
      '<option value="weekly">📆 Haftada bir</option>' +
      '<option value="monthly">🗓 Oyda bir</option></select></label>' +
      '<div id="r-extra"></div>' +
      '<label class="fld"><span class="cap">Vaqt</span>' +
      '<input type="time" id="r-time" value="09:00"></label>' +
      '<button class="btn block" id="r-save">Saqlash</button>';
    sheet("Yangi eslatma", html, (el, close) => {
      const freq = el.querySelector("#r-freq");
      const extra = el.querySelector("#r-extra");
      const days = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"];
      function renderExtra() {
        const f = freq.value;
        if (f === "weekly") {
          extra.innerHTML = '<label class="fld"><span class="cap">Hafta kuni</span><select id="r-wd">' +
            days.map((n, i) => '<option value="' + i + '">' + n + '</option>').join("") +
            '</select></label>';
        } else if (f === "monthly") {
          extra.innerHTML = '<label class="fld"><span class="cap">Oy kuni (1–31)</span>' +
            '<input type="number" id="r-md" min="1" max="31" value="1"></label>';
        } else if (f === "once") {
          const today = new Date().toISOString().slice(0, 10);
          extra.innerHTML = '<label class="fld"><span class="cap">Sana</span>' +
            '<input type="date" id="r-date" value="' + today + '"></label>';
        } else { extra.innerHTML = ""; }
      }
      freq.addEventListener("change", renderExtra);
      renderExtra();
      el.querySelector("#r-save").addEventListener("click", async () => {
        const text = el.querySelector("#r-text").value.trim();
        if (!text) { toast("Matnni yozing."); return; }
        const time = (el.querySelector("#r-time").value || "09:00").split(":");
        const payload = {
          text, freq: freq.value,
          hour: parseInt(time[0], 10), minute: parseInt(time[1], 10),
        };
        if (freq.value === "weekly") payload.weekday = parseInt(el.querySelector("#r-wd").value, 10);
        if (freq.value === "monthly") payload.monthday = parseInt(el.querySelector("#r-md").value, 10);
        if (freq.value === "once") payload.once_date = el.querySelector("#r-date").value;
        try {
          await api("POST", "reminders", payload);
          haptic("success"); close(); renderReminders();
        } catch (err) { haptic("error"); toast(err.message); }
      });
    });
  }

  // ===== ✅ Vazifalar =====
  async function renderTasks() {
    loading();
    try {
      const d = await api("GET", "tasks?filter=" + taskFilter);
      let html = '<div class="header"><h1>✅ Vazifalar</h1></div>';
      html += '<div class="filters">' +
        chip("open", "Ochiq") + chip("done", "Bajarilgan") + chip("all", "Hammasi") + '</div>';
      if (d.items.length === 0) {
        html += empty("✅", "Vazifa yo'q.");
      } else {
        html += d.items.map(taskCard).join("");
      }
      view.innerHTML = html;
      view.querySelectorAll(".chip").forEach((c) =>
        c.addEventListener("click", () => { taskFilter = c.dataset.f; renderTasks(); }));
    } catch (err) { errorView(err.message); }
  }
  function chip(f, label) {
    return '<button class="chip ' + (taskFilter === f ? "active" : "") +
      '" data-f="' + f + '">' + label + '</button>';
  }
  function taskCard(t) {
    const meta = ['<span class="badge">' + esc(t.priority_label) + '</span>'];
    if (t.due_date) meta.push('<span class="badge">📅 ' + esc(t.due_date) + '</span>');
    return '<div class="card item">' +
      '<button class="iconbtn" data-action="toggle-task" data-id="' + t.id + '">' +
      (t.is_done ? "✅" : "⬜️") + '</button>' +
      '<div class="grow"><div class="title ' + (t.is_done ? "muted" : "") +
      '" style="' + (t.is_done ? "text-decoration:line-through" : "") + '">' +
      esc(t.title) + '</div><div class="meta">' + meta.join("") + '</div></div>' +
      '<button class="iconbtn danger" data-action="del-task" data-id="' + t.id + '">🗑</button>' +
      '</div>';
  }
  function openTaskForm() {
    const html =
      '<label class="fld"><span class="cap">Vazifa</span>' +
      '<input type="text" id="t-title" placeholder="Masalan: Hisobotni tugatish" maxlength="500"></label>' +
      '<label class="fld"><span class="cap">Ustuvorlik</span><select id="t-prio">' +
      '<option value="normal">🟡 O\'rta</option><option value="high">🔴 Yuqori</option>' +
      '<option value="low">⚪ Past</option></select></label>' +
      '<label class="fld"><span class="cap">Muddat</span>' +
      '<div class="seg" id="t-due">' +
      '<button data-d="0" class="on">Bugun</button><button data-d="1">Ertaga</button>' +
      '<button data-d="7">+7 kun</button><button data-d="">Yo\'q</button></div></label>' +
      '<button class="btn block" id="t-save">Saqlash</button>';
    sheet("Yangi vazifa", html, (el, close) => {
      let due = "0";
      const seg = el.querySelector("#t-due");
      seg.addEventListener("click", (e) => {
        const b = e.target.closest("button"); if (!b) return;
        seg.querySelectorAll("button").forEach((x) => x.classList.remove("on"));
        b.classList.add("on"); due = b.dataset.d;
      });
      el.querySelector("#t-save").addEventListener("click", async () => {
        const title = el.querySelector("#t-title").value.trim();
        if (!title) { toast("Vazifani yozing."); return; }
        let due_date = null;
        if (due !== "") {
          const dt = new Date(); dt.setDate(dt.getDate() + parseInt(due, 10));
          due_date = dt.toISOString().slice(0, 10);
        }
        try {
          await api("POST", "tasks", { title, priority: el.querySelector("#t-prio").value, due_date });
          haptic("success"); close(); renderTasks();
        } catch (err) { haptic("error"); toast(err.message); }
      });
    });
  }

  // ===== 🗒 Qaydlar =====
  let noteTimer = null;
  async function renderNotes() {
    loading();
    try {
      const d = await api("GET", "notes" + (noteQuery ? "?q=" + encodeURIComponent(noteQuery) : ""));
      let html = '<div class="header"><h1>🗒 Qaydlar</h1></div>';
      html += '<input type="text" id="n-search" placeholder="🔍 Qidirish…" value="' +
        esc(noteQuery) + '" style="margin-bottom:12px">';
      if (d.items.length === 0) {
        html += empty("🗒", noteQuery ? "Hech narsa topilmadi." : "Qayd yo'q.");
      } else {
        html += d.items.map(noteCard).join("");
      }
      view.innerHTML = html;
      const s = view.querySelector("#n-search");
      s.addEventListener("input", () => {
        clearTimeout(noteTimer);
        noteTimer = setTimeout(() => {
          noteQuery = s.value.trim();
          const pos = s.selectionStart; renderNotes();
        }, 350);
      });
      // Fokusni saqlab qolish
      if (noteQuery) { s.focus(); s.setSelectionRange(s.value.length, s.value.length); }
    } catch (err) { errorView(err.message); }
  }
  function noteCard(n) {
    return '<div class="card"><div class="row between"><div class="grow" style="white-space:pre-wrap">' +
      esc(n.text) + '</div><button class="iconbtn danger" data-action="del-note" data-id="' +
      n.id + '">🗑</button></div></div>';
  }
  function openNoteForm() {
    const html = '<label class="fld"><span class="cap">Qayd matni</span>' +
      '<textarea id="n-text" placeholder="Yozib qo\'ying…" maxlength="4000"></textarea></label>' +
      '<button class="btn block" id="n-save">Saqlash</button>';
    sheet("Yangi qayd", html, (el, close) => {
      el.querySelector("#n-save").addEventListener("click", async () => {
        const text = el.querySelector("#n-text").value.trim();
        if (!text) { toast("Matnni yozing."); return; }
        try { await api("POST", "notes", { text }); haptic("success"); close(); renderNotes(); }
        catch (err) { haptic("error"); toast(err.message); }
      });
    });
  }

  // ===== 📚 Materiallar =====
  async function renderMaterials() {
    loading();
    try {
      const d = await api("GET", "materials");
      let html = '<div class="header"><h1>📚 Materiallar</h1></div>';
      if (d.items.length === 0) {
        html += empty("📚", "Material yo'q. Kitob/kurs/xatm qo'shing.");
      } else {
        html += d.items.map(materialCard).join("");
      }
      view.innerHTML = html;
    } catch (err) { errorView(err.message); }
  }
  function materialCard(m) {
    let prog = "";
    if (m.total) {
      prog = '<div class="progress"><div style="width:' + (m.percent || 0) + '%"></div></div>' +
        '<div class="meta"><span class="badge">' + (m.current || 0) + " / " + m.total +
        (m.unit ? " " + esc(m.unit) : "") + '</span><span class="badge">' + (m.percent || 0) +
        '%</span></div>';
    } else {
      prog = '<div class="meta"><span class="badge">' + (m.current || 0) +
        (m.unit ? " " + esc(m.unit) : "") + '</span></div>';
    }
    const controls = m.status === "done" ? "" :
      '<div class="row" style="margin-top:10px;gap:8px">' +
      '<button class="btn ghost sm" data-action="mat-dec" data-id="' + m.id + '" data-cur="' +
      (m.current || 0) + '">−</button>' +
      '<button class="btn ghost sm" data-action="mat-inc" data-id="' + m.id + '" data-cur="' +
      (m.current || 0) + '">＋</button>' +
      '<div class="grow"></div>' +
      '<button class="iconbtn" data-action="mat-edit" data-m=\'' +
      esc(JSON.stringify(m)) + '\'>✏️</button>' +
      '<button class="iconbtn danger" data-action="del-material" data-id="' + m.id + '">🗑</button></div>';
    return '<div class="card"><div class="row between"><div class="grow"><div class="title">' +
      esc(m.title) + '</div><div class="meta"><span class="badge">' + esc(m.mtype_label) +
      '</span><span class="badge">' + esc(m.status_label) + '</span></div></div></div>' +
      prog + controls + '</div>';
  }
  function openMaterialForm() {
    const html =
      '<label class="fld"><span class="cap">Nomi</span>' +
      '<input type="text" id="m-title" placeholder="Masalan: Qur\'on xatmi" maxlength="500"></label>' +
      '<label class="fld"><span class="cap">Turi</span><select id="m-type">' +
      '<option value="book">📖 Kitob</option><option value="course">🎓 Kurs</option>' +
      '<option value="quran">☪️ Qur\'on</option><option value="other">📄 Boshqa</option></select></label>' +
      '<label class="fld"><span class="cap">Umumiy hajm (ixtiyoriy)</span>' +
      '<input type="number" id="m-total" min="1" placeholder="Masalan: 604"></label>' +
      '<label class="fld"><span class="cap">O\'lchov (ixtiyoriy)</span>' +
      '<input type="text" id="m-unit" placeholder="bet / dars / bob" maxlength="30"></label>' +
      '<button class="btn block" id="m-save">Saqlash</button>';
    sheet("Yangi material", html, (el, close) => {
      el.querySelector("#m-save").addEventListener("click", async () => {
        const title = el.querySelector("#m-title").value.trim();
        if (!title) { toast("Nomini yozing."); return; }
        const total = parseInt(el.querySelector("#m-total").value, 10);
        try {
          await api("POST", "materials", {
            title, mtype: el.querySelector("#m-type").value,
            total: total > 0 ? total : null,
            unit: el.querySelector("#m-unit").value.trim() || null,
          });
          haptic("success"); close(); renderMaterials();
        } catch (err) { haptic("error"); toast(err.message); }
      });
    });
  }
  function openMaterialEdit(m) {
    const html =
      '<label class="fld"><span class="cap">Joriy nuqta</span>' +
      '<input type="number" id="e-cur" min="0" value="' + (m.current || 0) + '"></label>' +
      '<label class="fld"><span class="cap">Umumiy hajm</span>' +
      '<input type="number" id="e-total" min="1" value="' + (m.total || "") + '"></label>' +
      '<label class="fld"><span class="cap">Holat</span><select id="e-status">' +
      '<option value="active"' + (m.status === "active" ? " selected" : "") + '>🟢 Faol</option>' +
      '<option value="paused"' + (m.status === "paused" ? " selected" : "") + '>⏸ Pauzada</option>' +
      '<option value="done"' + (m.status === "done" ? " selected" : "") + '>✅ Yakunlangan</option>' +
      '</select></label><button class="btn block" id="e-save">Saqlash</button>';
    sheet("Tahrirlash", html, (el, close) => {
      el.querySelector("#e-save").addEventListener("click", async () => {
        const total = parseInt(el.querySelector("#e-total").value, 10);
        try {
          await api("POST", "materials/" + m.id, {
            current: parseInt(el.querySelector("#e-cur").value, 10) || 0,
            total: total > 0 ? total : null,
            status: el.querySelector("#e-status").value,
          });
          haptic("success"); close(); renderMaterials();
        } catch (err) { haptic("error"); toast(err.message); }
      });
    });
  }

  // ===== ⚙️ Sozlamalar =====
  async function renderSettings() {
    loading();
    try {
      const d = await api("GET", "bootstrap");
      const s = d.settings;
      const time = String(s.digest_hour).padStart(2, "0") + ":" +
        String(s.digest_minute).padStart(2, "0");
      let html = '<div class="header"><h1>⚙️ Sozlamalar</h1></div>' +
        '<div class="card"><div class="row between"><div class="grow">' +
        '<div class="title">🌅 Ertalabki reja</div>' +
        '<div class="meta">Har kuni bugungi rejalar bitta xabarda</div></div>' +
        '<label class="switch"><input type="checkbox" id="s-dg"' +
        (s.digest_enabled ? " checked" : "") +
        '><span class="track"></span><span class="knob"></span></label></div>' +
        '<label class="fld" style="margin-top:14px"><span class="cap">Yuborish vaqti</span>' +
        '<input type="time" id="s-time" value="' + time + '"></label>' +
        '<button class="btn block" id="s-save">Saqlash</button></div>' +
        '<div class="card muted center" style="margin-top:16px">EslatBot Mini App</div>';
      view.innerHTML = html;
      view.querySelector("#s-save").addEventListener("click", async () => {
        const time = (view.querySelector("#s-time").value || "07:00").split(":");
        try {
          await api("POST", "settings", {
            digest_enabled: view.querySelector("#s-dg").checked,
            digest_hour: parseInt(time[0], 10), digest_minute: parseInt(time[1], 10),
          });
          haptic("success"); toast("Saqlandi ✅");
        } catch (err) { haptic("error"); toast(err.message); }
      });
    } catch (err) { errorView(err.message); }
  }

  // ===== Ishga tushirish =====
  if (!INIT) {
    view.innerHTML = empty("📲",
      "Bu sahifa faqat Telegram ichida ishlaydi. Iltimos, botdagi «Mini App» tugmasi orqali oching.");
    return;
  }
  tabbar.classList.remove("hidden");
  setTab("home");
})();
