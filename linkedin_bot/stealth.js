// ── LinkedIn Auto-Apply Bot: Stealth Injections (2026) ──
// Loaded at runtime by browser.py via context.add_init_script()

// 1. Spoof WebGL Vendor and Renderer
const getParameterProxyHandler = {
    apply: function(target, ctx, args) {
        const param = args[0];
        if (param === 37445) return 'Intel Inc.'; // UNMASKED_VENDOR_WEBGL
        if (param === 37446) return 'Intel Iris OpenGL Engine'; // UNMASKED_RENDERER_WEBGL
        return Reflect.apply(target, ctx, args);
    }
};
const proxyWebGL = new Proxy(WebGLRenderingContext.prototype.getParameter, getParameterProxyHandler);
Object.defineProperty(WebGLRenderingContext.prototype, 'getParameter', {
    get: () => proxyWebGL,
    configurable: true
});
const proxyWebGL2 = new Proxy(WebGL2RenderingContext.prototype.getParameter, getParameterProxyHandler);
Object.defineProperty(WebGL2RenderingContext.prototype, 'getParameter', {
    get: () => proxyWebGL2,
    configurable: true
});

// 2. Add mild noise to Canvas getImageData to break static hashes
const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;
CanvasRenderingContext2D.prototype.getImageData = function() {
    const imageData = originalGetImageData.apply(this, arguments);
    for (let i = 0; i < imageData.data.length; i += 4) {
        const noise = Math.random() < 0.5 ? -1 : 1;
        imageData.data[i] = Math.max(0, Math.min(255, imageData.data[i] + noise));
    }
    return imageData;
};

// 3. Spoof Plugins & MimeTypes
const mockPlugins = [
    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
    { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
];
const mockMimes = [
    { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' }
];
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const pluginArray = Object.create(PluginArray.prototype);
        mockPlugins.forEach((p, i) => pluginArray[i] = p);
        Object.defineProperty(pluginArray, 'length', { value: mockPlugins.length });
        return pluginArray;
    }
});
Object.defineProperty(navigator, 'mimeTypes', {
    get: () => {
        const mimeArray = Object.create(MimeTypeArray.prototype);
        mockMimes.forEach((m, i) => mimeArray[i] = m);
        Object.defineProperty(mimeArray, 'length', { value: mockMimes.length });
        return mimeArray;
    }
});
