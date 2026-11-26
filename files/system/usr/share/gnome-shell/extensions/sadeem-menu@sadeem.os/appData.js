// appData.js - Application indexing, Unified 2D Free Board & Compact Foldable Groups model,
// strict Games exclusion filter, smart groups, and user-scoped seen-apps state.
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import * as I18n from './i18n.js';
import * as TileLayout from './tileLayout.js';

export const QUICK_PINS_GROUP_ID = 'quick_pins';
export const SMART_GROUP_ORDER = ['sadeem', 'office', 'games', 'social'];

export const SMART_GROUP_DEFS = {
    sadeem: { id: 'sadeem', titleKey: 'group_sadeem' },
    office: { id: 'office', titleKey: 'group_office' },
    games: { id: 'games', titleKey: 'group_games' },
    social: { id: 'social', titleKey: 'group_social' },
};

const OFFICE_CATEGORIES = new Set([
    'office',
    'wordprocessor',
    'spreadsheet',
    'presentation',
    'publishing',
    'calendar',
    'finance',
    'projectmanagement',
]);

const GAME_CATEGORIES = new Set([
    'game',
    'actiongame',
    'adventuregame',
    'arcadegame',
    'boardgame',
    'blocksgame',
    'cardgame',
    'kidsgame',
    'logicgame',
    'roleplaying',
    'shooter',
    'simulation',
    'sportsgame',
    'strategygame',
]);

// Launchers, compatibility runners, and utilities that must NEVER appear in Games
const GAME_TOOL_EXCLUSIONS = [
    'bottles',
    'usebottles',
    'pupgui',
    'protonup',
    'boxbuddy',
    'winetricks',
    'protontricks',
    'gamemode',
    'mangohud',
    'goverlay',
    'vkbasalt',
    'lutris',
    'heroic',
    'cartridges',
    'retroarch',
    'flatseal',
    'gearlever',
    'sadeem-windows-exe-handler',
];

const GAME_CONFLICTING_CATEGORIES = new Set([
    'utility',
    'system',
    'settings',
    'packagemanager',
    'development',
]);

const SOCIAL_CATEGORIES = new Set([
    'instantmessaging',
    'chat',
    'email',
    'videoconference',
    'telephony',
    'ircclient',
    'news',
]);

const SOCIAL_KEYWORDS = [
    'telegram',
    'zapfast',
    'whatsapp',
    'discord',
    'thunderbird',
    'signal',
    'vesktop',
    'element',
    'slack',
    'zoom',
    'viber',
    'teams',
    'geary',
    'betterbird',
    'mattermost',
    'pidgin',
    'hexchat',
];

const OFFICE_KEYWORDS = [
    'libreoffice',
    'onlyoffice',
    'wps-',
    'calligra',
    'abiword',
    'gnumeric',
    'gnucash',
];

const GAME_KEYWORDS = [
    'minecraft',
    'prismlauncher',
    'minetest',
    'supertux',
    'xonotic',
    '0ad',
];

const FALLBACK_BROWSER_IDS = [
    'org.mozilla.firefox.desktop',
    'firefox.desktop',
    'org.chromium.Chromium.desktop',
    'google-chrome.desktop',
    'brave-browser.desktop',
];

const CORE_DEFAULT_LOOSE_OTHERS = [
    'org.gnome.Nautilus.desktop',
    'org.gnome.Software.desktop',
    'org.gnome.TextEditor.desktop',
];

try {
    Gio._promisify(Gio.File.prototype, 'load_contents_async', 'load_contents_finish');
    Gio._promisify(Gio.File.prototype, 'replace_contents_async', 'replace_contents_finish');
    Gio._promisify(Gio.File.prototype, 'query_info_async', 'query_info_finish');
} catch (_e) {}

export function isUserScopedAppPath(filename, homeDir = null) {
    if (!filename || typeof filename !== 'string')
        return false;

    const home = (homeDir || GLib.get_home_dir() || '').replace(/\/+$/, '');
    const normalized = filename.replace(/\/+/g, '/');

    if (home) {
        if (normalized.startsWith(`${home}/.local/share/applications/`))
            return true;
        if (normalized.startsWith(`${home}/.local/share/flatpak/exports/share/applications/`))
            return true;
    }

    if (normalized.startsWith('/var/lib/flatpak/exports/share/applications/'))
        return true;

    return false;
}

export function extractAppRecord(shellApp) {
    if (!shellApp)
        return null;

    const appInfo = typeof shellApp.get_app_info === 'function' ? shellApp.get_app_info() : shellApp;
    if (!appInfo)
        return null;

    if (typeof appInfo.should_show === 'function' && !appInfo.should_show())
        return null;

    const id = typeof shellApp.get_id === 'function'
        ? shellApp.get_id()
        : (typeof appInfo.get_id === 'function' ? appInfo.get_id() : '');
    if (!id)
        return null;

    const name = (typeof shellApp.get_name === 'function' ? shellApp.get_name() : null)
        || (typeof appInfo.get_display_name === 'function' ? appInfo.get_display_name() : null)
        || (typeof appInfo.get_name === 'function' ? appInfo.get_name() : null)
        || id;

    let untranslatedName = name;
    try {
        if (typeof appInfo.get_string === 'function')
            untranslatedName = appInfo.get_string('Name') || name;
    } catch (_e) {}

    const description = (typeof appInfo.get_description === 'function' ? appInfo.get_description() : '') || '';
    let keywords = [];
    try {
        if (typeof appInfo.get_keywords === 'function')
            keywords = appInfo.get_keywords() || [];
    } catch (_e) {}

    let categories = [];
    try {
        const catStr = typeof appInfo.get_categories === 'function' ? appInfo.get_categories() : '';
        if (catStr)
            categories = catStr.split(';').map(s => s.trim()).filter(Boolean);
    } catch (_e) {}

    let exec = '';
    try {
        exec = (typeof appInfo.get_executable === 'function' ? appInfo.get_executable() : '')
            || (typeof appInfo.get_commandline === 'function' ? appInfo.get_commandline() : '')
            || '';
    } catch (_e) {}

    const filename = typeof appInfo.get_filename === 'function' ? (appInfo.get_filename() || '') : '';

    return {
        id,
        name,
        untranslatedName,
        description,
        keywords,
        categories,
        exec,
        filename,
        isUserScoped: isUserScopedAppPath(filename),
        shellApp: typeof shellApp.launch === 'function' ? shellApp : null,
        appInfo,
    };
}

