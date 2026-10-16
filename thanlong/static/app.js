"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const token = document.querySelector('meta[name="thanlong-token"]').content;
  const serverUnavailableMessage = "Không liên lạc được với máy chủ trên máy tính. Mở CHAY_TREN_WINDOWS.bat, giữ cửa sổ lệnh mở rồi tải lại trang.";
  const typeNames = {
    tap: "Chạm tọa độ", wait: "Chờ", swipe: "Vuốt", keyevent: "Phím Android",
    tap_image: "Chạm mẫu ảnh", wait_image: "Chờ mẫu ảnh",
    confirm: "Xác nhận thủ công",
  };
  const drafts = new Map();
  const dirty = new Set();
  let state = null;
  let selectedId = "trung_ac";
  let busy = false;
  let confirming = false;
  let presets = [];
  let polling = false;
  let deviceEdited = false;
  let mutationRevision = 0;
  let screenUrl = null;
  let screenSize = null;
  let screenCaptureId = null;
  let cropMode = false;
  let selection = null;
  let dragStart = null;
  let lastLogSignature = "";
  let lastCardSignature = "";
  let noticeTimer;
  let serverOffline = false;

  const clone = (value) => JSON.parse(JSON.stringify(value));
  const profile = () => drafts.get(selectedId);
  const screenMatchesProfile = () => !screenSize || !profile() || !profile().reference_size ||
    (profile().reference_size[0] === screenSize.width && profile().reference_size[1] === screenSize.height);
  const running = () => Boolean(state && state.runner && state.runner.running);
  const locked = () => busy || running();
  const uid = () => globalThis.crypto && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const missingTemplates = (item) => (item && item.steps || []).filter((step) => ["tap_image", "wait_image"].includes(step.action) && !step.template).length;
  const calibrated = (item) => Boolean(item && item.steps.length && item.reference_size && !missingTemplates(item));
  const currentPreset = () => presets.find((item) => item.profile_id === selectedId);

  function notify(message, kind = "success", persistent = false) {
    clearTimeout(noticeTimer);
    const notice = $("notice");
    notice.textContent = message;
    notice.className = `notice ${kind}`;
    notice.hidden = false;
    if (!persistent && kind !== "error") noticeTimer = setTimeout(() => { notice.hidden = true; }, 6500);
  }

  async function serverFetch(path, options) {
    try { return await fetch(path, options); }
    catch (error) {
      if (error instanceof TypeError) {
        const failure = new Error(serverUnavailableMessage);
        failure.serverUnavailable = true;
        throw failure;
      }
      throw error;
    }
  }

  async function api(path, body) {
    const options = body === undefined ? {cache: "no-store"} : {
      method: "POST", headers: {"Content-Type": "application/json", "X-ThanLong-Token": token}, body: JSON.stringify(body),
    };
    const response = await serverFetch(path, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Yêu cầu thất bại (HTTP ${response.status}).`);
    return data;
  }

  async function perform(action) {
    if (busy) return;
    mutationRevision += 1;
    busy = true;
    $("main").setAttribute("aria-busy", "true");
    updateControls();
    try { await action(); }
    catch (error) { notify(error.message || String(error), "error", true); }
    finally { busy = false; $("main").setAttribute("aria-busy", "false"); updateControls(); }
  }

  function markDirty() {
    dirty.add(selectedId);
    updateDraftStatus();
    renderCards();
    updateControls();
  }

  function mergeState(next) {
    const recovered = serverOffline;
    serverOffline = false;
    if (recovered && $("notice").textContent === serverUnavailableMessage) notify("Đã liên lạc lại được với máy chủ trên máy tính.");
    const oldSerial = state && state.device && state.device.serial;
    state = next;
    if (oldSerial && next.device && oldSerial !== next.device.serial) clearScreenshot();
    let editorChanged = false;
    for (const item of next.profiles || []) {
      if (!drafts.has(item.id)) drafts.set(item.id, clone(item));
      else if (!dirty.has(item.id) && JSON.stringify(drafts.get(item.id)) !== JSON.stringify(item)) {
        drafts.set(item.id, clone(item));
        if (item.id === selectedId) editorChanged = true;
      }
    }
    if (!drafts.has(selectedId) && drafts.size) selectedId = drafts.keys().next().value;
    renderCards();
    renderDeviceStatus();
    renderRunner();
    renderLogs();
    renderPresetPanel();
    if (editorChanged) renderEditor();
    updateControls();
  }

  async function refreshState(first = false) {
    if (polling) return;
    polling = true;
    const revision = mutationRevision;
    try {
      const next = await api("/api/state");
      if (revision !== mutationRevision) return;
      mergeState(next);
      if (first) { renderEditor(); syncDeviceInputs(); }
    } catch (error) {
      $("connectionBadge").textContent = error.serverUnavailable ? "Mất kết nối máy chủ" : "Máy chủ báo lỗi";
      $("connectionBadge").className = "status-pill";
      if (first || !serverOffline) notify(error.message, "error", true);
      serverOffline = Boolean(error.serverUnavailable);
    } finally { polling = false; }
  }

  async function loadPresets() {
    try {
      const items = await api("/api/presets");
      presets = Array.isArray(items) ? items : [];
      renderPresetPanel();
      if (profile()) renderEditor();
    } catch (error) {
      $("presetDescription").textContent = `Chưa tải được luồng từ clip: ${error.message}`;
    }
    updateControls();
  }

  function renderPresetPanel() {
    $("presetPanel").hidden = selectedId !== "trung_ac";
    const item = currentPreset();
    if (!item) return;
    $("presetDescription").textContent = item.description || item.name;
    const list = $("presetTemplates");
    const signature = JSON.stringify(item.required_templates || []);
    if (list.dataset.signature !== signature) {
      list.dataset.signature = signature;
      list.replaceChildren();
      for (const required of item.required_templates || []) {
        const row = document.createElement("li");
        const label = document.createElement("strong");
        label.textContent = required.label || required.key;
        row.append(label, document.createTextNode(required.hint ? ` — ${required.hint}` : ""));
        list.append(row);
      }
    }
  }

  function renderCards() {
    const container = $("profileCards");
    const signature = JSON.stringify([...drafts.values()].map((item) => [item.id, item.name, item.steps.length, missingTemplates(item), item.reference_size, dirty.has(item.id), item.id === selectedId]));
    if (signature === lastCardSignature) return;
    lastCardSignature = signature;
    const focusId = document.activeElement && document.activeElement.dataset.profileId;
    container.replaceChildren();
    for (const item of drafts.values()) {
      const card = document.createElement("button");
      card.type = "button";
      card.className = `profile-card${item.id === selectedId ? " selected" : ""}${item.id === "tang_bao_do" ? " gold" : ""}`;
      card.dataset.profileId = item.id;
      card.setAttribute("aria-pressed", String(item.id === selectedId));
      card.disabled = locked();
      const symbol = document.createElement("span");
      symbol.className = "profile-symbol";
      symbol.setAttribute("aria-hidden", "true");
      symbol.textContent = item.id === "trung_ac" ? "⚔" : "◇";
      const content = document.createElement("div");
      const title = document.createElement("h3");
      title.textContent = item.name;
      const description = document.createElement("p");
      description.className = "profile-description";
      description.textContent = item.id === "trung_ac" ? "Kịch bản nhiệm vụ trừng ác" : "Kịch bản sử dụng tàng bảo đồ";
      const status = document.createElement("span");
      const count = (item.steps || []).length;
      const missing = missingTemplates(item);
      const ready = calibrated(item);
      status.className = `profile-state${ready ? " ready" : ""}`;
      const dot = document.createElement("span");
      dot.className = "dot";
      const setupText = missing ? `Cần gán ảnh cho ${missing} bước` : !item.reference_size ? "Cần ảnh tham chiếu" : "Cần kiểm thử trên giả lập";
      status.append(dot, document.createTextNode(count ? `${count} thao tác · ${dirty.has(item.id) ? "Chưa lưu · " : ""}${setupText}` : "Cần thiết lập thao tác"));
      content.append(title, description, status);
      const check = document.createElement("span");
      check.className = "profile-check";
      check.setAttribute("aria-hidden", "true");
      check.textContent = item.id === selectedId ? "◉" : "○";
      card.append(symbol, content, check);
      card.addEventListener("click", () => {
        if (locked()) return;
        selectedId = item.id;
        if (screenSize && !profile().reference_size) { profile().reference_size = [screenSize.width, screenSize.height]; dirty.add(selectedId); }
        renderCards();
        renderEditor();
        renderPresetPanel();
        updateControls();
      });
      container.append(card);
    }
    if (focusId) {
      const previous = [...container.querySelectorAll("button")].find((node) => node.dataset.profileId === focusId);
      if (previous) previous.focus({preventScroll: true});
    }
  }

  function syncDeviceInputs() {
    if (!state || deviceEdited) return;
    $("adbPath").value = state.device && state.device.adb_path || "";
    $("deviceAddress").value = state.device && state.device.address || "127.0.0.1:5555";
    renderDeviceOptions(state.device && state.device.serial || "");
  }

  function renderDeviceOptions(value) {
    const select = $("deviceSerial");
    const chosen = value === undefined ? select.value : value;
    select.replaceChildren(new Option("Tự chọn thiết bị khả dụng", ""));
    let hasChosen = !chosen;
    for (const device of state && state.devices || []) {
      const serial = typeof device === "string" ? device : device.serial;
      if (!serial) continue;
      const status = typeof device === "string" ? "device" : device.state || device.status || "device";
      const model = typeof device === "string" ? "" : device.model || "";
      select.add(new Option(`${serial}${model ? ` · ${model}` : ""}${status !== "device" ? ` (${status})` : ""}`, serial));
      if (serial === chosen) hasChosen = true;
    }
    if (!hasChosen) select.add(new Option(`${chosen} · chưa thấy thiết bị`, chosen));
    select.value = chosen;
  }

  function renderDeviceStatus() {
    const connected = Boolean(state && state.connected);
    const badge = $("connectionBadge");
    badge.className = `status-pill${connected ? " connected" : ""}`;
    badge.replaceChildren();
    const dot = document.createElement("span");
    dot.className = "dot";
    badge.append(dot, document.createTextNode(connected ? "Đã kết nối LDPlayer" : "Chưa kết nối"));
    const count = (state && state.devices || []).length;
    $("deviceCount").textContent = count ? `${count} thiết bị được tìm thấy` : "Chưa tìm thấy thiết bị";
    $("selectedDeviceHint").textContent = deviceEdited ? "Cài đặt chưa áp dụng. Nhấn Kết nối hoặc Làm mới thiết bị." : connected && state.device && state.device.serial ? `Đang dùng: ${state.device.serial}` : "Chọn đúng phiên giả lập đang chơi.";
    const currentOptions = [...$("deviceSerial").options].map((o) => o.value).join("|");
    const nextOptions = ["", ...(state.devices || []).map((d) => typeof d === "string" ? d : d.serial)].join("|");
    if (!deviceEdited && currentOptions !== nextOptions) syncDeviceInputs();
  }

  function updateDraftStatus() {
    const current = profile();
    const changed = dirty.has(selectedId);
    $("draftState").textContent = changed ? "Chưa lưu" : "Đã lưu";
    $("draftState").className = `draft-state${changed ? " unsaved" : ""}`;
    $("stepCount").textContent = current ? current.steps.length : "0";
    $("referenceSizeText").textContent = current && current.reference_size ? `Khung tọa độ: ${current.reference_size.join(" × ")} px` : "Chưa có kích thước tham chiếu";
    $("profileDescription").textContent = current && current.description || "";
    const missing = missingTemplates(current);
    const messages = [];
    if (!current || !current.steps.length) messages.push("Cần thiết lập thao tác.");
    else {
      if (missing) messages.push(`Cần gán ảnh cho ${missing} bước nhận diện.`);
      if (!current.reference_size) messages.push("Chụp màn hình LDPlayer để đặt kích thước tham chiếu.");
      if (!missing && current.reference_size) messages.push("Đã gán các mẫu cần thiết. Kiểm tra từng bước trên giả lập trước khi chạy.");
    }
    $("calibrationStatus").textContent = messages.join(" ");
    $("calibrationStatus").className = calibrated(current) ? "configured" : "incomplete";
  }

  function defaultStep(type) {
    const common = {id: uid(), action: type, name: typeNames[type], delay_after: 0};
    if (type === "tap") return {...common, x: 0, y: 0, delay_after: 0.5};
    if (type === "wait") return {...common, seconds: 1};
    if (type === "swipe") return {...common, x: 0, y: 0, x2: 0, y2: 0, duration_ms: 500, delay_after: 0.5};
    if (type === "keyevent") return {...common, code: "BACK", delay_after: 0.5};
    if (type === "confirm") return {...common, prompt: "Kiểm tra trạng thái trên giả lập trước khi tiếp tục.", timeout: 600};
    return {...common, template: "", threshold: 0.90, timeout: 15, delay_after: type === "tap_image" ? 0.5 : 0};
  }

  function makeField(labelText, step, key, {type = "number", min = 0, max, increment = "1", full = false, options, multiline = false} = {}) {
    const label = document.createElement("label");
    label.className = `field${full ? " full" : ""}`;
    label.append(document.createTextNode(labelText));
    const input = document.createElement(options ? "select" : multiline ? "textarea" : "input");
    if (options) {
      for (const [value, text] of options) input.add(new Option(text, value));
    } else if (!multiline) {
      input.type = type;
      if (type === "number") { input.min = min; input.step = increment; if (max !== undefined) input.max = max; }
    }
    input.value = step[key] === undefined ? "" : step[key];
    input.setAttribute("aria-label", labelText);
    input.dataset.runLock = "";
    input.addEventListener("input", () => {
      step[key] = type === "number" && !options ? (input.value === "" ? null : Number(input.value)) : input.value;
      markDirty();
    });
    label.append(input);
    return label;
  }

  function stepButton(label, symbol, handler, disabled = false, extra = "") {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `icon-button ${extra}`;
    button.textContent = symbol;
    button.setAttribute("aria-label", label);
    button.title = label;
    button.dataset.runLock = "";
    button.dataset.alwaysDisabled = String(disabled);
    button.disabled = disabled || locked();
    button.addEventListener("click", () => { if (!locked()) handler(); });
    return button;
  }

  function renderEditor() {
    const current = profile();
    if (!current) return;
    $("editorTitle").textContent = current.name;
    $("repeatCount").value = current.repeat || 1;
    $("repeatCount").max = current.single_cycle ? 1 : 10000;
    $("singleCycleNote").hidden = !current.single_cycle;
    updateDraftStatus();
    const list = $("stepsList");
    list.replaceChildren();
    if (!current.steps.length) {
      const empty = document.createElement("div");
      empty.className = "steps-empty";
      empty.innerHTML = '<div class="empty-icon" aria-hidden="true">☷</div><strong>Cần thiết lập thao tác</strong><p>Bật ghi thao tác rồi chạm vào ảnh màn hình, hoặc chọn một mẫu ảnh để tạo bước nhận diện.</p>';
      list.append(empty);
    }
    current.steps.forEach((step, index) => {
      const card = document.createElement("div");
      card.className = "step-card";
      if (["tap_image", "wait_image"].includes(step.action) && !step.template) card.classList.add("uncalibrated");
      const head = document.createElement("div");
      head.className = "step-head";
      const number = document.createElement("span");
      number.className = "step-number";
      number.textContent = String(index + 1).padStart(2, "0");
      const name = document.createElement("input");
      name.type = "text";
      name.className = "step-name-input";
      name.value = step.name || typeNames[step.action] || step.action;
      name.setAttribute("aria-label", `Tên thao tác ${index + 1}`);
      name.dataset.runLock = "";
      name.addEventListener("input", () => { step.name = name.value; markDirty(); });
      const actions = document.createElement("div");
      actions.className = "step-actions";
      const move = (direction) => {
        [current.steps[index], current.steps[index + direction]] = [current.steps[index + direction], current.steps[index]];
        markDirty(); renderEditor(); updateControls();
      };
      actions.append(
        stepButton(`Di chuyển thao tác ${index + 1} lên`, "↑", () => move(-1), index === 0),
        stepButton(`Di chuyển thao tác ${index + 1} xuống`, "↓", () => move(1), index === current.steps.length - 1),
        stepButton(`Xóa thao tác ${index + 1}`, "×", () => { current.steps.splice(index, 1); markDirty(); renderEditor(); updateControls(); }, false, "remove"),
      );
      head.append(number, name, actions);
      const fields = document.createElement("div");
      fields.className = "step-fields";
      const typeLabel = document.createElement("label");
      typeLabel.className = "field full";
      typeLabel.append(document.createTextNode("Loại thao tác"));
      const typeSelect = document.createElement("select");
      typeSelect.dataset.runLock = "";
      typeSelect.setAttribute("aria-label", "Loại thao tác");
      const imageAction = ["tap_image", "wait_image"].includes(step.action);
      Object.entries(typeNames).forEach(([value, text]) => {
        if (imageAction || !["tap_image", "wait_image"].includes(value)) typeSelect.add(new Option(text, value));
      });
      typeSelect.value = step.action;
      typeSelect.addEventListener("change", () => {
        current.steps[index] = imageAction && ["tap_image", "wait_image"].includes(typeSelect.value)
          ? {...step, action: typeSelect.value, name: typeNames[typeSelect.value]}
          : defaultStep(typeSelect.value);
        markDirty(); renderEditor(); updateControls();
      });
      typeLabel.append(typeSelect);
      fields.append(typeLabel);
      if (step.action === "tap" || step.action === "swipe") {
        fields.append(makeField("Tọa độ X (px)", step, "x"), makeField("Tọa độ Y (px)", step, "y"));
      }
      if (step.action === "swipe") {
        fields.append(makeField("Điểm cuối X (px)", step, "x2"), makeField("Điểm cuối Y (px)", step, "y2"), makeField("Thời gian vuốt (ms)", step, "duration_ms", {min: 1, max: 60000}));
      }
      if (step.action === "wait") fields.append(makeField("Thời gian chờ (giây)", step, "seconds", {increment: "0.1", full: true}));
      if (step.action === "keyevent") fields.append(makeField("Phím Android", step, "code", {options: [["BACK", "Quay lại (BACK)"], ["ENTER", "Xác nhận (ENTER)"]], full: true}));
      if (step.action === "confirm") {
        fields.append(makeField("Yêu cầu cần xác nhận", step, "prompt", {type: "text", full: true, multiline: true}), makeField("Chờ xác nhận tối đa (giây)", step, "timeout", {min: 1, max: 3600, full: true}));
      }
      if (step.action === "tap_image" || step.action === "wait_image") {
        const preview = document.createElement("div");
        preview.className = "template-preview full";
        if (!step.template) preview.classList.add("missing");
        if (step.template) {
          const img = document.createElement("img");
          img.src = `/api/templates/${encodeURIComponent(step.template)}`;
          img.alt = `Mẫu nhận diện của thao tác ${index + 1}`;
          img.addEventListener("error", () => { img.hidden = true; });
          preview.append(img);
        }
        const text = document.createElement("span");
        const spec = currentPreset() && (currentPreset().required_templates || []).find((item) => item.key === step.calibration_key);
        text.textContent = step.template || `Cần gán ảnh${spec ? `: ${spec.label}. ${spec.hint || ""}` : ". Chọn vùng ảnh ở màn hình bên cạnh rồi gán vào bước này."}`;
        preview.append(text);
        const assign = document.createElement("button");
        assign.type = "button";
        assign.className = "button secondary assign-template full";
        assign.textContent = "Gán mẫu ảnh đã chọn";
        assign.setAttribute("aria-label", `Gán mẫu ảnh đã chọn cho thao tác ${index + 1}`);
        assign.dataset.runLock = "";
        assign.dataset.assignTemplate = "";
        assign.addEventListener("click", () => { if (!locked() && !deviceEdited) perform(() => assignImageStep(step)); });
        fields.append(preview, assign, makeField("Độ khớp (0–1)", step, "threshold", {min: 0.1, max: 1, increment: "0.01"}), makeField("Chờ tối đa (giây)", step, "timeout", {min: 0.1, increment: "0.1"}));
        if (step.region) {
          const region = document.createElement("p");
          region.className = "step-note full";
          region.textContent = `Vùng tìm kiếm từ kịch bản nhập: ${JSON.stringify(step.region)}. Xuất JSON để xem cấu hình đầy đủ.`;
          fields.append(region);
        }
      }
      fields.append(makeField("Chờ sau thao tác (giây)", step, "delay_after", {increment: "0.1", full: true}));
      card.append(head, fields);
      list.append(card);
    });
    updateControls();
  }

  function updateControls() {
    document.querySelectorAll("[data-run-lock]").forEach((element) => {
      element.disabled = locked() || element.dataset.alwaysDisabled === "true";
    });
    document.querySelectorAll(".profile-card").forEach((button) => { button.disabled = locked(); });
    const hasDevice = Boolean(state && state.connected);
    for (const id of ["captureButton", "recordToggle", "cropToggle"]) $(id).disabled = locked() || !hasDevice || deviceEdited;
    if (!screenMatchesProfile()) {
      $("recordToggle").checked = false;
      $("recordToggle").disabled = true;
    }
    for (const id of ["addTapImage", "addWaitImage"]) $(id).disabled = locked() || !selection || !screenSize || deviceEdited || !screenMatchesProfile();
    $("useScreenSize").disabled = locked() || !screenSize || deviceEdited;
    const hasSteps = Boolean(profile() && profile().steps.length);
    const ready = calibrated(profile());
    $("startRun").disabled = locked() || !hasDevice || !ready || deviceEdited;
    $("dryRun").disabled = locked() || !ready || deviceEdited;
    $("repeatCount").disabled = locked() || Boolean(profile() && profile().single_cycle);
    $("loadPreset").disabled = locked() || deviceEdited || !currentPreset() || selectedId !== "trung_ac";
    document.querySelectorAll("[data-assign-template]").forEach((button) => {
      button.disabled = locked() || deviceEdited || !screenSize || !selection || !screenMatchesProfile();
    });
    const runner = state && state.runner || {};
    $("confirmRun").disabled = confirming || !runner.running || !runner.awaiting_confirmation || !runner.confirmation_id || runner.stopping;
    $("saveProfile").disabled = locked() || !profile();
    $("stopRun").disabled = !running() || Boolean(state.runner.stopping);
    $("stopRun").textContent = state && state.runner && state.runner.stopping ? "Đang dừng…" : "■ Dừng";
    $("startRun").title = deviceEdited ? "Áp dụng cài đặt thiết bị trước khi chạy." : !hasSteps ? "Hãy thêm ít nhất một thao tác." : !ready ? "Gán đầy đủ mẫu ảnh và kích thước tham chiếu trước khi chạy." : !hasDevice ? "Kết nối LDPlayer trước khi chạy." : "Gửi thao tác đến LDPlayer đã chọn";
    updateScreenMode();
  }

  function renderRunner() {
    const runner = state && state.runner || {};
    const status = $("runStatus");
    status.className = `run-status${runner.running ? " running" : runner.error ? " error" : ""}`;
    const dot = document.createElement("span");
    dot.className = "dot";
    const label = runner.stopping ? "Đang dừng…" : runner.running && runner.awaiting_confirmation ? "Chờ bạn xác nhận" : runner.running ? (runner.dry_run ? "Đang chạy thử" : "Đang chạy trên giả lập") : runner.error ? "Đã dừng do lỗi" : "Sẵn sàng";
    status.replaceChildren(dot, document.createTextNode(label));
    const progress = $("runProgress");
    if (runner.running) {
      const current = drafts.get(runner.profile_id);
      const stepIndex = Number(runner.step_index);
      progress.textContent = `Vòng ${runner.iteration || 1}/${runner.repeat || 1} · Bước ${Number.isFinite(stepIndex) ? Math.max(0, stepIndex + 1) : 0}/${current ? current.steps.length : "?"}`;
      progress.title = runner.step_name || "";
    } else { progress.textContent = runner.error ? "Xem lỗi trong nhật ký" : ""; progress.title = ""; }
    $("confirmationPanel").hidden = !(runner.running && runner.awaiting_confirmation);
    $("confirmationPrompt").textContent = runner.confirmation_prompt || "";
  }

  function renderLogs() {
    const logs = state && state.runner && state.runner.logs || [];
    const signature = JSON.stringify(logs);
    if (signature === lastLogSignature) return;
    lastLogSignature = signature;
    $("logCount").textContent = `${logs.length} sự kiện`;
    const container = $("logs");
    const atBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 65;
    container.replaceChildren();
    if (!logs.length) {
      const empty = document.createElement("div");
      empty.className = "log-empty";
      empty.textContent = "Các bước chạy và lỗi kết nối sẽ xuất hiện tại đây.";
      container.append(empty);
    }
    for (const log of logs.slice(-200)) {
      const row = document.createElement("div");
      const level = String(log.level || "info").toLowerCase();
      row.className = "log-row";
      if (["error", "warn", "warning"].includes(level)) row.classList.add(level);
      const time = document.createElement("span");
      time.className = "log-time";
      const rawTime = String(log.time || "");
      const parsed = new Date(rawTime);
      time.textContent = Number.isNaN(parsed.getTime()) ? rawTime : parsed.toLocaleTimeString("vi-VN", {hour12: false});
      time.title = rawTime;
      const kind = document.createElement("span");
      kind.className = "log-level";
      kind.textContent = level === "error" ? "LỖI" : level === "warning" || level === "warn" ? "CHÚ Ý" : "INFO";
      const message = document.createElement("span");
      message.className = "log-message";
      message.textContent = log.message || "";
      row.append(time, kind, message);
      container.append(row);
    }
    if (atBottom) container.scrollTop = container.scrollHeight;
  }

  function deviceBody(connect) {
    return {adb_path: $("adbPath").value.trim(), address: $("deviceAddress").value.trim(), serial: connect ? null : $("deviceSerial").value, connect};
  }

  function requireCaptureId() {
    if (!screenCaptureId || !screenSize) throw new Error("Hãy chụp lại màn hình LDPlayer trước khi ghi thao tác hoặc gán mẫu ảnh.");
    return screenCaptureId;
  }

  async function saveCurrentProfile() {
    if (!profile()) throw new Error("Chưa có kịch bản để lưu.");
    const data = clone(profile());
    if (screenSize && !data.reference_size) data.reference_size = [screenSize.width, screenSize.height];
    const normalized = await api(`/api/profiles/${encodeURIComponent(selectedId)}`, data);
    drafts.set(selectedId, clone(normalized));
    dirty.delete(selectedId);
    renderCards(); renderEditor();
    return normalized;
  }

  function resetCrop() {
    selection = null;
    dragStart = null;
    $("cropBox").hidden = true;
    $("cropActions").hidden = true;
    updateControls();
  }

  function clearScreenshot() {
    if (screenUrl) URL.revokeObjectURL(screenUrl);
    screenUrl = null;
    screenSize = null;
    screenCaptureId = null;
    $("screenshot").hidden = true;
    $("screenshot").removeAttribute("src");
    $("screenshotEmpty").hidden = false;
    $("screenSize").textContent = "Chưa có ảnh";
    $("pointerPosition").textContent = "Tọa độ theo ảnh gốc";
    $("recordToggle").checked = false;
    cropMode = false;
    resetCrop();
    updateScreenMode();
  }

  function updateScreenMode() {
    const recording = $("recordToggle").checked;
    $("screenshotStage").classList.toggle("crop-mode", cropMode);
    $("screenshotStage").classList.toggle("record-mode", recording && !cropMode);
    $("cropToggle").setAttribute("aria-pressed", String(cropMode));
    $("screenHint").textContent = !screenSize ? "Chụp màn hình sau khi kết nối để bắt đầu." : !screenMatchesProfile() ? "Ảnh khác kích thước kịch bản. Kiểm tra và cập nhật khung tọa độ trước khi ghi thao tác." : cropMode ? "Kéo một vùng nhỏ, đặc trưng trên ảnh để tạo mẫu nhận diện." : recording ? "Mỗi lần chạm ảnh sẽ gửi chạm thật tới LDPlayer và thêm một bước vào kịch bản." : "Ảnh dùng để quan sát. Bật ghi thao tác hoặc chọn mẫu ảnh để thiết lập.";
  }

  async function captureScreen() {
    const response = await serverFetch(`/api/screenshot?t=${Date.now()}`, {cache: "no-store"});
    if (!response.ok) {
      const failure = await response.json().catch(() => ({}));
      throw new Error(failure.error || `Không chụp được màn hình (HTTP ${response.status}).`);
    }
    const captureId = response.headers.get("X-ThanLong-Capture");
    if (!captureId) {
      clearScreenshot();
      throw new Error("Ảnh chưa có mã xác nhận của máy chủ. Hãy tải lại trang và chụp lại màn hình trước khi ghi thao tác hoặc gán mẫu.");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const img = $("screenshot");
    try {
      await new Promise((resolve, reject) => {
        img.onload = resolve;
        img.onerror = () => reject(new Error("Không đọc được ảnh chụp từ LDPlayer."));
        img.src = url;
      });
    } catch (error) { URL.revokeObjectURL(url); throw error; }
    if (screenUrl) URL.revokeObjectURL(screenUrl);
    screenUrl = url;
    screenSize = {width: img.naturalWidth, height: img.naturalHeight};
    screenCaptureId = captureId;
    img.hidden = false;
    $("screenshotEmpty").hidden = true;
    $("screenSize").textContent = `${screenSize.width} × ${screenSize.height} px`;
    if (profile() && !profile().reference_size) {
      profile().reference_size = [screenSize.width, screenSize.height];
      markDirty();
    } else if (profile() && (profile().reference_size[0] !== screenSize.width || profile().reference_size[1] !== screenSize.height)) {
      notify(`Ảnh hiện tại ${screenSize.width} × ${screenSize.height}, khác kích thước kịch bản ${profile().reference_size.join(" × ")}. Kiểm tra lại tọa độ trước khi chạy.`, "warning", true);
    }
    resetCrop();
    updateScreenMode();
  }

  function imagePoint(event, clamp = false) {
    if (!screenSize || $("screenshot").hidden) return null;
    const rect = $("screenshot").getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    const rawX = (event.clientX - rect.left) * screenSize.width / rect.width;
    const rawY = (event.clientY - rect.top) * screenSize.height / rect.height;
    if (!clamp && (rawX < 0 || rawY < 0 || rawX >= screenSize.width || rawY >= screenSize.height)) return null;
    return {x: Math.min(screenSize.width - 1, Math.max(0, Math.floor(rawX))), y: Math.min(screenSize.height - 1, Math.max(0, Math.floor(rawY)))};
  }

  function drawCrop() {
    if (!selection || !screenSize) return;
    const imageRect = $("screenshot").getBoundingClientRect();
    const stageRect = $("screenshotStage").getBoundingClientRect();
    const box = $("cropBox");
    box.style.left = `${imageRect.left - stageRect.left + selection.x * imageRect.width / screenSize.width}px`;
    box.style.top = `${imageRect.top - stageRect.top + selection.y * imageRect.height / screenSize.height}px`;
    box.style.width = `${selection.width * imageRect.width / screenSize.width}px`;
    box.style.height = `${selection.height * imageRect.height / screenSize.height}px`;
    box.hidden = false;
    $("cropDimensions").textContent = `${selection.width} × ${selection.height}`;
    $("cropSummary").textContent = `${selection.width} × ${selection.height} px · x: ${selection.x}, y: ${selection.y}`;
    $("cropActions").hidden = selection.width < 8 || selection.height < 8;
  }

  function updateSelection(point) {
    if (!dragStart || !point) return;
    selection = {
      x: Math.min(dragStart.x, point.x), y: Math.min(dragStart.y, point.y),
      width: Math.abs(point.x - dragStart.x) + 1, height: Math.abs(point.y - dragStart.y) + 1,
    };
    drawCrop(); updateControls();
  }

  async function addImageStep(type) {
    if (!selection || !screenSize) throw new Error("Hãy chọn vùng ảnh trước.");
    const result = await api("/api/template", {...selection, name: `${selectedId}-${Date.now()}`, capture_id: requireCaptureId()});
    const step = {...defaultStep(type), template: result.template};
    profile().steps.push(step);
    if (!profile().reference_size) profile().reference_size = [screenSize.width, screenSize.height];
    markDirty(); renderEditor();
    notify(`Đã thêm ${type === "tap_image" ? "chạm mẫu ảnh" : "chờ mẫu ảnh"}. Lưu kịch bản trước khi đóng ứng dụng.`);
  }

  async function assignImageStep(step) {
    if (!selection || !screenSize || deviceEdited || !screenMatchesProfile()) throw new Error("Chụp màn hình đúng kích thước kịch bản và chọn vùng ảnh trước khi gán mẫu.");
    const result = await api("/api/template", {...selection, name: `${selectedId}-${step.calibration_key || step.id}-${Date.now()}`, capture_id: requireCaptureId()});
    const matches = step.calibration_key
      ? profile().steps.filter((item) => ["tap_image", "wait_image"].includes(item.action) && item.calibration_key === step.calibration_key)
      : [step];
    for (const item of matches) item.template = result.template;
    if (!profile().reference_size) profile().reference_size = [screenSize.width, screenSize.height];
    markDirty(); renderEditor();
    notify(`Đã gán mẫu cho ${matches.length} bước${step.calibration_key ? " dùng cùng nút hoặc trạng thái" : ""}. Lưu kịch bản để giữ thay đổi.`);
  }

  $("loadPreset").addEventListener("click", () => {
    const item = currentPreset();
    if (locked() || deviceEdited || !item || selectedId !== "trung_ac") return;
    if (!window.confirm("Nạp luồng Trừng ác từ clip sẽ thay toàn bộ kịch bản Trừng ác đã lưu và bản nháp chưa lưu. Kịch bản Tàng bảo đồ được giữ nguyên. Luồng mới cần gán ảnh chụp LDPlayer thực tế và có bốn điểm xác nhận thủ công. Tiếp tục thay thế?")) return;
    perform(async () => {
      const loaded = await api(`/api/presets/${encodeURIComponent(item.id)}`, {});
      selectedId = loaded.id;
      drafts.set(loaded.id, clone(loaded));
      dirty.delete(loaded.id);
      if (screenSize && !profile().reference_size) {
        profile().reference_size = [screenSize.width, screenSize.height];
        dirty.add(loaded.id);
      }
      renderCards(); renderEditor(); renderPresetPanel();
      notify("Đã nạp luồng Trừng ác từ clip. Gán đầy đủ mẫu ảnh thật ở từng bước trước khi chạy. Luồng chạy một lượt và chờ bạn xác nhận tại bốn điểm.", "warning", true);
    });
  });

  $("deviceForm").addEventListener("submit", (event) => {
    event.preventDefault();
    if (locked()) return;
    perform(async () => {
      const next = await api("/api/device", deviceBody(true));
      deviceEdited = false;
      mergeState(next); syncDeviceInputs();
      clearScreenshot();
      if (!next.connected) throw new Error("Chưa kết nối được LDPlayer. Kiểm tra đường dẫn ADB, địa chỉ và quyền ADB trong cài đặt giả lập.");
      $("recordToggle").checked = false;
      cropMode = false;
      resetCrop(); updateScreenMode();
      notify("Đã kết nối LDPlayer. Chọn Chụp màn hình để tạo thao tác.");
    });
  });
  $("refreshDevices").addEventListener("click", () => {
    if (locked()) return;
    perform(async () => {
      const next = await api("/api/device", deviceBody(false));
      deviceEdited = false;
      mergeState(next); syncDeviceInputs();
      clearScreenshot();
      notify("Đã làm mới danh sách thiết bị.");
    });
  });
  for (const id of ["adbPath", "deviceAddress", "deviceSerial"]) $(id).addEventListener("input", () => {
    deviceEdited = true;
    $("selectedDeviceHint").textContent = "Cài đặt chưa áp dụng. Nhấn Kết nối hoặc Làm mới thiết bị.";
    updateControls();
  });
  $("deviceSerial").addEventListener("change", () => {
    if (locked()) return;
    perform(async () => {
      const next = await api("/api/device", deviceBody(false));
      deviceEdited = false;
      mergeState(next); syncDeviceInputs(); clearScreenshot();
      notify("Đã áp dụng thiết bị được chọn. Chụp lại màn hình trước khi ghi thao tác.");
    });
  });
  $("useScreenSize").addEventListener("click", () => {
    if (locked() || !screenSize || !profile() || deviceEdited) return;
    profile().reference_size = [screenSize.width, screenSize.height];
    markDirty(); updateScreenMode();
    notify("Đã đổi khung tham chiếu theo ảnh hiện tại. Tọa độ và mẫu ảnh không tự thay đổi; kiểm tra lại từng bước rồi lưu.", "warning", true);
  });
  $("repeatCount").addEventListener("input", () => { if (!locked() && profile()) { profile().repeat = $("repeatCount").value === "" ? null : Number($("repeatCount").value); markDirty(); } });
  $("addStep").addEventListener("click", () => {
    if (locked() || !profile()) return;
    profile().steps.push(defaultStep($("newStepType").value));
    markDirty(); renderEditor();
    $("stepsList").scrollTop = $("stepsList").scrollHeight;
  });
  $("saveProfile").addEventListener("click", () => { if (!locked()) perform(async () => { await saveCurrentProfile(); notify("Đã lưu kịch bản."); }); });
  $("captureButton").addEventListener("click", () => { if (!locked()) perform(captureScreen); });
  $("recordToggle").addEventListener("change", () => {
    if ($("recordToggle").checked) { cropMode = false; resetCrop(); }
    updateScreenMode();
  });
  $("cropToggle").addEventListener("click", () => {
    if (locked()) return;
    if (!screenSize) { notify("Chụp màn hình trước khi chọn mẫu ảnh.", "warning"); return; }
    cropMode = !cropMode;
    if (cropMode) $("recordToggle").checked = false;
    else resetCrop();
    updateScreenMode();
  });
  $("screenshotStage").addEventListener("pointerdown", (event) => {
    if (locked() || deviceEdited || event.button !== 0) return;
    const point = imagePoint(event);
    if (!point || (!cropMode && !$("recordToggle").checked)) return;
    dragStart = {...point, clientX: event.clientX, clientY: event.clientY};
    if (cropMode) {
      event.preventDefault();
      $("screenshotStage").setPointerCapture(event.pointerId);
      updateSelection(point);
    }
  });
  $("screenshotStage").addEventListener("pointermove", (event) => {
    const point = imagePoint(event);
    $("pointerPosition").textContent = point ? `x: ${point.x} · y: ${point.y}` : "Tọa độ theo ảnh gốc";
    if (cropMode && dragStart && !locked()) updateSelection(imagePoint(event, true));
  });
  $("screenshotStage").addEventListener("pointerup", (event) => {
    if (!dragStart || locked()) { dragStart = null; return; }
    const start = dragStart;
    if (cropMode) {
      updateSelection(imagePoint(event, true));
      dragStart = null;
      if ($("screenshotStage").hasPointerCapture(event.pointerId)) $("screenshotStage").releasePointerCapture(event.pointerId);
      if (selection && (selection.width < 8 || selection.height < 8)) { resetCrop(); notify("Chọn mẫu ít nhất 8 × 8 px để nhận diện.", "warning"); }
      return;
    }
    dragStart = null;
    if (!$("recordToggle").checked || Math.hypot(event.clientX - start.clientX, event.clientY - start.clientY) > 8) return;
    const point = imagePoint(event);
    if (!point) return;
    perform(async () => {
      if (!screenMatchesProfile()) throw new Error("Ảnh khác kích thước tham chiếu. Hãy kiểm tra và cập nhật khung tọa độ trước khi gửi chạm.");
      await api("/api/tap", {...point, capture_id: requireCaptureId()});
      profile().steps.push({...defaultStep("tap"), ...point, name: `Chạm (${point.x}, ${point.y})`});
      markDirty(); renderEditor();
      notify(`Đã gửi chạm (${point.x}, ${point.y}) và thêm thao tác. Chụp lại ảnh để xem giao diện mới.`);
    });
  });
  $("screenshotStage").addEventListener("pointercancel", () => { dragStart = null; });
  window.addEventListener("pointerup", () => { dragStart = null; });
  window.addEventListener("resize", drawCrop);
  $("addTapImage").addEventListener("click", () => { if (!locked()) perform(() => addImageStep("tap_image")); });
  $("addWaitImage").addEventListener("click", () => { if (!locked()) perform(() => addImageStep("wait_image")); });
  async function start(dryRun) {
    if (locked()) return;
    if (!calibrated(profile())) { notify("Gán đầy đủ mẫu ảnh và chụp màn hình LDPlayer để xác định kích thước tham chiếu trước khi chạy.", "warning", true); return; }
    perform(async () => {
      await saveCurrentProfile();
      const runner = await api("/api/run", {profile_id: selectedId, dry_run: dryRun});
      state.runner = runner;
      $("recordToggle").checked = false;
      cropMode = false;
      resetCrop(); updateScreenMode();
      renderRunner(); renderLogs();
      notify(dryRun ? "Đã bắt đầu chạy thử. Không gửi thao tác tới giả lập." : "Đã bắt đầu chạy. Theo dõi giả lập và nhấn Dừng khi cần.");
    });
  }
  $("dryRun").addEventListener("click", () => start(true));
  $("startRun").addEventListener("click", () => start(false));
  $("stopRun").addEventListener("click", async () => {
    if (!running() || state.runner.stopping) return;
    mutationRevision += 1;
    $("stopRun").disabled = true;
    try { state.runner = await api("/api/stop", {}); renderRunner(); updateControls(); notify("Đã gửi yêu cầu dừng. Đợi lệnh đang thực hiện kết thúc."); }
    catch (error) { notify(error.message, "error", true); updateControls(); }
  });
  $("confirmRun").addEventListener("click", async () => {
    const runner = state && state.runner;
    if (confirming || !runner || !runner.running || !runner.awaiting_confirmation || !runner.confirmation_id || runner.stopping) return;
    const confirmationId = runner.confirmation_id;
    confirming = true;
    mutationRevision += 1;
    updateControls();
    try {
      state.runner = await api("/api/confirm", {confirmation_id: confirmationId});
      renderRunner(); renderLogs();
      notify("Đã gửi xác nhận. Luồng sẽ tiếp tục bước kế tiếp.");
    } catch (error) { notify(error.message, "error", true); }
    finally { confirming = false; updateControls(); }
  });
  $("exportProfile").addEventListener("click", () => {
    if (locked()) return;
    perform(async () => {
      await saveCurrentProfile();
      const bundle = await api(`/api/export/${encodeURIComponent(selectedId)}`);
      const url = URL.createObjectURL(new Blob([JSON.stringify(bundle, null, 2)], {type: "application/json"}));
      const link = document.createElement("a");
      link.href = url;
      link.download = `thanlong-${selectedId}.json`;
      document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      notify("Đã xuất kịch bản JSON kèm các mẫu ảnh.");
    });
  });
  $("importProfile").addEventListener("click", () => { if (!locked()) $("importFile").click(); });
  $("importFile").addEventListener("change", () => {
    const file = $("importFile").files[0];
    $("importFile").value = "";
    if (!file || locked()) return;
    perform(async () => {
      if (file.size > 16 * 1024 * 1024) throw new Error("Tệp kịch bản quá lớn (tối đa 16 MiB).");
      let bundle;
      try { bundle = JSON.parse(await file.text()); }
      catch { throw new Error("Tệp không phải JSON hợp lệ."); }
      const incomingId = bundle.profile && bundle.profile.id || bundle.id;
      if (incomingId && dirty.has(incomingId)) throw new Error("Kịch bản đích có thay đổi chưa lưu. Hãy lưu kịch bản đó trước khi nhập tệp để tránh mất thao tác.");
      const imported = await api("/api/import", {bundle});
      drafts.set(imported.id, clone(imported));
      dirty.delete(imported.id);
      selectedId = imported.id;
      renderCards(); renderEditor();
      notify(`Đã nhập ${imported.name}. Kiểm tra lại thiết bị, độ phân giải và từng thao tác trước khi chạy.`);
    });
  });
  window.addEventListener("beforeunload", (event) => {
    if (dirty.size) { event.preventDefault(); event.returnValue = ""; }
  });
  refreshState(true);
  loadPresets();
  setInterval(() => { if (!document.hidden && !busy && !confirming) refreshState(); }, 1000);
})();
