import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
// Production builds get an extra CSP <meta> that limits network access to the
// configured client_api_server origin only (plus Tauri IPC). Browsers enforce
// every CSP present, so this narrows tauri.conf.json's broader connect-src.
// Skipped for `vite dev` so HMR's websocket keeps working.
function restrictConnectSrc(serverUrl) {
    return {
        name: "restrict-connect-src",
        apply: "build",
        transformIndexHtml: function () {
            if (!serverUrl) {
                throw new Error("VITE_SERVER_URL must be set for production builds.");
            }
            var origin = new URL(serverUrl).origin;
            return [
                {
                    tag: "meta",
                    attrs: {
                        "http-equiv": "Content-Security-Policy",
                        content: "connect-src 'self' ipc: http://ipc.localhost ".concat(origin),
                    },
                    injectTo: "head-prepend",
                },
            ];
        },
    };
}
// See: https://v2.tauri.app/start/frontend/vite/
export default defineConfig(function (_a) {
    var mode = _a.mode;
    var env = loadEnv(mode, process.cwd(), "VITE_");
    return {
        plugins: [react(), restrictConnectSrc(env.VITE_SERVER_URL)],
        clearScreen: false,
        server: {
            port: 1420,
            strictPort: true,
        },
        envPrefix: ["VITE_", "TAURI_"],
        build: {
            target: process.env.TAURI_ENV_PLATFORM === "windows" ? "chrome105" : "safari13",
            minify: process.env.TAURI_ENV_DEBUG ? false : "esbuild",
            sourcemap: !!process.env.TAURI_ENV_DEBUG,
        },
    };
});
