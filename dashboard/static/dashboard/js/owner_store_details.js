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

  // เลือกรูปแล้วแสดงแค่ preview ยังไม่ส่งอะไรไปเซิร์ฟเวอร์
  // ไฟล์จะถูกส่งไปพร้อมฟอร์มตอนกด Save (เซิร์ฟเวอร์ตรวจไฟล์ซ้ำเสมอ)
  form.querySelectorAll("[data-image-input]").forEach((input) => {
    const box = input.closest(".store-upload");
    const image = box.querySelector("img");
    const label = box.querySelector("[data-image-label]");
    const isProfile = input.hasAttribute("data-profile-input");
    const savedSrc = isProfile ? image.getAttribute("src") : null;
    let previewUrl;

    const showImage = (src) => { image.src = src; image.hidden = false; label.hidden = true; };
    const showEmpty = () => { image.removeAttribute("src"); image.hidden = true; label.hidden = false; };
    const restoreSaved = () => { if (savedSrc) showImage(savedSrc); else showEmpty(); };
    const clearPreview = () => { if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; } };

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

      if (!file) { restoreSaved(); return; }
      if (!IMAGE_TYPES.includes(file.type)) { announce("รองรับเฉพาะไฟล์รูป JPG, PNG หรือ WebP เท่านั้น"); input.value = ""; restoreSaved(); return; }
      if (file.size > MAX_IMAGE_BYTES) { announce("ไฟล์รูปต้องมีขนาดไม่เกิน 5 MB"); input.value = ""; restoreSaved(); return; }

      previewUrl = URL.createObjectURL(file);
      showImage(previewUrl);
    });
  });
  form.querySelector("[data-add-slot]").addEventListener("click", () => {
    const row = document.createElement("tr");
    row.innerHTML = '<td><input type="checkbox" checked aria-label="Slot available"></td><td><input type="time" value="14:00" aria-label="Slot time"></td><td><input type="number" value="4" min="1" max="100" aria-label="Tables"></td><td><button type="button" data-remove-slot aria-label="Remove slot">×</button></td>';
    list.append(row);
  });
  list.addEventListener("click", (event) => { const button = event.target.closest("[data-remove-slot]"); if (button) button.closest("tr").remove(); });
  // กดซ้ำไม่ได้ระหว่างบันทึก (อัปโหลดรูปอาจใช้เวลา) หน้าจะโหลดใหม่เองหลังเซิร์ฟเวอร์ตอบ
  const saveButton = form.querySelector("[data-save-button]");
  const saveLabel = saveButton ? saveButton.innerHTML : "";
  form.addEventListener("submit", (event) => {
    if (!form.reportValidity()) { event.preventDefault(); return; }
    if (saveButton) { saveButton.disabled = true; saveButton.textContent = "กำลังบันทึก…"; }
  });
  // กลับมาที่หน้านี้ด้วยปุ่ม Back (bfcache) ให้ปุ่มกดได้อีกครั้ง
  window.addEventListener("pageshow", () => { if (saveButton) { saveButton.disabled = false; saveButton.innerHTML = saveLabel; } });
})();
