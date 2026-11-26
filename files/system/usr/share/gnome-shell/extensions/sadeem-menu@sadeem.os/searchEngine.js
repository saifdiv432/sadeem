// searchEngine.js - Multilingual Unicode search across installed apps and async Nautilus D-Bus files
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

const NAUTILUS_BUS_NAME = 'org.gnome.Nautilus';
const NAUTILUS_OBJECT_PATH = '/org/gnome/Nautilus/SearchProvider';
const SEARCH_PROVIDER_IFACE = 'org.gnome.Shell.SearchProvider2';

try {
    Gio._promisify(Gio.DBusConnection.prototype, 'call', 'call_finish');
    Gio._promisify(Gio.File.prototype, 'load_contents_async', 'load_contents_finish');
} catch (_e) {}

/**
 * Normalize Unicode text cleanly across all scripts without mangling non-Latin alphabets:
 * - Removes Arabic harakat, Quranic marks, and tatweel
 * - Normalizes Arabic letters: أ إ آ ٱ -> ا , ة -> ه , ى -> ي
 * - Strips combining accents from Latin characters via NFD (e.g., é -> e)
 * - Preserves Cyrillic, CJK, symbols, numbers, and punctuation cleanly
 */
export function normalizeSearchText(input) {
    if (!input || typeof input !== 'string')
        return '';

    let text = input
        // Remove Arabic diacritics and tatweel
        .replace(/[\u064B-\u065F\u0670\u06D6-\u06ED\u0640]/g, '')
        // Normalize common Arabic orthographic variants
        .replace(/[أإآٱ]/g, 'ا')
        .replace(/ة/g, 'ه')
        .replace(/ى/g, 'ي');

    // Decompose and remove combining marks ONLY on Latin characters so Cyrillic/Arabic stays faithful
    text = text.replace(/[\u00C0-\u024F\u1E00-\u1EFFA-Za-z][\u0300-\u036F]*/g, seg =>
        seg.normalize('NFD').replace(/[\u0300-\u036F]/g, '')
    );

    return text.toLowerCase().replace(/\s+/g, ' ').trim();
}

function splitTerms(normalizedQuery) {
    if (!normalizedQuery)
        return [];
    return normalizedQuery.split(' ').filter(Boolean);
}

function splitWords(normalizedStr) {
    if (!normalizedStr)
        return [];
    return normalizedStr.split(/[\s\-_./:()[\]]+/).filter(Boolean);
}

/**
 * Search app records using normalized multilingual matching across:
 * display name, untranslated Name, description, Keywords, Exec, and desktop ID.
 */
export function searchAppRecords(records, rawQuery, limit = 15) {
    const normQuery = normalizeSearchText(rawQuery);
    const terms = splitTerms(normQuery);
    if (terms.length === 0)
        return [];

    const scored = [];
    for (const rec of records) {
        if (!rec)
            continue;

        const nameNorm = normalizeSearchText(rec.name || '');
        const origNorm = normalizeSearchText(rec.untranslatedName || '');
        const descNorm = normalizeSearchText(rec.description || '');
        const kwNorm = normalizeSearchText((rec.keywords || []).join(' '));
        const execNorm = normalizeSearchText(rec.exec || '');
        const idNorm = normalizeSearchText(rec.id || '');

        const combined = `${nameNorm} ${origNorm} ${kwNorm} ${execNorm} ${idNorm} ${descNorm}`;
        if (!terms.every(term => combined.includes(term)))
            continue;

        let score = 0;
        const primaryWords = [...splitWords(nameNorm), ...splitWords(origNorm)];

        if (nameNorm === normQuery || origNorm === normQuery)
            score += 1000;
        else if (nameNorm.startsWith(normQuery) || origNorm.startsWith(normQuery))
            score += 600;
        else if (terms.every(term => primaryWords.some(w => w.startsWith(term))))
            score += 400;
        else if (nameNorm.includes(normQuery) || origNorm.includes(normQuery))
            score += 260;

        if (terms.every(term => nameNorm.includes(term) || origNorm.includes(term)))
            score += 180;
        if (terms.some(term => kwNorm.includes(term) || execNorm.includes(term) || idNorm.includes(term)))
            score += 90;
        if (terms.some(term => descNorm.includes(term)))
            score += 40;

        scored.push({ record: rec, score });
    }

    scored.sort((a, b) => {
        if (b.score !== a.score)
            return b.score - a.score;
        return (a.record.name || '').localeCompare(b.record.name || '');
    });

    return scored.slice(0, limit).map(s => s.record);
}

/**
 * Filter recent XBEL bookmark URIs without blocking the main loop.
 */