export function isGameUtilityExcluded(record) {
    if (!record || !record.id)
        return true;

    const idLow = record.id.toLowerCase();
    const nameLow = (record.untranslatedName || record.name || '').toLowerCase();
    const execLow = (record.exec || '').toLowerCase();
    const catsLow = new Set((record.categories || []).map(c => c.toLowerCase()));
    const isWindowsGameShortcut = idLow.startsWith('sadeem-win-') && catsLow.has('game');

    if (idLow === 'sadeem-windows-exe-handler.desktop')
        return true;

    for (const token of GAME_TOOL_EXCLUSIONS) {
        if (idLow.includes(token) || nameLow.includes(token))
            return true;
        if (!isWindowsGameShortcut && execLow.includes(token))
            return true;
    }

    if ([...catsLow].some(c => GAME_CONFLICTING_CATEGORIES.has(c)))
        return true;

    return false;
}

export function classifySmartGroup(record) {
    if (!record || !record.id)
        return [];

    const idLow = record.id.toLowerCase();
    const nameLow = (record.untranslatedName || record.name || '').toLowerCase();
    const execLow = (record.exec || '').toLowerCase();
    const catsLow = new Set((record.categories || []).map(c => c.toLowerCase()));
    const matched = [];

    const isWindowsShortcut = idLow.startsWith('sadeem-win-');
    const isWindowsHandler = idLow === 'sadeem-windows-exe-handler.desktop';
    if (
        !isWindowsShortcut && !isWindowsHandler && (
            idLow.startsWith('org.sadeem.') ||
            idLow.startsWith('sadeem-') ||
            idLow.includes('rumman') ||
            execLow.includes('/sadeem-')
        )
    ) {
        matched.push('sadeem');
    }

    if (
        [...catsLow].some(c => OFFICE_CATEGORIES.has(c)) ||
        OFFICE_KEYWORDS.some(k => idLow.includes(k) || nameLow.includes(k))
    ) {
        matched.push('office');
    }

    const matchesGameSignal = [...catsLow].some(c => GAME_CATEGORIES.has(c))
        || GAME_KEYWORDS.some(k => idLow.includes(k) || nameLow.includes(k));
    if (matchesGameSignal && !isGameUtilityExcluded(record))
        matched.push('games');

    if (
        [...catsLow].some(c => SOCIAL_CATEGORIES.has(c)) ||
        SOCIAL_KEYWORDS.some(k => idLow.includes(k) || nameLow.includes(k) || execLow.includes(k))
    ) {
        matched.push('social');
    }

    return matched;
}

function normalizeGroupApps(rawApps) {
    if (!Array.isArray(rawApps))
        return [];
    const seen = new Set();
    const out = [];
    for (const entry of rawApps) {
        const id = typeof entry === 'string'
            ? entry
            : (entry && typeof entry === 'object' && typeof entry.id === 'string' ? entry.id : '');
        if (id && !seen.has(id)) {
            seen.add(id);
            out.push({ id });
        }
    }
    return out;
}

function normalizeBoardItems(rawItems) {
    if (!Array.isArray(rawItems))
        return [];
    const out = [];
    const seenLooseApps = new Set();
    const seenGroups = new Set();

    for (const entry of rawItems) {
        if (!entry || typeof entry !== 'object')
            continue;

        if (entry.type === 'group') {
            const gid = typeof entry.id === 'string' && entry.id ? entry.id : '';
            if (!gid || seenGroups.has(gid))
                continue;
            seenGroups.add(gid);
            const gObj = {
                type: 'group',
                id: gid,
                name: typeof entry.name === 'string' ? entry.name : null,
                cardSize: TileLayout.normalizeGroupCardSize(entry.cardSize),
                apps: normalizeGroupApps(entry.apps),
            };
            if (Number.isInteger(entry.col) && entry.col >= 0)
                gObj.col = entry.col;
            if (Number.isInteger(entry.row) && entry.row >= 0)
                gObj.row = entry.row;
            out.push(gObj);
            continue;
        }

        const appId = typeof entry.id === 'string' && entry.id ? entry.id : '';
        if (!appId || seenLooseApps.has(appId))
            continue;
        seenLooseApps.add(appId);
        const aObj = {
            type: 'app',
            id: appId,
        };
        if (Number.isInteger(entry.col) && entry.col >= 0)
            aObj.col = entry.col;
        if (Number.isInteger(entry.row) && entry.row >= 0)
            aObj.row = entry.row;
        out.push(aObj);
    }

    return out;
}

