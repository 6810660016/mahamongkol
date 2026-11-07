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

  // รูปโปรไฟล์: เลือกแล้วแสดงแค่ preview ยังไม่ส่งอะไรไปเซิร์ฟเวอร์
  // ไฟล์จะถูกส่งไปพร้อมข้อมูลร้านตอนกด Save เท่านั้น (เซิร์ฟเวอร์ตรวจไฟล์ซ้ำเสมอ)
  let profile = null; // { commit(url) } ใช้หลังบันทึกสำเร็จ
  form.querySelectorAll("[data-image-input]").forEach((input) => {
    const box = input.closest(".store-upload");
    const image = box.querySelector("img");
    const label = box.querySelector("[data-image-label]");
    const isProfile = input.hasAttribute("data-profile-input");
    let savedSrc = isProfile ? image.getAttribute("src") : null;
    let previewUrl;

    const showImage = (src) => { image.src = src; image.hidden = false; label.hidden = true; };
    const showEmpty = () => { image.removeAttribute("src"); image.hidden = true; label.hidden = false; };
    const restoreSaved = () => { if (savedSrc) showImage(savedSrc); else showEmpty(); };
    const clearPreview = () => { if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; } };

    if (isProfile) {
      // บันทึกสำเร็จ: รูปที่เลือกกลายเป็นรูปที่บันทึกแล้ว และล้างไฟล์ออกจาก input กันอัปโหลดซ้ำ
      profile = { commit(url) { if (url) savedSrc = url; input.value = ""; clearPreview(); restoreSaved(); } };
    }

    input.addEventListener("change", () => {
      const file = input.files[0];
      clearPreview();

      // ช่องรูปแกลเลอรี่ยังเป็น preview เท่านั้น (ไม่มี name จึงไม่ถูกส่ง)
      if (!isProfile) {
        if (!file) { showEmpty(); return; }
        previewUrl = URL.createObjectURL(file);
        showImage(previewUrl);
        return;
      }

      setError("image_file", "");
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

  form.querySelector("[data-add-slot]").addEventListener("click", () => {
    const row = document.createElement("tr");
    row.innerHTML = '<td><input type="checkbox" checked aria-label="Slot available"></td><td><input type="time" value="14:00" aria-label="Slot time"></td><td><input type="number" value="4" min="1" max="100" aria-label="Tables"></td><td><button type="button" data-remove-slot aria-label="Remove slot">×</button></td>';
    list.append(row);
  });
  list.addEventListener("click", (event) => { const button = event.target.closest("[data-remove-slot]"); if (button) button.closest("tr").remove(); });

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
