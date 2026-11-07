(() => {
  "use strict";
  const form = document.querySelector("[data-store-detail-form]");
  if (!form) return;
  const list = form.querySelector("[data-slot-list]");
  const toast = document.querySelector("[data-store-toast]");
  let toastTimer;
  const announce = (message) => { toast.textContent = message; toast.classList.add("is-visible"); clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 3500); };
  const uploadUrl = form.dataset.uploadUrl;
  const csrfToken = form.dataset.csrf;
  const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
  const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

  // รูปโปรไฟล์: อัปโหลดจริงผ่าน Django -> Cloudinary (เซิร์ฟเวอร์ตรวจไฟล์ซ้ำเสมอ)
  const uploadProfileImage = async (file) => {
    const data = new FormData();
    data.append("image", file);
    const response = await fetch(uploadUrl, {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken },
      body: data,
      credentials: "same-origin",
    });
    let payload = null;
    try { payload = await response.json(); } catch (error) { payload = null; }
    if (!response.ok || !payload || !payload.ok) {
      throw new Error((payload && payload.error) || "อัปโหลดรูปไม่สำเร็จ กรุณาลองใหม่อีกครั้ง");
    }
    return payload.image_url;
  };

  form.querySelectorAll("[data-image-input]").forEach((input) => {
    const box = input.closest(".store-upload");
    const image = box.querySelector("img");
    const label = box.querySelector("[data-image-label]");
    const isProfile = input.hasAttribute("data-profile-input");
    let previewUrl;
    let savedSrc = isProfile ? image.getAttribute("src") : null;
    let uploading = false;

    const showImage = (src) => { image.src = src; image.hidden = false; label.hidden = true; };
    const showEmpty = () => { image.removeAttribute("src"); image.hidden = true; label.hidden = false; };
    const restoreSaved = () => { if (savedSrc) showImage(savedSrc); else showEmpty(); };
    const clearPreview = () => { if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; } };

    input.addEventListener("change", async () => {
      const file = input.files[0];
      if (uploading) return;
      clearPreview();

      // ช่องรูปอื่นๆ ยังเป็น preview เท่านั้น (ยังไม่บันทึก)
      if (!isProfile) {
        if (!file) { showEmpty(); return; }
        previewUrl = URL.createObjectURL(file);
        showImage(previewUrl);
        return;
      }

      if (!file) { restoreSaved(); return; }
      if (!uploadUrl) { announce("ยังไม่มีร้านสำหรับบัญชีนี้ จึงอัปโหลดรูปไม่ได้"); input.value = ""; return; }
      if (!IMAGE_TYPES.includes(file.type)) { announce("รองรับเฉพาะไฟล์รูป JPG, PNG หรือ WebP เท่านั้น"); input.value = ""; return; }
      if (file.size > MAX_IMAGE_BYTES) { announce("ไฟล์รูปต้องมีขนาดไม่เกิน 5 MB"); input.value = ""; return; }

      previewUrl = URL.createObjectURL(file);
      showImage(previewUrl);
      uploading = true;
      input.disabled = true;
      box.classList.add("is-uploading");
      box.setAttribute("aria-busy", "true");
      try {
        const url = await uploadProfileImage(file);
        savedSrc = url;
        showImage(url);
        announce("อัปโหลดรูปโปรไฟล์เรียบร้อยแล้ว");
      } catch (error) {
        restoreSaved();
        announce(error.message);
      } finally {
        clearPreview();
        input.value = "";
        input.disabled = false;
        uploading = false;
        box.classList.remove("is-uploading");
        box.removeAttribute("aria-busy");
      }
    });
  });
  form.querySelector("[data-add-slot]").addEventListener("click", () => {
    const row = document.createElement("tr");
    row.innerHTML = '<td><input type="checkbox" checked aria-label="Slot available"></td><td><input type="time" value="14:00" aria-label="Slot time"></td><td><input type="number" value="4" min="1" max="100" aria-label="Tables"></td><td><button type="button" data-remove-slot aria-label="Remove slot">×</button></td>';
    list.append(row);
  });
  list.addEventListener("click", (event) => { const button = event.target.closest("[data-remove-slot]"); if (button) button.closest("tr").remove(); });
  form.addEventListener("submit", (event) => { event.preventDefault(); if (form.reportValidity()) announce("Preview updated on this page only. No store data was saved."); });
})();