export function parseLayoutConfig(layoutJson) {
    let raw = {};
    if (typeof layoutJson === 'string' && layoutJson.trim()) {
        try {
            const parsed = JSON.parse(layoutJson);
            if (parsed && typeof parsed === 'object' && !Array.isArray(parsed))
                raw = parsed;
        } catch (_e) {
            raw = {};
        }
    }

    const removedGroups = Array.isArray(raw.removed_groups)
        ? [...new Set(raw.removed_groups.filter(x => typeof x === 'string' && x))]
        : [];
    const excludedApps = Array.isArray(raw.excluded_apps)
        ? [...new Set(raw.excluded_apps.filter(x => typeof x === 'string' && x))]
        : [];

    const excludedFromGroup = {};
    if (raw.excluded_from_group && typeof raw.excluded_from_group === 'object') {
        for (const [gid, arr] of Object.entries(raw.excluded_from_group)) {
            if (Array.isArray(arr))
                excludedFromGroup[gid] = [...new Set(arr.filter(x => typeof x === 'string' && x))];
        }
    }

    const nextGroupCounter = Number.isInteger(raw.next_group_counter) && raw.next_group_counter >= 1
        ? raw.next_group_counter
        : 1;

    if (raw.version === 2 && Array.isArray(raw.board_items)) {
        return {
            version: 2,
            board_initialized: Boolean(raw.board_initialized),
            board_items: normalizeBoardItems(raw.board_items),
            removed_groups: removedGroups,
            excluded_apps: excludedApps,
            excluded_from_group: excludedFromGroup,
            next_group_counter: nextGroupCounter,
        };
    }

    // Migrate custom groups & quick_pins items seamlessly from legacy v1 payloads if present
    const migrated = [];
    let hasLegacyCustomData = false;
    if (raw.groups && typeof raw.groups === 'object') {
        const qp = raw.groups[QUICK_PINS_GROUP_ID];
        if (qp && Array.isArray(qp.items)) {
            for (const it of qp.items) {
                if (it?.type === 'app' && it.id) {
                    migrated.push({ type: 'app', id: it.id });
                    hasLegacyCustomData = true;
                } else if (it?.type === 'folder' && it.id && Array.isArray(it.apps) && it.apps.length > 0) {
                    migrated.push({
                        type: 'group',
                        id: it.id,
                        name: typeof it.name === 'string' ? it.name : '',
                        cardSize: '2x2',
                        apps: normalizeGroupApps(it.apps),
                    });
                    hasLegacyCustomData = true;
                }
            }
        }
        for (const [gid, gobj] of Object.entries(raw.groups)) {
            if (!gid || gid === QUICK_PINS_GROUP_ID || !gobj || typeof gobj !== 'object')
                continue;
            const rawApps = [];
            for (const it of (gobj.items || gobj.apps || [])) {
                if (it?.type === 'app' && it.id)
                    rawApps.push({ id: it.id });
                else if (it?.type === 'folder' && Array.isArray(it.apps))
                    rawApps.push(...normalizeGroupApps(it.apps));
            }
            if (rawApps.length > 0 || gid.startsWith('custom_')) {
                migrated.push({
                    type: 'group',
                    id: gid,
                    name: typeof gobj.name === 'string' ? gobj.name : null,
                    cardSize: '2x2',
                    apps: normalizeGroupApps(rawApps),
                });
                hasLegacyCustomData = true;
            }
        }
    }

    return {
        version: 2,
        board_initialized: hasLegacyCustomData,
        board_items: normalizeBoardItems(migrated),
        removed_groups: removedGroups,
        excluded_apps: excludedApps,
        excluded_from_group: excludedFromGroup,
        next_group_counter: nextGroupCounter,
    };
}

export function serializeLayoutConfig(config) {
    return JSON.stringify(config);
}

function getDefaultBrowserId(recordsById) {
    try {
        const def = Gio.AppInfo.get_default_for_type('x-scheme-handler/https', false);
        const id = def?.get_id?.();
        if (id && recordsById.has(id))
            return id;
    } catch (_e) {}

    for (const fid of FALLBACK_BROWSER_IDS) {
        if (recordsById.has(fid))
            return fid;
    }
    return null;
}

function buildDefaultLooseApps(recordsById) {
    const out = [];
    const seen = new Set();
    const browserId = getDefaultBrowserId(recordsById);
    if (browserId) {
        seen.add(browserId);
        out.push(browserId);
    }
    for (const id of CORE_DEFAULT_LOOSE_OTHERS) {
        if (recordsById.has(id) && !seen.has(id)) {
            seen.add(id);
            out.push(id);
        }
    }
    return out;
}

function buildSmartRecordsMap(records, config) {
    const excludedGlobal = new Set(config.excluded_apps);
    const map = new Map();
    for (const sid of SMART_GROUP_ORDER)
        map.set(sid, []);

    for (const rec of records) {
        if (excludedGlobal.has(rec.id))
            continue;
        for (const sid of classifySmartGroup(rec)) {
            const excludedGrp = new Set(config.excluded_from_group[sid] || []);
            if (!excludedGrp.has(rec.id))
                map.get(sid)?.push(rec);
        }
    }

    for (const [sid, arr] of map.entries())
        arr.sort((a, b) => a.name.localeCompare(b.name));

    return map;
}

