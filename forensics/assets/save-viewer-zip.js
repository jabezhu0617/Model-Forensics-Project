(() => {
    const save = el('zip-save'), choose = el('zip-choose'), copy = el('zip-copy'), status = el('zip-status');
    if (!window.showSaveFilePicker) {
        status.textContent = 'To replace a ZIP, use Save link as…';
        return;
    }
    let destination, database;
    const key = location.pathname;
    async function restoreDestination() {
        try {
            database = await new Promise((resolve, reject) => {
                const request = indexedDB.open('model-forensics-zip', 1);
                request.onupgradeneeded = () => request.result.createObjectStore('destinations');
                request.onsuccess = () => resolve(request.result);
                request.onerror = () => reject(request.error);
            });
            destination = await new Promise((resolve, reject) => {
                const request = database.transaction('destinations').objectStore('destinations').get(key);
                request.onsuccess = () => resolve(request.result);
                request.onerror = () => reject(request.error);
            });
        } catch { /* Browsers with storage disabled can still use the save picker. */ }
    }
    function remember(file) {
        destination = file;
        choose.hidden = !file;
        if (!database) return;
        try {
            const store = database.transaction('destinations', 'readwrite').objectStore('destinations');
            if (file) store.put(file, key); else store.delete(key);
        } catch { /* Keep the selection for this tab if storage is unavailable. */ }
    }
    async function latestArchive() {
        if (location.protocol !== 'file:') {
            const response = await fetch(copy.href, {cache:'no-store'});
            if (!response.ok) throw new Error('ZIP unavailable');
            return response.blob();
        }
        // Browsers block fetch() of sibling file: URLs. The exporter publishes the
        // exact same ZIP bytes as a local script, loaded only when saving.
        const script = document.createElement('script');
        try {
            await new Promise((resolve, reject) => {
                script.onload = resolve;
                script.onerror = () => reject(new Error('ZIP unavailable'));
                script.src = './viewer-zip-data.js?v=' + Date.now();
                document.head.append(script);
            });
            const bytes = atob(window.viewerZipBase64);
            return Uint8Array.from(bytes, c => c.charCodeAt(0));
        } finally {
            script.remove();
            delete window.viewerZipBase64;
        }
    }
    async function saveArchive(selectNew) {
        if (save.disabled) return;
        save.disabled = choose.disabled = true;
        status.textContent = '';
        try {
            let file = selectNew ? null : destination;
            if (file && await file.requestPermission({mode:'readwrite'}) !== 'granted') {
                remember(null);
                status.textContent = 'Click Save viewer ZIP to choose a destination.';
                return;
            }
            if (!file) {
                file = await window.showSaveFilePicker({id:'model-forensics-zip',startIn:'downloads',
                    suggestedName:'viewer-laptop.zip',types:[{description:'Viewer ZIP',accept:{'application/zip':['.zip']}}]});
            }
            if (!file.name.toLowerCase().endsWith('.zip')) {
                status.textContent = 'Choose a file with a .zip extension.';
                return;
            }
            const bytes = await latestArchive();
            const stream = await file.createWritable();
            try {
                await stream.write(bytes);
                await stream.close();
            } catch (error) {
                await stream.abort().catch(() => {});
                throw error;
            }
            remember(file);
            status.textContent = 'Saved ' + file.name;
            copy.hidden = true;
        } catch (error) {
            if (error.name === 'AbortError') return;
            if (error.name === 'NotFoundError') remember(null);
            status.textContent = 'Couldn’t save. Choose a ZIP again, or use Save link as… on Download a copy.';
            copy.textContent = 'Download a copy';
            copy.hidden = false;
        } finally {
            save.disabled = choose.disabled = false;
        }
    }
    save.onclick = () => saveArchive(false);
    choose.onclick = () => saveArchive(true);
    restoreDestination().finally(() => {
        choose.hidden = !destination;
        copy.hidden = true;
        save.hidden = false;
    });
})();
