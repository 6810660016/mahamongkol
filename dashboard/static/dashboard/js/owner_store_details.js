(() => {
  "use strict";
  const form = document.querySelector("[data-store-detail-form]");
  if (!form) return;
  const list = form.querySelector("[data-slot-list]");
  const toast = document.querySelector("[data-store-toast]");
  let toastTimer;
  const announce = (message) => { toast.textContent = message; toast.classList.add("is-visible"); clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 3500); };
  const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
  const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

  // รูปโปรไฟล์และรูป Pictures ทำงานเหมือนกัน: เลือกแล้วแสดงแค่ preview ยังไม่ส่งอะไรไปเซิร์ฟเวอร์
  // ไฟล์จะถูกส่งไปพร้อมข้อมูลร้านตอนกด Save เท่านั้น (เซิร์ฟเวอร์ตรวจไฟล์ซ้ำเสมอ)
  // ช่อง Pictures: ปุ่ม × มุมขวาบนของรูปลบรูปในช่อง (ลบจริงตอนกด Save) และมี Undo ให้เปลี่ยนใจ
  // ข้างหลังใช้ช่องติ๊ก gallery_remove เป็นตัวส่งค่า ถ้าไม่มี JS ช่องติ๊กนี้จะโผล่ให้ติ๊กเองแทนปุ่ม ×
  let profile = null; // { commit(url) } ใช้หลังบันทึกสำเร็จ
  const gallery = {}; // { slot: { commit(url) } }
  form.querySelectorAll("[data-image-input]").forEach((input) => {
    const box = input.closest(".store-upload");
    const image = box.querySelector("img");
    const label = box.querySelector("[data-image-label]");
    const isProfile = input.hasAttribute("data-profile-input");
    const slotBox = input.closest("[data-gallery-slot]");
    const removeLabel = slotBox ? slotBox.querySelector("[data-gallery-remove-label]") : null;
    const removeBox = slotBox ? slotBox.querySelector("[data-gallery-remove]") : null;
    const clearButton = slotBox ? slotBox.querySelector("[data-gallery-clear]") : null;
    const undoBox = slotBox ? slotBox.querySelector("[data-gallery-undo]") : null;
    const undoButton = slotBox ? slotBox.querySelector("[data-gallery-undo-button]") : null;
    let savedSrc = image.getAttribute("src");
    let previewUrl;

    // × แสดงเมื่อมีรูปให้ลบ (รูปที่บันทึกไว้หรือรูปที่เพิ่งเลือก) Undo แสดงเมื่อสั่งลบรูปที่บันทึกไว้แล้ว
    const syncControls = () => {
      if (!removeBox) return;
      const removed = removeBox.checked;
      if (clearButton) clearButton.hidden = removed || !(savedSrc || previewUrl);
      if (undoBox) undoBox.hidden = !removed;
    };
    const showImage = (src) => { image.src = src; image.hidden = false; label.hidden = true; syncControls(); };
    const showEmpty = () => { image.removeAttribute("src"); image.hidden = true; label.hidden = false; syncControls(); };
    // ติ๊ก Remove อยู่ = แสดงช่องว่าง (รูปจริงจะถูกลบตอนกด Save)
    const restoreSaved = () => { if (savedSrc && !(removeBox && removeBox.checked)) showImage(savedSrc); else showEmpty(); };
    const clearPreview = () => { if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; } };

    // บันทึกสำเร็จ: รูปที่เลือกกลายเป็นรูปที่บันทึกแล้ว (หรือถูกลบถ้า url ว่าง) และล้างไฟล์/ช่องติ๊กออก กันส่งซ้ำ
    const commit = (url) => {
      savedSrc = url || null;
      input.value = "";
      if (removeBox) removeBox.checked = false;
      clearPreview(); restoreSaved();
    };
    if (isProfile) profile = { commit: (url) => { if (url) commit(url); else { input.value = ""; clearPreview(); restoreSaved(); } } };
    if (slotBox) gallery[slotBox.dataset.gallerySlot] = { commit };

    if (removeBox) {
      // มี JS: ซ่อนช่องติ๊กแบบ fallback แล้วใช้ปุ่ม × / Undo แทน (ช่องติ๊กยังเป็นตัวเก็บค่าที่ถูกส่งไปกับฟอร์ม)
      if (removeLabel) removeLabel.hidden = true;
      removeBox.addEventListener("change", () => {
        if (removeBox.checked) { input.value = ""; clearPreview(); }
        setError(input.name, "");
        restoreSaved();
      });
      if (clearButton) {
        clearButton.addEventListener("click", () => {
          input.value = ""; clearPreview(); setError(input.name, "");
          // มีรูปที่บันทึกไว้ = สั่งลบ (กด Undo ได้) ถ้ามีแค่รูปที่เพิ่งเลือก = ทิ้งรูปนั้นกลับเป็นช่องว่าง
          removeBox.checked = Boolean(savedSrc);
          restoreSaved();
          if (removeBox.checked && undoButton) undoButton.focus();
          else input.focus();
        });
      }
      if (undoButton) {
        undoButton.addEventListener("click", () => {
          removeBox.checked = false;
          restoreSaved();
          if (clearButton && !clearButton.hidden) clearButton.focus();
        });
      }
      syncControls();
    }

    input.addEventListener("change", () => {
      const file = input.files[0];
      clearPreview();
      setError(input.name, "");
      if (removeBox) removeBox.checked = false; // เลือกไฟล์ใหม่ = แทนที่รูปเดิม ไม่ใช่ลบ
      if (!file) { restoreSaved(); return; }
      if (!IMAGE_TYPES.includes(file.type)) { announce("รองรับเฉพาะไฟล์รูป JPG, PNG หรือ WebP เท่านั้น"); input.value = ""; restoreSaved(); return; }
      if (file.size > MAX_IMAGE_BYTES) { announce("ไฟล์รูปต้องมีขนาดไม่เกิน 5 MB"); input.value = ""; restoreSaved(); return; }

      previewUrl = URL.createObjectURL(file);
      showImage(previewUrl);
    });
  });

  // error รายช่อง: <small data-error-for="ชื่อ input"> ใต้แต่ละช่อง
  const errorBox = (name) => form.querySelector('[data-error-for="' + name + '"]');
  function setError(name, message) {
    const box = errorBox(name);
    if (box) box.textContent = message;
    const field = form.elements[name];
    if (field && field.setAttribute) { if (message) field.setAttribute("aria-invalid", "true"); else field.removeAttribute("aria-invalid"); }
    return Boolean(box);
  }
  const clearErrors = () => form.querySelectorAll("[data-error-for]").forEach((box) => setError(box.dataset.errorFor, ""));
  // พิมพ์/เลือกใหม่ในช่องที่มี error ให้ล้าง error ของช่องนั้น
  form.addEventListener("input", (event) => { if (event.target.name) setError(event.target.name, ""); });

  // Extra details: แถว key/value เพิ่ม-ลบได้ (เซิร์ฟเวอร์จำกัดจำนวนและความยาวซ้ำเสมอ)
  // ใช้ createElement + .value ไม่ใช้ innerHTML กับข้อความที่ผู้ใช้พิมพ์
  const extraList = form.querySelector("[data-extra-list]");
  const addExtraButton = form.querySelector("[data-add-extra]");
  const maxExtras = extraList ? parseInt(extraList.dataset.max, 10) || 10 : 0;
  const noStoreYet = Boolean(addExtraButton && addExtraButton.disabled && extraList && !extraList.children.length);
  const syncExtraButton = () => { if (addExtraButton) addExtraButton.disabled = noStoreYet || extraList.children.length >= maxExtras; };
  function addExtraRow(key, value) {
    const row = document.createElement("div");
    row.className = "store-extra-row";
    const keyInput = document.createElement("input");
    keyInput.name = "extra_key"; keyInput.type = "text"; keyInput.maxLength = 60;
    keyInput.placeholder = "e.g. Parking"; keyInput.setAttribute("aria-label", "Detail name"); keyInput.value = key || "";
    const valueInput = document.createElement("input");
    valueInput.name = "extra_value"; valueInput.type = "text"; valueInput.maxLength = 200;
    valueInput.placeholder = "e.g. Available on site"; valueInput.setAttribute("aria-label", "Detail value"); valueInput.value = value || "";
    const remove = document.createElement("button");
    remove.type = "button"; remove.textContent = "×"; remove.setAttribute("data-remove-extra", ""); remove.setAttribute("aria-label", "Remove detail");
    row.append(keyInput, valueInput, remove);
    extraList.append(row);
    syncExtraButton();
    return keyInput;
  }
  if (extraList && addExtraButton) {
    addExtraButton.addEventListener("click", () => { if (extraList.children.length < maxExtras) addExtraRow("", "").focus(); });
    extraList.addEventListener("click", (event) => { const button = event.target.closest("[data-remove-extra]"); if (button) { button.closest(".store-extra-row").remove(); syncExtraButton(); } });
    syncExtraButton();
  }
  // หลังบันทึกสำเร็จ: วาดแถวใหม่ตามที่เซิร์ฟเวอร์บันทึกจริง (แถวที่กรอกไม่ครบจะถูกตัดออก)
  const renderExtras = (items) => { if (!extraList) return; extraList.replaceChildren(); items.forEach((item) => addExtraRow(item.key, item.value)); syncExtraButton(); };

  // รอบเวลาจอง: แถวเวลา / จำนวนโต๊ะ / คนต่อโต๊ะ / เปิดให้จอง (เซิร์ฟเวอร์ตรวจและจำกัดจำนวนซ้ำเสมอ)
  // ช่องติ๊ก Available ไม่มี name จึงใช้ input hidden slot_available (1/0) ส่งค่าไปแทน
  const addSlotButton = form.querySelector("[data-add-slot]");
  const slotInput = (name, type, label, value, attrs) => {
    const input = document.createElement("input");
    input.name = name; input.type = type; input.required = true; input.value = value; input.setAttribute("aria-label", label);
    Object.entries(attrs || {}).forEach(([key, val]) => input.setAttribute(key, val));
    return input;
  };
  function addSlotRow(slot) {
    const row = document.createElement("tr");
    row.setAttribute("data-slot-row", "");
    const cells = Array.from({ length: 6 }, () => document.createElement("td"));
    const toggle = document.createElement("input");
    toggle.type = "checkbox"; toggle.checked = slot.available !== false; toggle.setAttribute("data-slot-toggle", ""); toggle.setAttribute("aria-label", "Slot available");
    const flag = document.createElement("input");
    flag.type = "hidden"; flag.name = "slot_available"; flag.value = toggle.checked ? "1" : "0";
    cells[0].append(toggle, flag);
    cells[1].append(slotInput("slot_time", "time", "Slot time", slot.time || "18:00"));
    cells[2].append(slotInput("slot_tables", "number", "Number of tables", slot.table_count || 4, { min: 1, max: addSlotButton.dataset.maxTables }));
    cells[3].append(slotInput("slot_seats", "number", "Guests per table", slot.seats || 4, { min: 1, max: addSlotButton.dataset.maxSeats }));
    cells[4].className = "store-slot-booked"; cells[4].setAttribute("data-slot-booked", "");
    cells[4].textContent = slot.booked === undefined ? "–" : slot.booked + " / " + (slot.table_count || 0);
    const remove = document.createElement("button");
    remove.type = "button"; remove.textContent = "×"; remove.setAttribute("data-remove-slot", ""); remove.setAttribute("aria-label", "Remove slot");
    cells[5].append(remove);
    row.append(...cells);
    list.append(row);
    return row;
  }
  const maxSlots = parseInt(addSlotButton.dataset.max, 10) || 20;
  const syncSlotButton = () => { if (!addSlotButton.hasAttribute("data-no-store")) addSlotButton.disabled = list.children.length >= maxSlots || addSlotDisabledAtStart; };
  const addSlotDisabledAtStart = addSlotButton.disabled;
  addSlotButton.addEventListener("click", () => { if (list.children.length < maxSlots) addSlotRow({}).querySelector("input[name=slot_time]").focus(); syncSlotButton(); });
  list.addEventListener("click", (event) => { const button = event.target.closest("[data-remove-slot]"); if (button) { button.closest("tr").remove(); syncSlotButton(); } });
  list.addEventListener("change", (event) => {
    const toggle = event.target.closest("[data-slot-toggle]");
    if (toggle) toggle.closest("tr").querySelector("input[name=slot_available]").value = toggle.checked ? "1" : "0";
  });
  const renderSlots = (items) => { list.replaceChildren(); items.forEach(addSlotRow); syncSlotButton(); setDirty(false); };
  syncSlotButton();

  // ปฏิทิน: เลือกวันที่เพื่อกำหนดรอบเวลาเฉพาะวันนั้นล่วงหน้า (เลือกได้ตั้งแต่วันนี้จนถึงวันสุดท้ายที่ลูกค้าจองได้)
  // ไม่เลือกวัน = แก้รอบปกติของร้าน เลือกวัน = ตารางด้านซ้ายคือรอบของวันนั้น (แทนรอบปกติเฉพาะวันนั้น)
  let dirty = false;
  function setDirty(value) { dirty = value; }
  list.addEventListener("input", () => setDirty(true));
  list.addEventListener("change", () => setDirty(true));
  list.addEventListener("click", (event) => { if (event.target.closest("[data-remove-slot]")) setDirty(true); });
  addSlotButton.addEventListener("click", () => setDirty(true));

  const calendar = form.querySelector("[data-calendar]");
  const slotsDate = form.querySelector("[data-slots-date]");
  const statusBox = form.querySelector("[data-slots-status]");
  const clearButton = form.querySelector("[data-slots-clear]");
  const usualButton = form.querySelector("[data-slots-usual]");
  if (calendar && slotsDate) {
    const iso = (d) => d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
    const parse = (text) => { const [y, m, d] = text.split("-").map(Number); return new Date(y, m - 1, d); };
    const minDate = parse(calendar.dataset.min);
    const maxDate = parse(calendar.dataset.max);
    const todayText = iso(new Date());
    let customDates = new Set((calendar.dataset.customDates || "").split(",").filter(Boolean));
    let view = new Date(minDate.getFullYear(), minDate.getMonth(), 1);
    const grid = calendar.querySelector("[data-cal-grid]");
    const title = calendar.querySelector("[data-cal-title]");
    const prev = calendar.querySelector("[data-cal-prev]");
    const next = calendar.querySelector("[data-cal-next]");
    const disabledAtStart = addSlotButton.hasAttribute("disabled");

    function drawCalendar() {
      title.textContent = view.toLocaleDateString("en-GB", { month: "long", year: "numeric" });
      grid.replaceChildren();
      const offset = (new Date(view.getFullYear(), view.getMonth(), 1).getDay() + 6) % 7; // เริ่มวันจันทร์
      for (let i = 0; i < offset; i += 1) grid.append(document.createElement("span"));
      const days = new Date(view.getFullYear(), view.getMonth() + 1, 0).getDate();
      for (let day = 1; day <= days; day += 1) {
        const date = new Date(view.getFullYear(), view.getMonth(), day);
        const text = iso(date);
        const button = document.createElement("button");
        button.type = "button"; button.textContent = String(day); button.dataset.date = text;
        button.disabled = disabledAtStart || date < minDate || date > maxDate;
        if (text === todayText) button.classList.add("is-today");
        if (text === slotsDate.value) { button.classList.add("is-selected"); button.setAttribute("aria-pressed", "true"); }
        if (customDates.has(text)) button.classList.add("has-custom");
        grid.append(button);
      }
      prev.disabled = new Date(view.getFullYear(), view.getMonth(), 1) <= new Date(minDate.getFullYear(), minDate.getMonth(), 1);
      next.disabled = new Date(view.getFullYear(), view.getMonth() + 1, 1) > maxDate;
    }
    prev.addEventListener("click", () => { view = new Date(view.getFullYear(), view.getMonth() - 1, 1); drawCalendar(); });
    next.addEventListener("click", () => { view = new Date(view.getFullYear(), view.getMonth() + 1, 1); drawCalendar(); });

    const labelFor = (text) => parse(text).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
    function showStatus(source, text) {
      const defaultNote = form.querySelector("[data-default-note]");
      if (defaultNote) defaultNote.hidden = true;
      clearButton.hidden = source !== "date";
      usualButton.hidden = false;
      const lead = "Schedule for " + labelFor(text) + ". ";
      statusBox.textContent = source === "date" ? lead + "This date has its own schedule. Edit it, then press Save."
        : lead + "It uses the " + (source === "usual" ? "usual" : "default") + " times for now. Change them and press Save to give this date its own schedule.";
    }
    grid.addEventListener("click", async (event) => {
      const button = event.target.closest("button[data-date]");
      if (!button || button.disabled) return;
      if (dirty && !window.confirm("เปลี่ยนวันที่ การแก้ไขที่ยังไม่ได้บันทึกจะหายไป ต้องการทำต่อไหม?")) return;
      try {
        const response = await fetch(calendar.dataset.url + "?date=" + encodeURIComponent(button.dataset.date), { headers: { "X-Requested-With": "XMLHttpRequest", "Accept": "application/json" }, credentials: "same-origin" });
        const payload = await response.json();
        if (!response.ok) { announce(payload.error || "โหลดรอบเวลาของวันนี้ไม่สำเร็จ"); return; }
        slotsDate.value = payload.date;
        renderSlots(payload.rows);
        showStatus(payload.source, payload.date);
        drawCalendar();
      } catch (error) { announce("เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ ลองเลือกวันที่อีกครั้ง"); }
    });
    usualButton.addEventListener("click", () => {
      if (dirty && !window.confirm("การแก้ไขที่ยังไม่ได้บันทึกจะหายไป ต้องการทำต่อไหม?")) return;
      window.location.href = form.action;
    });
    clearButton.addEventListener("click", () => {
      list.replaceChildren(); syncSlotButton(); setDirty(true);
      statusBox.textContent = "All rows removed. Press Save and this date will use the usual schedule again.";
    });
    // บันทึกสำเร็จ: ปรับจุดบนปฏิทินตามที่เซิร์ฟเวอร์บันทึกจริง และวาดสถานะของวันที่เลือกใหม่
    window.refreshSlotCalendar = (dates, selected) => {
      if (Array.isArray(dates)) customDates = new Set(dates);
      if (selected) showStatus(customDates.has(selected) ? "date" : "usual", selected);
      drawCalendar();
    };
    drawCalendar();
  }

  // ก่อนบันทึกจริงถามยืนยันอีกครั้งด้วย dialog (ไม่มี <dialog> ในเบราว์เซอร์เก่าใช้ confirm() แทน)
  const confirmDialog = document.querySelector("[data-confirm-dialog]");
  const confirmSave = () => new Promise((resolve) => {
    if (!confirmDialog || typeof confirmDialog.showModal !== "function") { resolve(window.confirm("ยืนยันว่าจะเปลี่ยนแปลงข้อมูลร้านและรอบเวลาจองใช่ไหม?")); return; }
    const done = () => { confirmDialog.removeEventListener("close", done); resolve(confirmDialog.returnValue === "ok"); };
    confirmDialog.addEventListener("close", done);
    confirmDialog.returnValue = "cancel";
    confirmDialog.showModal();
  });

  // Save: ส่งทั้งฟอร์ม (ข้อมูลร้าน + ไฟล์รูป) ด้วย fetch ใน request เดียว
  // ถ้าไม่ผ่านหน้าไม่ reload ไฟล์รูปที่เลือกไว้และค่าที่กรอกจึงไม่หาย
  // ถ้าเบราว์เซอร์ไม่รองรับ fetch จะส่งฟอร์มแบบปกติ (เซิร์ฟเวอร์รองรับทั้งสองแบบ)
  const saveButton = form.querySelector("[data-save-button]");
  const saveLabel = saveButton ? saveButton.innerHTML : "";
  const saveDisabledAtStart = Boolean(saveButton && saveButton.disabled); // บัญชีที่ยังไม่มีร้านจะกดไม่ได้เสมอ
  let saving = false;
  const setSaving = (value) => {
    saving = value;
    if (!saveButton) return;
    saveButton.disabled = value || saveDisabledAtStart;
    if (value) saveButton.textContent = "กำลังบันทึก…"; else saveButton.innerHTML = saveLabel;
    form.setAttribute("aria-busy", value ? "true" : "false");
  };

  form.addEventListener("submit", async (event) => {
    if (!window.fetch || !window.FormData) return;
    event.preventDefault();
    if (saving) return;
    if (!form.reportValidity()) return;
    if (!(await confirmSave())) return;
    clearErrors();
    setSaving(true);
    try {
      const response = await fetch(form.action, {
        method: "POST",
        headers: { "X-Requested-With": "XMLHttpRequest", "Accept": "application/json", "X-CSRFToken": form.elements.csrfmiddlewaretoken.value },
        body: new FormData(form),
        credentials: "same-origin",
      });
      let payload = null;
      try { payload = await response.json(); } catch (error) { payload = null; }

      if (response.ok && payload && payload.ok) {
        if (profile) profile.commit(payload.image_url);
        if (Array.isArray(payload.extras)) renderExtras(payload.extras);
        if (Array.isArray(payload.booking_slots)) renderSlots(payload.booking_slots);
        if (window.refreshSlotCalendar) window.refreshSlotCalendar(payload.custom_dates, form.elements.slots_date ? form.elements.slots_date.value : "");
        if (Array.isArray(payload.gallery)) payload.gallery.forEach((item) => { if (gallery[item.slot]) gallery[item.slot].commit(item.url); });
        const chip = document.querySelector("[data-store-name-chip]");
        if (chip && payload.name) chip.textContent = payload.name;
        announce(payload.message || "บันทึกเรียบร้อยแล้ว");
        return;
      }

      const errors = (payload && payload.errors) || {};
      let firstInvalid = null;
      Object.entries(errors).forEach(([name, messages]) => {
        const shown = setError(name, [].concat(messages).join(" "));
        if (shown && !firstInvalid) firstInvalid = form.elements[name];
      });
      if (firstInvalid && firstInvalid.focus) firstInvalid.focus();
      announce((payload && payload.error) || "บันทึกไม่สำเร็จ กรุณาลองใหม่อีกครั้ง (" + response.status + ")");
    } catch (error) {
      announce("เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ ข้อมูลที่กรอกยังอยู่ ลองกด Save อีกครั้ง");
    } finally {
      setSaving(false);
    }
  });
  // กลับมาที่หน้านี้ด้วยปุ่ม Back (bfcache) ให้ปุ่มกดได้อีกครั้ง
  window.addEventListener("pageshow", () => { if (!saving) setSaving(false); });
})();