function materializeBoardConfig(config, records, recordsById, autoCategorize = true) {
    const removedSet = new Set(config.removed_groups);
    const excludedGlobal = new Set(config.excluded_apps);

    // Seed initial unified 2D Free Board cleanly on first run:
    // Row 0: 1x1 loose core apps; Row 1..2: compact 2x2 foldable smart groups
    if (!config.board_initialized && config.board_items.length === 0) {
        const defaults = buildDefaultLooseApps(recordsById).filter(id => !excludedGlobal.has(id));
        defaults.forEach((id, idx) => {
            config.board_items.push({
                type: 'app',
                id,
                col: idx,
                row: 0,
            });
        });

        if (autoCategorize) {
            const smartMap = buildSmartRecordsMap(records, config);
            let smartColOffset = 0;
            for (const sid of SMART_GROUP_ORDER) {
                if (removedSet.has(sid))
                    continue;
                const matched = smartMap.get(sid) || [];
                if (matched.length === 0)
                    continue;
                config.board_items.push({
                    type: 'group',
                    id: sid,
                    name: null,
                    cardSize: '2x2',
                    col: smartColOffset,
                    row: defaults.length > 0 ? 1 : 0,
                    apps: matched.map(r => ({ id: r.id })),
                });
                smartColOffset += 2;
            }
        }
        config.board_initialized = true;
    }

    if (autoCategorize) {
        const smartMap = buildSmartRecordsMap(records, config);
        for (const sid of SMART_GROUP_ORDER) {
            if (removedSet.has(sid))
                continue;
            const matched = smartMap.get(sid) || [];
            if (matched.length === 0)
                continue;

            let grp = config.board_items.find(it => it.type === 'group' && it.id === sid);
            if (!grp) {
                grp = {
                    type: 'group',
                    id: sid,
                    name: null,
                    cardSize: '2x2',
                    apps: [],
                };
                config.board_items.push(grp);
            }
            const existingIds = new Set(grp.apps.map(a => a.id));
            for (const rec of matched) {
                if (!existingIds.has(rec.id)) {
                    existingIds.add(rec.id);
                    grp.apps.push({ id: rec.id });
                }
            }
        }
    }

    return config;
}

export function computeTileBoardModel({ records, layoutJson = '{}', autoCategorize = true, disabledSmartGroups = [] }) {
    const config = parseLayoutConfig(layoutJson);
    const recordsById = new Map(records.map(r => [r.id, r]));
    const removedSet = new Set(config.removed_groups);
    const disabledSet = new Set(Array.isArray(disabledSmartGroups) ? disabledSmartGroups : []);

    materializeBoardConfig(config, records, recordsById, autoCategorize);

    const items = [];
    const groups = [];
    const allGroups = [];

    for (const rawItem of config.board_items) {
        if (rawItem.type === 'group') {
            if (removedSet.has(rawItem.id))
                continue;

            const isSmart = Boolean(SMART_GROUP_DEFS[rawItem.id]);
            if (isSmart && (!autoCategorize || disabledSet.has(rawItem.id)))
                continue;
            const resolvedApps = [];
            const seenAppIds = new Set();
            for (const a of rawItem.apps) {
                if (seenAppIds.has(a.id))
                    continue;
                const rec = recordsById.get(a.id);
                if (rec) {
                    seenAppIds.add(rec.id);
                    resolvedApps.push({ id: rec.id, record: rec });
                }
            }

            const displayName = (typeof rawItem.name === 'string' && rawItem.name.trim())
                ? rawItem.name.trim()
                : (isSmart ? I18n.t(SMART_GROUP_DEFS[rawItem.id].titleKey) : '');

            const groupObj = {
                type: 'group',
                id: rawItem.id,
                name: displayName,
                rawName: rawItem.name,
                cardSize: TileLayout.normalizeGroupCardSize(rawItem.cardSize),
                isSmart,
                apps: resolvedApps,
            };
            if (Number.isInteger(rawItem.col) && rawItem.col >= 0)
                groupObj.col = rawItem.col;
            if (Number.isInteger(rawItem.row) && rawItem.row >= 0)
                groupObj.row = rawItem.row;

            allGroups.push(groupObj);
            // Omit empty smart groups while keeping explicit custom groups
            if (resolvedApps.length > 0 || !isSmart) {
                items.push(groupObj);
                groups.push(groupObj);
            }
            continue;
        }

        const rec = recordsById.get(rawItem.id);
        if (!rec)
            continue;
        const appObj = {
            type: 'app',
            id: rec.id,
            record: rec,
        };
        if (Number.isInteger(rawItem.col) && rawItem.col >= 0)
            appObj.col = rawItem.col;
        if (Number.isInteger(rawItem.row) && rawItem.row >= 0)
            appObj.row = rawItem.row;
        items.push(appObj);
    }

    return {
        config,
        items,
        boardItems: items,
        groups,
        allGroups,
    };
}

export const computeUnifiedBoardModel = computeTileBoardModel;

function removeAppFromBoardGroupInternal(config, groupId, appId) {
    const idx = config.board_items.findIndex(it => it.type === 'group' && it.id === groupId);
    if (idx < 0)
        return false;

    const grp = config.board_items[idx];
    const beforeLen = grp.apps.length;
    grp.apps = grp.apps.filter(a => a.id !== appId);
    if (grp.apps.length === beforeLen)
        return false;

    if (SMART_GROUP_DEFS[groupId]) {
        const ex = config.excluded_from_group[groupId] || [];
        if (!ex.includes(appId))
            ex.push(appId);
        config.excluded_from_group[groupId] = ex;
    }

    // Prune smart group if emptied completely (and remember removal so it stays hidden),
    // or prune unnamed custom group once completely empty
    if (grp.apps.length === 0) {
        if (SMART_GROUP_DEFS[groupId]) {
            config.board_items.splice(idx, 1);
            if (!config.removed_groups.includes(groupId))
                config.removed_groups.push(groupId);
        } else if (!(grp.name || '').trim()) {
            config.board_items.splice(idx, 1);
        }
    }

    return true;
}

function unexcludeInGroup(config, groupId, appId) {
    config.excluded_apps = config.excluded_apps.filter(id => id !== appId);
    if (groupId && config.excluded_from_group[groupId])
        config.excluded_from_group[groupId] = config.excluded_from_group[groupId].filter(id => id !== appId);
    if (groupId)
        config.removed_groups = config.removed_groups.filter(id => id !== groupId);
}

