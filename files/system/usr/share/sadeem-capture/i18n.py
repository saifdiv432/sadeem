#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Internationalization and localization for Sadeem Capture (أداة لقطة سديم).
Supports 10 system languages: ar, en, fr, es, de, tr, ru, pt, it, zh.
"""

import os

SUPPORTED_LANGUAGES = ("ar", "en", "fr", "es", "de", "tr", "ru", "pt", "it", "zh")


def detect_lang():
    for var in ("LC_ALL", "LC_MESSAGES", "LANGUAGE", "LANG"):
        val = os.environ.get(var, "")
        if val:
            code = val.split(":")[0].split(".")[0].split("_")[0].split("@")[0].lower()
            if code in SUPPORTED_LANGUAGES:
                return code
    return "ar"


LANG = detect_lang()


def is_rtl():
    return LANG == "ar"


STRINGS = {
    "ar": {
        "app_name": "لقطة سديم",
        "mode_selection": "تحديد",
        "mode_screen": "شاشة",
        "mode_window": "نافذة",
        "tooltip_cursor": "تضمين مؤشر الفأرة",
        "tooltip_halo": "تأثير هالة المؤشر",
        "btn_capture": "التقاط",
        "tab_photo": "صورة",
        "tab_video": "فيديو",
        "video_phase2_note": "تسجيل الفيديو سيتوفر في المرحلة القادمة",
        "tooltip_close": "إلغاء (Esc)",
        "select_hint": "اسحب لتحديد منطقة، ثم اضغط Enter أو زر الالتقاط",
        "window_hint": "انقر على النافذة لالتقاطها فوراً",
        "toast_copied": "تم حفظ اللقطة ونسخها إلى الحافظة",
        "filename_prefix": "لقطة_شاشة",
    },
    "en": {
        "app_name": "Sadeem Capture",
        "mode_selection": "Selection",
        "mode_screen": "Screen",
        "mode_window": "Window",
        "tooltip_cursor": "Include mouse cursor",
        "tooltip_halo": "Cursor halo highlight",
        "btn_capture": "Capture",
        "tab_photo": "Photo",
        "tab_video": "Video",
        "video_phase2_note": "Video recording will be available in Phase 2",
        "tooltip_close": "Cancel (Esc)",
        "select_hint": "Drag to select an area, then press Enter or Capture",
        "window_hint": "Click any window to capture immediately",
        "toast_copied": "Screenshot saved and copied to clipboard",
        "filename_prefix": "Screenshot",
    },
    "fr": {
        "app_name": "Sadeem Capture",
        "mode_selection": "Sélection",
        "mode_screen": "Écran",
        "mode_window": "Fenêtre",
        "tooltip_cursor": "Inclure le curseur",
        "tooltip_halo": "Effet de halo du curseur",
        "btn_capture": "Capturer",
        "tab_photo": "Photo",
        "tab_video": "Vidéo",
        "video_phase2_note": "L'enregistrement vidéo sera disponible dans la phase 2",
        "tooltip_close": "Annuler (Échap)",
        "select_hint": "Glissez pour sélectionner une zone, puis appuyez sur Entrée",
        "window_hint": "Cliquez sur une fenêtre pour la capturer",
        "toast_copied": "Capture enregistrée et copiée dans le presse-papiers",
        "filename_prefix": "Capture_d_ecran",
    },
    "es": {
        "app_name": "Sadeem Capture",
        "mode_selection": "Selección",
        "mode_screen": "Pantalla",
        "mode_window": "Ventana",
        "tooltip_cursor": "Incluir puntero",
        "tooltip_halo": "Efecto de halo del cursor",
        "btn_capture": "Capturar",
        "tab_photo": "Foto",
        "tab_video": "Vídeo",
        "video_phase2_note": "La grabación de vídeo estará disponible en la Fase 2",
        "tooltip_close": "Cancelar (Esc)",
        "select_hint": "Arrastra para seleccionar un área, luego presiona Enter",
        "window_hint": "Haz clic en una ventana para capturarla",
        "toast_copied": "Captura guardada y copiada al portapapeles",
        "filename_prefix": "Captura_de_pantalla",
    },
    "de": {
        "app_name": "Sadeem Capture",
        "mode_selection": "Auswahl",
        "mode_screen": "Bildschirm",
        "mode_window": "Fenster",
        "tooltip_cursor": "Mauszeiger einbeziehen",
        "tooltip_halo": "Cursor-Halo-Hervorhebung",
        "btn_capture": "Aufnehmen",
        "tab_photo": "Foto",
        "tab_video": "Video",
        "video_phase2_note": "Videoaufnahme wird in Phase 2 verfügbar sein",
        "tooltip_close": "Abbrechen (Esc)",
        "select_hint": "Bereich ziehen und Enter drücken",
        "window_hint": "Auf ein Fenster klicken, um es aufzunehmen",
        "toast_copied": "Bildschirmfoto gespeichert und in die Zwischenablage kopiert",
        "filename_prefix": "Bildschirmfoto",
    },
    "tr": {
        "app_name": "Sadeem Yakalama",
        "mode_selection": "Seçim",
        "mode_screen": "Ekran",
        "mode_window": "Pencere",
        "tooltip_cursor": "İmleci dahil et",
        "tooltip_halo": "İmleç hale efekti",
        "btn_capture": "Yakalama",
        "tab_photo": "Fotoğraf",
        "tab_video": "Video",
        "video_phase2_note": "Video kaydı Faz 2'de mevcut olacak",
        "tooltip_close": "İptal (Esc)",
        "select_hint": "Bir alan seçmek için sürükleyin, ardından Enter'a basın",
        "window_hint": "Hemen yakalamak için herhangi bir pencereye tıklayın",
        "toast_copied": "Ekran görüntüsü kaydedildi ve panoya kopyalandı",
        "filename_prefix": "Ekran_Goruntusu",
    },
    "ru": {
        "app_name": "Снимок Sadeem",
        "mode_selection": "Область",
        "mode_screen": "Экран",
        "mode_window": "Окно",
        "tooltip_cursor": "Включить курсор",
        "tooltip_halo": "Ореол вокруг курсора",
        "btn_capture": "Снимок",
        "tab_photo": "Фото",
        "tab_video": "Видео",
        "video_phase2_note": "Запись видео появится на этапе 2",
        "tooltip_close": "Отмена (Esc)",
        "select_hint": "Выделите область и нажмите Enter или кнопку снимка",
        "window_hint": "Нажмите на окно для быстрого снимка",
        "toast_copied": "Снимок экрана сохранен и скопирован в буфер",
        "filename_prefix": "Snimok_ekrana",
    },
    "pt": {
        "app_name": "Captura Sadeem",
        "mode_selection": "Seleção",
        "mode_screen": "Ecrã",
        "mode_window": "Janela",
        "tooltip_cursor": "Incluir cursor",
        "tooltip_halo": "Destaque de auréola do cursor",
        "btn_capture": "Capturar",
        "tab_photo": "Fotografia",
        "tab_video": "Vídeo",
        "video_phase2_note": "A gravação de vídeo estará disponível na Fase 2",
        "tooltip_close": "Cancelar (Esc)",
        "select_hint": "Arraste para selecionar uma área e prima Enter",
        "window_hint": "Clique em qualquer janela para capturar",
        "toast_copied": "Captura guardada e copiada para a área de transferência",
        "filename_prefix": "Captura_de_ecra",
    },
    "it": {
        "app_name": "Cattura Sadeem",
        "mode_selection": "Selezione",
        "mode_screen": "Schermo",
        "mode_window": "Finestra",
        "tooltip_cursor": "Includi cursore",
        "tooltip_halo": "Effetto alone del cursore",
        "btn_capture": "Cattura",
        "tab_photo": "Foto",
        "tab_video": "Video",
        "video_phase2_note": "La registrazione video sarà disponibile nella Fase 2",
        "tooltip_close": "Annulla (Esc)",
        "select_hint": "Trascina per selezionare un'area e premi Invio",
        "window_hint": "Fai clic su una finestra per catturarla subito",
        "toast_copied": "Schermata salvata e copiata negli appunti",
        "filename_prefix": "Schermata",
    },
    "zh": {
        "app_name": "Sadeem 截图",
        "mode_selection": "选区",
        "mode_screen": "全屏",
        "mode_window": "窗口",
        "tooltip_cursor": "包含鼠标指针",
        "tooltip_halo": "鼠标光环高亮",
        "btn_capture": "截取",
        "tab_photo": "照片",
        "tab_video": "录屏",
        "video_phase2_note": "录屏功能将在第二阶段推出",
        "tooltip_close": "取消 (Esc)",
        "select_hint": "拖拽选定区域后按回车或截取按钮",
        "window_hint": "点击任意窗口立即截取",
        "toast_copied": "截图已保存并复制到剪贴板",
        "filename_prefix": "Jietu",
    },
}


def t(key, **kwargs):
    bundle = STRINGS.get(LANG, STRINGS["ar"])
    pattern = bundle.get(key) or STRINGS["en"].get(key) or STRINGS["ar"].get(key, key)
    if kwargs:
        try:
            return pattern.format(**kwargs)
        except Exception:
            return pattern
    return pattern