export function filterBookmarkUris(uris, bookmarkFile, terms, maxCount = 6) {
    const matches = [];
    for (const uri of uris) {
        if (!uri)
            continue;
        let decoded = uri;
        try {
            decoded = decodeURIComponent(uri);
        } catch (_e) {}

        const normUri = normalizeSearchText(decoded);
        if (!terms.every(term => normUri.includes(term)))
            continue;

        let displayName = '';
        try {
            displayName = GLib.path_get_basename(decoded.replace(/^file:\/\//, ''));
        } catch (_e) {
            displayName = decoded;
        }

        let mime = '';
        try {
            mime = bookmarkFile.get_mime_type(uri) || '';
        } catch (_e) {}

        let parentPath = '';
        try {
            if (decoded.startsWith('file://'))
                parentPath = GLib.path_get_dirname(decoded.slice(7));
        } catch (_e) {}

        matches.push({
            id: uri,
            uri,
            name: displayName || uri,
            description: parentPath,
            mimeType: mime,
            gicon: mime ? Gio.content_type_get_icon(mime) : Gio.Icon.new_for_string('text-x-generic'),
            source: 'recent',
        });

        if (matches.length >= maxCount)
            break;
    }
    return matches;
}

export class SearchEngine {
    constructor() {
        this._activeCancellable = null;
        this._destroyed = false;
    }

    cancelPending() {
        if (this._activeCancellable) {
            this._activeCancellable.cancel();
            this._activeCancellable = null;
        }
    }

    searchApps(records, rawQuery, limit = 15) {
        return searchAppRecords(records, rawQuery, limit);
    }

    /**
     * Query Nautilus SearchProvider2 asynchronously via session D-Bus, with async
     * fallback to recently-used.xbel bookmarks when Nautilus returns empty/unavailable.
     */
    async searchFilesAsync(rawQuery, maxResults = 6) {
        this.cancelPending();

        const norm = normalizeSearchText(rawQuery);
        const terms = splitTerms(rawQuery.trim());
        const normTerms = splitTerms(norm);
        if (terms.length === 0 || this._destroyed)
            return [];

        const cancellable = new Gio.Cancellable();
        this._activeCancellable = cancellable;

        try {
            const nautilusResults = await this._queryNautilusAsync(terms, cancellable, maxResults);
            if (cancellable.is_cancelled() || this._destroyed)
                return [];
            if (nautilusResults.length > 0)
                return nautilusResults;

            const recentResults = await this._queryRecentFilesAsync(normTerms, cancellable, maxResults);
            if (cancellable.is_cancelled() || this._destroyed)
                return [];
            return recentResults;
        } finally {
            if (this._activeCancellable === cancellable)
                this._activeCancellable = null;
        }
    }

    async _queryNautilusAsync(terms, cancellable, maxResults) {
        try {
            const resVariant = await Gio.DBus.session.call(
                NAUTILUS_BUS_NAME,
                NAUTILUS_OBJECT_PATH,
                SEARCH_PROVIDER_IFACE,
                'GetInitialResultSet',
                new GLib.Variant('(as)', [terms]),
                GLib.VariantType.new('(as)'),
                Gio.DBusCallFlags.NONE,
                1800,
                cancellable
            );

            if (cancellable.is_cancelled() || this._destroyed)
                return [];

            const [ids] = resVariant.deepUnpack();
            if (!Array.isArray(ids) || ids.length === 0)
                return [];

            const slicedIds = ids.slice(0, maxResults);
            const metasVariant = await Gio.DBus.session.call(
                NAUTILUS_BUS_NAME,
                NAUTILUS_OBJECT_PATH,
                SEARCH_PROVIDER_IFACE,
                'GetResultMetas',
                new GLib.Variant('(as)', [slicedIds]),
                GLib.VariantType.new('(aa{sv})'),
                Gio.DBusCallFlags.NONE,
                1800,
                cancellable
            );

            if (cancellable.is_cancelled() || this._destroyed)
                return [];

            const [metas] = metasVariant.deepUnpack();
            const results = [];
            for (const meta of metas) {
                const id = meta.id?.unpack?.() ?? meta.id ?? '';
                const name = meta.name?.unpack?.() ?? meta.name ?? '';
                const description = meta.description?.unpack?.() ?? meta.description ?? '';
                if (!id || !name)
                    continue;

                let gicon = null;
                try {
                    if (meta.icon)
                        gicon = Gio.Icon.deserialize(meta.icon);
                    else if (meta.gicon)
                        gicon = Gio.Icon.new_for_string(meta.gicon.unpack?.() ?? meta.gicon);
                } catch (_e) {
                    gicon = null;
                }

                results.push({
                    id,
                    uri: id.includes('://') ? id : null,
                    name,
                    description,
                    gicon: gicon || Gio.Icon.new_for_string('text-x-generic'),
                    source: 'nautilus',
                });
            }
            return results;
        } catch (_e) {
            return [];
        }
    }

    async _queryRecentFilesAsync(normTerms, cancellable, maxResults) {
        try {
            const xbelPath = GLib.build_filenamev([GLib.get_user_data_dir(), 'recently-used.xbel']);
            const file = Gio.File.new_for_path(xbelPath);
            const [ok, contents] = await file.load_contents_async(cancellable);
            if (!ok || !contents || cancellable.is_cancelled() || this._destroyed)
                return [];

            const bookmark = new GLib.BookmarkFile();
            bookmark.load_from_data(contents);
            const uris = bookmark.get_uris();
            uris.sort((a, b) => {
                try {
                    return bookmark.get_modified(b) - bookmark.get_modified(a);
                } catch (_e) {
                    return 0;
                }
            });
            return filterBookmarkUris(uris, bookmark, normTerms, maxResults);
        } catch (_e) {
            return [];
        }
    }

    activateFileResult(fileResult, rawQuery = '', context = null) {
        if (!fileResult)
            return;
        const targetUri = fileResult.uri || (fileResult.id?.includes('://') ? fileResult.id : null);
        if (targetUri) {
            try {
                Gio.AppInfo.launch_default_for_uri(targetUri, context);
                return;
            } catch (_e) {}
        }

        if (fileResult.source === 'nautilus' && fileResult.id) {
            const terms = splitTerms(rawQuery.trim());
            const timestamp = globalThis.global?.get_current_time?.() ?? 0;
            try {
                Gio.DBus.session.call(
                    NAUTILUS_BUS_NAME,
                    NAUTILUS_OBJECT_PATH,
                    SEARCH_PROVIDER_IFACE,
                    'ActivateResult',
                    new GLib.Variant('(sasu)', [fileResult.id, terms, timestamp]),
                    null,
                    Gio.DBusCallFlags.NONE,
                    1800,
                    null,
                    null
                );
            } catch (_e) {}
        }
    }

    destroy() {
        this._destroyed = true;
        this.cancelPending();
    }
}