export function mutateLayoutPlaceBoardItem(
    layoutJson,
    {
        itemType = 'app',
        itemId,
        sourceGroupId = null,
        targetCol = null,
        targetRow = null,
        records = [],
        autoCategorize = true,
    }
) {
    if (!itemId)
        return layoutJson;

    const hasExplicitTarget = (
        Number.isInteger(targetCol) && targetCol >= 0
        && Number.isInteger(targetRow) && targetRow >= 0
    );

    const config = parseLayoutConfig(layoutJson);
    const recordsById = new Map(records.map(r => [r.id, r]));
    materializeBoardConfig(config, records, recordsById, autoCategorize);

    if (itemType === 'group') {
        if (!hasExplicitTarget)
            return serializeLayoutConfig(config);
        const key = `group:${itemId}`;
        config.board_items = TileLayout.placeBoardItemAt(config.board_items, key, targetCol, targetRow);
        return serializeLayoutConfig(config);
    }

    if (sourceGroupId)
        removeAppFromBoardGroupInternal(config, sourceGroupId, itemId);

    config.excluded_apps = config.excluded_apps.filter(id => id !== itemId);
    let loose = config.board_items.find(it => it.type === 'app' && it.id === itemId);

    if (!hasExplicitTarget) {
        if (!loose) {
            loose = { type: 'app', id: itemId };
            config.board_items.push(loose);
        }
        if (!Number.isInteger(loose.col) || loose.col < 0 || !Number.isInteger(loose.row) || loose.row < 0) {
            const packed = TileLayout.computeUnifiedBoardRects(config.board_items);
            const placed = packed.rects.find(r => r.item?.type === 'app' && r.item?.id === itemId);
            if (placed) {
                loose.col = placed.col;
                loose.row = placed.row;
            }
        }
        return serializeLayoutConfig(config);
    }

    if (!loose) {
        loose = { type: 'app', id: itemId, col: targetCol, row: targetRow };
        config.board_items.push(loose);
    }

    config.board_items = TileLayout.placeBoardItemAt(
        config.board_items,
        `app:${itemId}`,
        targetCol,
        targetRow
    );
    return serializeLayoutConfig(config);
}

export function mutateLayoutMergeAppsIntoGroup(
    layoutJson,
    {
        targetAppId,
        sourceAppId,
        sourceGroupId = null,
        targetCol = null,
        targetRow = null,
        name = '',
        records = [],
        autoCategorize = true,
    }
) {
    if (!targetAppId || !sourceAppId || targetAppId === sourceAppId)
        return { layoutJson, groupId: null };

    const config = parseLayoutConfig(layoutJson);
    const recordsById = new Map(records.map(r => [r.id, r]));
    materializeBoardConfig(config, records, recordsById, autoCategorize);

    const targetIdx = config.board_items.findIndex(it => it.type === 'app' && it.id === targetAppId);
    if (targetIdx < 0)
        return { layoutJson: serializeLayoutConfig(config), groupId: null };

    const targetItem = config.board_items[targetIdx];
    const resolvedCol = Number.isInteger(targetCol) ? targetCol : (targetItem.col ?? 0);
    const resolvedRow = Number.isInteger(targetRow) ? targetRow : (targetItem.row ?? 0);

    const newGroupId = `custom_${config.next_group_counter}`;
    config.next_group_counter += 1;

    config.board_items[targetIdx] = {
        type: 'group',
        id: newGroupId,
        name: typeof name === 'string' ? name.trim() : '',
        cardSize: '2x2',
        col: resolvedCol,
        row: resolvedRow,
        apps: [{ id: targetAppId }, { id: sourceAppId }],
    };

    if (sourceGroupId)
        removeAppFromBoardGroupInternal(config, sourceGroupId, sourceAppId);
    else
        config.board_items = config.board_items.filter(it => !(it.type === 'app' && it.id === sourceAppId));

    config.board_items = TileLayout.placeBoardItemAt(
        config.board_items,
        `group:${newGroupId}`,
        resolvedCol,
        resolvedRow
    );

    return {
        layoutJson: serializeLayoutConfig(config),
        groupId: newGroupId,
    };
}

export function mutateLayoutAddAppToGroupItem(
    layoutJson,
    {
        targetGroupId,
        appId,
        sourceGroupId = null,
        removeLoose = false,
        records = [],
        autoCategorize = true,
    }
) {
    if (!targetGroupId || !appId)
        return layoutJson;

    const config = parseLayoutConfig(layoutJson);
    const recordsById = new Map(records.map(r => [r.id, r]));
    materializeBoardConfig(config, records, recordsById, autoCategorize);

    if (sourceGroupId && sourceGroupId !== targetGroupId)
        removeAppFromBoardGroupInternal(config, sourceGroupId, appId);

    if (removeLoose)
        config.board_items = config.board_items.filter(it => !(it.type === 'app' && it.id === appId));

    unexcludeInGroup(config, targetGroupId, appId);

    let grp = config.board_items.find(it => it.type === 'group' && it.id === targetGroupId);
    if (!grp) {
        grp = {
            type: 'group',
            id: targetGroupId,
            name: SMART_GROUP_DEFS[targetGroupId] ? null : '',
            cardSize: '2x2',
            apps: [],
        };
        config.board_items.push(grp);
    }

    if (!grp.apps.some(a => a.id === appId))
        grp.apps.push({ id: appId });

    return serializeLayoutConfig(config);
}

