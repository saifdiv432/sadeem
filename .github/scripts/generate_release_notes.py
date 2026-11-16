#!/usr/bin/env python3
"""
Generate Bilingual (English + Arabic) GitHub Release Notes for Sadeem ISO.
"""
import os
import sys

def main():
    download_url = os.environ.get("DIRECT_URL")
    if not download_url:
        owner = os.environ.get("HF_USERNAME", "saifeldin432")
        download_url = f"https://huggingface.co/datasets/{owner}/sadeem-iso/resolve/main/sadeem-45.iso"

    notes = f"""# 🚀 Sadeem 45 (v45) — Official Installation Image

### 📥 Direct Download (Single-Click):
* **[Download sadeem-45.iso (Full Installer - Single Complete File)]({download_url})**
* **Direct Download Link:** `{download_url}`

---

### 💾 Flashing to USB Drive:
Write the complete `sadeem-45.iso` image directly to a USB flash drive (minimum 8 GB) using one of the following utilities:
1. **Fedora Media Writer** (Recommended for Linux, Windows, macOS).
2. **BalenaEtcher** (Cross-platform).
3. **Rufus** (On Windows: ensure you select **DD Image mode** when prompted after clicking Start).
4. **Ventoy** (Simply copy `sadeem-45.iso` directly onto your Ventoy drive).

---

### 🔍 Verify SHA256 Checksum:
Verify that your downloaded ISO matches the attached `SHA256SUMS` file:
* **Linux / macOS:**
  ```bash
  sha256sum -c SHA256SUMS
  ```
* **Windows (PowerShell):**
  ```powershell
  Get-FileHash -Algorithm SHA256 .\\sadeem-45.iso
  ```

---

### ⚙️ System Requirements:
* **Storage:** At least **40 GB** free disk space (SSD strongly recommended).
* **RAM:** 4 GB minimum (8 GB recommended for containers and gaming).

---

### 🔄 Direct Rebase for Fedora Atomic Users:
If you are already running Fedora Silverblue 45 (or any Fedora Atomic desktop), you can switch to Sadeem 45 with a single command without flashing an ISO:
```bash
rpm-ostree rebase ostree-unverified-registry:ghcr.io/saifdiv432/sadeem:latest
systemctl reboot
```

<br>

---

# 🚀 سـديـم 45 (v45) — وسائط التثبيت الرسمية

### 📥 رابط التنزيل المباشر (ملف كامل بنقرة واحدة):
* **[اضغط هنا لتنزيل ملف sadeem-45.iso كاملاً ومباشرة (Hugging Face)]({download_url})**
* **رابط التنزيل المباشر:** `{download_url}`

---

### 💾 طريقة حرق ملف الـ ISO على ذاكرة فلاشية (USB):
احرق ملف `sadeem-45.iso` الكامل مباشرة على ذاكرة فلاشية USB (سعة 8 جيجابايت على الأقل) باستخدام أحد البرامج التالية:
1. **Fedora Media Writer** (الخيار الموصى به لجميع الأنظمة - Linux, Windows, macOS).
2. **BalenaEtcher** (متوفر لجميع المنصات).
3. **Rufus** (على Windows: تأكد من اختيار **وضع كتابة صورة DD** أو **DD Image mode** عند ظهور رسالة التأكيد بعد الضغط على Start).
4. **Ventoy** (يمكنك ببساطة نسخ ملف `sadeem-45.iso` مباشرة إلى فلاشة Ventoy).

---

### 🔍 التحقق من صحة وسلامة الملف (Verify SHA256 Checksum):
تحقق من تطابق بصمة التشفير لملف الـ ISO مع الملف المرفق `SHA256SUMS`:
* **لينكس أو ماك (Linux / macOS):**
  ```bash
  sha256sum -c SHA256SUMS
  ```
* **ويندوز (PowerShell):**
  ```powershell
  Get-FileHash -Algorithm SHA256 .\\sadeem-45.iso
  ```

---

### ⚙️ متطلبات التثبيت على القرص:
* **المساحة التخزينية:** مساحة حرة لا تقل عن **40 جيجابايت** على القرص (SSD موصى به).
* **الذاكرة العشوائية (RAM):** 4 جيجابايت كحد أدنى (8 جيجابايت موصى بها للحاويات والألعاب).

---

### 🔄 التحويل المباشر لمستخدمي فيدورا الذرية:
إذا كنت تستخدم حالياً أي توزيعة ذرية مبنية على فيدورا (مثل Fedora Silverblue 45)، يمكنك التحويل مباشرة عبر طرفية نظامك دون الحاجة لحرق الـ ISO:
```bash
rpm-ostree rebase ostree-unverified-registry:ghcr.io/saifdiv432/sadeem:latest
systemctl reboot
```
"""

    os.makedirs("build-output", exist_ok=True)
    notes_path = os.path.join("build-output", "RELEASE_NOTES.md")
    with open(notes_path, "w", encoding="utf-8") as f:
        f.write(notes.strip() + "\n")
    print(f"Generated {notes_path} with download URL: {download_url}")

if __name__ == "__main__":
    main()
