#!/usr/bin/env python3
"""
Generate GitHub Release Notes for Sadeem ISO.
"""
import os
import sys

def main():
    download_url = os.environ.get("DIRECT_URL")
    if not download_url:
        owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "saifeldinosama9677-ctrl")
        download_url = f"https://huggingface.co/datasets/{owner}/sadeem-iso/resolve/main/sadeem-45.iso"

    notes = f"""# 🚀 Sadeem 45 (سديم 45) - Official ISO Release

### 📥 رابط التنزيل المباشر بنقرة واحدة (Single-Click Direct Download):
* **[اضغط هنا لتنزيل ملف sadeem-45.iso كاملاً ومباشرة]({download_url})**
* **Direct Download Link:** [{download_url}]({download_url})

---

### 💾 طريقة حرق ملف الـ ISO على ذاكرة فلاشية (Flashing to USB):
احرق ملف `sadeem-45.iso` الكامل مباشرة على ذاكرة فلاشية USB (سعة 8 جيجابايت على الأقل) باستخدام أحد البرامج التالية:
1. **Fedora Media Writer** (الخيار الموصى به لجميع الأنظمة - Linux, Windows, macOS).
2. **BalenaEtcher** (متوفر لجميع المنصات).
3. **Rufus** (على Windows: تأكد من اختيار **وضع كتابة صورة DD** أو **DD Image mode** عند ظهور رسالة التأكيد بعد الضغط على Start).
4. **Ventoy** (يمكنك نسخ ملف `sadeem-45.iso` مباشرة إلى فلاشة Ventoy).

---

### 🔍 التحقق من صحة وسلامة الملف (Verify SHA256 Checksum):
تحقق من تطابق بصمة التشفير لملف الـ ISO مع الملف المرفق `SHA256SUMS`:

#### 🐧 لينكس أو ماك (Linux / macOS):
```bash
sha256sum -c SHA256SUMS
```

#### 🪟 ويندوز (PowerShell):
```powershell
Get-FileHash -Algorithm SHA256 .\\sadeem-45.iso
```

---

### ⚙️ متطلبات التثبيت (Installation Requirements):
* **المساحة التخزينية:** مساحة حرة لا تقل عن **40 جيجابايت** على القرص (SSD موصى به).
* **الذاكرة العشوائية (RAM):** 4 جيجابايت كحد أدنى (8 جيجابايت موصى بها للحاويات والألعاب).

---

### 🔄 التحويل المباشر لمستخدمي فيدورا الذرية (Direct Rebase):
إذا كنت تستخدم حالياً أي توزيعة ذرية مبنية على فيدورا (مثل Fedora Silverblue 45)، يمكنك التحويل مباشرة عبر طرفية نظامك دون الحاجة لحرق الـ ISO:
```bash
rpm-ostree rebase ostree-unverified-registry:ghcr.io/saifeldinosama9677-ctrl/sadeem:latest
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