export function mutateLayoutExtractAppToBoard(
    layoutJson,
    {
        groupId,
        appId,
        targetCol = null,
        targetRow = null,
        records = [],
        autoCategorize = true,
    }
) {
    if (!groupId || !appId)
        return layoutJson;

    const config = parseLayoutConfig(layoutJson);
    const recordsById = new Map(records.map(r => [r.id, r]));
    materializeBoardConfig(config, records, recordsById, autoCategorize);

    removeAppFromBoardGroupInternal(config, groupId, appId);
    config.excluded_apps = config.excluded_apps.filter(id => id !== appId);

    const hasLoose = config.board_items.some(it => it.type === 'app' && it.id === appId);
    if (!hasLoose)
        config.board_items.push({ type: 'app', id: appId });

    if (Number.isInteger(targetCol) && targetCol >= 0 && Number.isInteger(targetRow) && targetRow >= 0) {
        config.board_items = TileLayout.placeBoardItemAt(
            config.board_items,
            `app:${appId}`,
            targetCol,
            targetRow
        );
    } else {
        const packed = TileLayout.computeUnifiedBoardRects(config.board_items);
        const looseRect = packed.rects.find(r => r.item?.type === 'app' && r.item?.id === appId);
        if (looseRect) {
            config.board_items = TileLayout.placeBoardItemAt(
                config.board_items,
                `app:${appId}`,
                looseRect.col,
                looseRect.row
            );
        }
    }

    return serializeLayoutConfig(config);
}

export function mutateLayoutRemoveAppFromBoardGroup(
    layoutJson,
    { groupId, appId, records = [], autoCategorize = true }
) {
    if (!groupId || !appId)
        return layoutJson;
    const config = parseLayoutConfig(layoutJson);
    const recordsById = new Map(records.map(r => [r.id, r]));
    materializeBoardConfig(config, records, recordsById, autoCategorize);
    removeAppFromBoardGroupInternal(config, groupId, appId);
    return serializeLayoutConfig(config);
}

export function mutateLayoutRemoveLooseApp(
    layoutJson,
    { appId, records = [], autoCategorize = true }
) {
    if (!appId)
        return layoutJson;
    const config = parseLayoutConfig(layoutJson);
    const recordsById = new Map(records.map(r => [r.id, r]));
    materializeBoardConfig(config, records, recordsById, autoCategorize);
    config.board_items = config.board_items.filter(it => !(it.type === 'app' && it.id === appId));
    return serializeLayoutConfig(config);
}

export function mutateLayoutSetGroupCardSize(
    layoutJson,
    { groupId, cardSize, records = [], autoCategorize = true }
) {
    if (!groupId)
        return layoutJson;
    const config = parseLayoutConfig(layoutJson);
    const recordsById = new Map(records.map(r => [r.id, r]));
    materializeBoardConfig(config, records, recordsById, autoCategorize);

    const grp = config.board_items.find(it => it.type === 'group' && it.id === groupId);
    if (!grp)
        return serializeLayoutConfig(config);

    grp.cardSize = TileLayout.normalizeGroupCardSize(cardSize);
    const packed = TileLayout.computeUnifiedBoardRects(config.board_items);
    const rect = packed.rects.find(r => r.key === `group:${groupId}`);
    if (rect) {
        config.board_items = TileLayout.placeBoardItemAt(
            config.board_items,
            `group:${groupId}`,
            rect.col,
            rect.row
        );
    }

    return serializeLayoutConfig(config);
}

export function mutateLayoutCreateGroup(
    layoutJson,
    name = '',
    targetCol = null,
    targetRow = null,
    records = [],
    autoCategorize = true
) {
    const config = parseLayoutConfig(layoutJson);
    const recordsById = new Map(records.map(r => [r.id, r]));
    materializeBoardConfig(config, records, recordsById, autoCategorize);

    const newId = `custom_${config.next_group_counter}`;
    config.next_group_counter += 1;

    const grp = {
        type: 'group',
        id: newId,
        name: typeof name === 'string' ? name.trim() : '',
        cardSize: '2x2',
        apps: [],
    };
    if (Number.isInteger(targetCol) && targetCol >= 0)
        grp.col = targetCol;
    if (Number.isInteger(targetRow) && targetRow >= 0)
        grp.row = targetRow;

    config.board_items.push(grp);

    if (Number.isInteger(grp.col) && Number.isInteger(grp.row))
        config.board_items = TileLayout.placeBoardItemAt(config.board_items, `group:${newId}`, grp.col, grp.row);

    return {
        layoutJson: serializeLayoutConfig(config),
        groupId: newId,
    };
}

export function mutateLayoutRenameGroup(
    layoutJson,
    groupId,
    newName,
    records = [],
    autoCategorize = true
) {
    if (!groupId)
        return layoutJson;
    const config = parseLayoutConfig(layoutJson);
    const recordsById = new Map(records.map(r => [r.id, r]));
    materializeBoardConfig(config, records, recordsById, autoCategorize);

    const clean = typeof newName === 'string' ? newName.trim() : '';
    const grp = config.board_items.find(it => it.type === 'group' && it.id === groupId);
    if (grp)
        grp.name = clean;

    return serializeLayoutConfig(config);
}

export function mutateLayoutDeleteGroup(
    layoutJson,
    groupId,
    records = [],
    autoCategorize = true
) {
    if (!groupId)
        return layoutJson;
    const config = parseLayoutConfig(layoutJson);
    const recordsById = new Map(records.map(r => [r.id, r]));
    materializeBoardConfig(config, records, recordsById, autoCategorize);

    config.board_items = config.board_items.filter(it => !(it.type === 'group' && it.id === groupId));
    if (SMART_GROUP_DEFS[groupId] && !config.removed_groups.includes(groupId))
        config.removed_groups.push(groupId);

    return serializeLayoutConfig(config);
}

export function mutateLayoutRestoreSmartGroup(
    layoutJson,
    groupId,
    records = [],
    autoCategorize = true
) {
    if (!groupId || !SMART_GROUP_DEFS[groupId])
        return layoutJson;
    const config = parseLayoutConfig(layoutJson);
    if (!config.removed_groups.includes(groupId))
        return layoutJson;
    config.removed_groups = config.removed_groups.filter(id => id !== groupId);
    const recordsById = new Map(records.map(r => [r.id, r]));
    materializeBoardConfig(config, records, recordsById, autoCategorize);
    return serializeLayoutConfig(config);
}

/**
 * Pure reconciliation of user-scoped/Flatpak seen-apps map.
 */
export function reconcileSeenApps(userRecordsWithMtime, existingState, nowSec) {
    const isFirstRun = existingState === null || existingState === undefined;
    const prevSeen = (!isFirstRun && typeof existingState.apps === 'object') ? existingState.apps : {};
    const nextApps = {};
    let changed = isFirstRun;

    for (const item of userRecordsWithMtime) {
        if (!item?.id || !isUserScopedAppPath(item.filename, item.homeDir))
            continue;

        if (Object.prototype.hasOwnProperty.call(prevSeen, item.id)) {
            nextApps[item.id] = prevSeen[item.id];
        } else {
            const mtime = Number.isFinite(item.mtimeSec) && item.mtimeSec > 0 ? item.mtimeSec : nowSec;
            nextApps[item.id] = isFirstRun ? mtime : nowSec;
            changed = true;
        }
    }

    if (Object.keys(prevSeen).length !== Object.keys(nextApps).length)
        changed = true;

    return {
        state: { version: 1, apps: nextApps },
        changed,
    };
}

export class AppDataManager {
    constructor(settingsOrOpts, legacyOpts = {}) {
        const isOptsObject = Boolean(
            settingsOrOpts
            && typeof settingsOrOpts === 'object'
            && ('settings' in settingsOrOpts || 'appSystem' in settingsOrOpts || 'appUsage' in settingsOrOpts)
        );
        if (isOptsObject) {
            this._settings = settingsOrOpts.settings || null;
            this._appSystem = settingsOrOpts.appSystem || null;
            this._appUsage = settingsOrOpts.appUsage || null;
        } else {
            this._settings = settingsOrOpts || null;
            this._appSystem = legacyOpts?.appSystem || null;
            this._appUsage = legacyOpts?.appUsage || null;
        }
        this._seenStatePath = GLib.build_filenamev([
            GLib.get_user_data_dir(),
            'sadeem-menu',
            'seen-apps.json',
        ]);
        this._seenState = null;
        this._destroyed = false;
    }

    getInstalledRecords() {
        let installed = [];
        try {
            if (this._appSystem && typeof this._appSystem.get_installed === 'function')
                installed = this._appSystem.get_installed() || [];
            else
                installed = Gio.AppInfo.get_all() || [];
        } catch (_e) {
            try {
                installed = Gio.AppInfo.get_all() || [];
            } catch (_e2) {
                installed = [];
            }
        }

        const seen = new Set();
        const records = [];

        for (const appInfo of installed) {
            const id = typeof appInfo?.get_id === 'function' ? appInfo.get_id() : '';
            if (!id || seen.has(id))
                continue;
            const shellApp = this._appSystem?.lookup_app?.(id) || appInfo;
            const rec = extractAppRecord(shellApp);
            if (rec) {
                seen.add(rec.id);
                records.push(rec);
            }
        }

        return records;
    }

    getBoardModel(records = null) {
        const list = records || this.getInstalledRecords();
        let disabledSmartGroups = [];
        try {
            disabledSmartGroups = this._settings.get_strv('disabled-smart-groups') || [];
        } catch (_e) {}
        return computeTileBoardModel({
            records: list,
            layoutJson: this._settings.get_string('layout-config'),
            autoCategorize: this._settings.get_boolean('auto-categorize'),
            disabledSmartGroups,
        });
    }

    getMostUsedRecords(records = null, count = null) {
        const list = records || this.getInstalledRecords();
        const byId = new Map(list.map(r => [r.id, r]));
        const rawCount = count ?? this._settings.get_int('most-used-count');
        const maxCount = TileLayout.clampNumber(Math.round(Number(rawCount) || 3), 1, 4);
        const out = [];

        try {
            const usedApps = this._appUsage.get_most_used() || [];
            for (const app of usedApps) {
                const id = app?.get_id?.();
                const rec = id ? byId.get(id) : null;
                if (rec) {
                    out.push(rec);
                    if (out.length >= maxCount)
                        break;
                }
            }
        } catch (_e) {}

        return out;
    }

    async refreshSeenAppsAsync(records = null) {
        const list = records || this.getInstalledRecords();
        if (this._seenState === null)
            this._seenState = await this._readSeenStateFileAsync();

        if (this._destroyed)
            return [];

        const userRecords = list.filter(r => r.isUserScoped && r.filename);
        const enriched = await Promise.all(
            userRecords.map(async rec => {
                let mtimeSec = 0;
                try {
                    const file = Gio.File.new_for_path(rec.filename);
                    const info = await file.query_info_async(
                        'time::modified',
                        Gio.FileQueryInfoFlags.NONE,
                        GLib.PRIORITY_DEFAULT,
                        null
                    );
                    mtimeSec = Number(info.get_attribute_uint64('time::modified')) || 0;
                } catch (_e) {}
                return {
                    id: rec.id,
                    filename: rec.filename,
                    mtimeSec,
                };
            })
        );

        if (this._destroyed)
            return [];

        const nowSec = Math.floor(Date.now() / 1000);
        const { state, changed } = reconcileSeenApps(enriched, this._seenState, nowSec);
        this._seenState = state;
        if (changed)
            await this._writeSeenStateFileAsync(state);

        return this.getRecentlyInstalledRecords(list);
    }

    getRecentlyInstalledRecords(records = null, count = null) {
        const list = records || this.getInstalledRecords();
        const rawCount = count ?? this._settings.get_int('recently-installed-count');
        const maxCount = TileLayout.clampNumber(Math.round(Number(rawCount) || 3), 1, 4);
        const seenApps = this._seenState?.apps || {};

        const userRecs = list
            .filter(r => r.isUserScoped && Object.prototype.hasOwnProperty.call(seenApps, r.id))
            .sort((a, b) => {
                const diff = (seenApps[b.id] || 0) - (seenApps[a.id] || 0);
                if (diff !== 0)
                    return diff;
                return a.name.localeCompare(b.name);
            });

        return userRecs.slice(0, maxCount);
    }

    async _readSeenStateFileAsync() {
        try {
            const file = Gio.File.new_for_path(this._seenStatePath);
            const [ok, contents] = await file.load_contents_async(null);
            if (!ok || !contents)
                return null;
            const decoded = new TextDecoder().decode(contents);
            const parsed = JSON.parse(decoded);
            if (parsed && typeof parsed === 'object' && typeof parsed.apps === 'object')
                return parsed;
        } catch (_e) {}
        return null;
    }

    async _writeSeenStateFileAsync(state) {
        try {
            const dir = GLib.path_get_dirname(this._seenStatePath);
            GLib.mkdir_with_parents(dir, 0o755);
            const file = Gio.File.new_for_path(this._seenStatePath);
            const bytes = new TextEncoder().encode(JSON.stringify(state));
            await file.replace_contents_async(
                bytes,
                null,
                false,
                Gio.FileCreateFlags.REPLACE_DESTINATION,
                null
            );
        } catch (_e) {}
    }

    _getAutoFlag() {
        return this._settings.get_boolean('auto-categorize');
    }

    _getLayout() {
        return this._settings.get_string('layout-config');
    }

    _setLayout(next) {
        this._settings.set_string('layout-config', next);
    }

    placeBoardItem(params, records = null) {
        const list = records || this.getInstalledRecords();
        this._setLayout(mutateLayoutPlaceBoardItem(this._getLayout(), {
            ...params,
            records: list,
            autoCategorize: this._getAutoFlag(),
        }));
    }

    mergeAppsIntoGroup(params, records = null) {
        const list = records || this.getInstalledRecords();
        const result = mutateLayoutMergeAppsIntoGroup(this._getLayout(), {
            ...params,
            records: list,
            autoCategorize: this._getAutoFlag(),
        });
        if (result?.layoutJson) {
            this._setLayout(result.layoutJson);
            return result.groupId;
        }
        return null;
    }

    addAppToGroup(params, records = null) {
        const list = records || this.getInstalledRecords();
        this._setLayout(mutateLayoutAddAppToGroupItem(this._getLayout(), {
            ...params,
            records: list,
            autoCategorize: this._getAutoFlag(),
        }));
    }

    pinLooseApp(appId, targetCol = null, targetRow = null, records = null) {
        this.placeBoardItem({
            itemType: 'app',
            itemId: appId,
            targetCol,
            targetRow,
        }, records);
    }

    removeLooseApp(appId, records = null) {
        const list = records || this.getInstalledRecords();
        this._setLayout(mutateLayoutRemoveLooseApp(this._getLayout(), {
            appId,
            records: list,
            autoCategorize: this._getAutoFlag(),
        }));
    }

    extractAppToBoard(groupId, appId, targetCol = null, targetRow = null, records = null) {
        const list = records || this.getInstalledRecords();
        this._setLayout(mutateLayoutExtractAppToBoard(this._getLayout(), {
            groupId,
            appId,
            targetCol,
            targetRow,
            records: list,
            autoCategorize: this._getAutoFlag(),
        }));
    }

    removeAppFromGroup(groupId, appId, records = null) {
        const list = records || this.getInstalledRecords();
        this._setLayout(mutateLayoutRemoveAppFromBoardGroup(this._getLayout(), {
            groupId,
            appId,
            records: list,
            autoCategorize: this._getAutoFlag(),
        }));
    }

    setGroupCardSize(groupId, cardSize, records = null) {
        const list = records || this.getInstalledRecords();
        this._setLayout(mutateLayoutSetGroupCardSize(this._getLayout(), {
            groupId,
            cardSize,
            records: list,
            autoCategorize: this._getAutoFlag(),
        }));
    }

    createGroup(name = '', targetCol = null, targetRow = null, records = null) {
        const list = records || this.getInstalledRecords();
        const result = mutateLayoutCreateGroup(
            this._getLayout(),
            name,
            targetCol,
            targetRow,
            list,
            this._getAutoFlag()
        );
        if (result?.layoutJson) {
            this._setLayout(result.layoutJson);
            return result.groupId;
        }
        return null;
    }

    renameGroup(groupId, newName, records = null) {
        const list = records || this.getInstalledRecords();
        this._setLayout(mutateLayoutRenameGroup(
            this._getLayout(),
            groupId,
            newName,
            list,
            this._getAutoFlag()
        ));
    }

    deleteGroup(groupId, records = null) {
        const list = records || this.getInstalledRecords();
        this._setLayout(mutateLayoutDeleteGroup(
            this._getLayout(),
            groupId,
            list,
            this._getAutoFlag()
        ));
    }

    restoreSmartGroup(groupId, records = null) {
        const list = records || this.getInstalledRecords();
        const next = mutateLayoutRestoreSmartGroup(
            this._getLayout(),
            groupId,
            list,
            this._getAutoFlag()
        );
        if (next !== this._getLayout())
            this._setLayout(next);
    }

    resetLayout() {
        this._setLayout('{}');
    }

    destroy() {
        this._destroyed = true;
        this._seenState = null;
        this._appSystem = null;
        this._appUsage = null;
        this._settings = null;
    }
}
