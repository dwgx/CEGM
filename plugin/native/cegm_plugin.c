/*
 * cegm_plugin.c — CEGM Cheat Engine native plugin shell.
 *
 * The heavy lifting (MCP server, named-pipe bridge, dashboard, LLM
 * tool routing) lives in the autorun Lua scripts and the Python
 * broker. This DLL exists so CEGM appears as a proper plugin in CE's
 * "Settings → Plugins" list and so the user can launch the dashboard
 * from the CE main menu.
 *
 * Build (from a "Developer Command Prompt for VS 2022"):
 *
 *     cl /nologo /LD /MD /O2 /W3 ^
 *        /I "C:\Path\To\Cheat Engine\plugins" ^
 *        cegm_plugin.c ^
 *        /link /DEF:cegm_plugin.def /OUT:CEGM-x64.dll
 *
 * Or run plugin/native/build.ps1 to auto-detect MSVC + the CE install.
 *
 * Install: copy the output DLL to "<CE>\plugins\" and tick it on in
 * CE → Settings → Plugins → enable.
 */

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>

#include "cepluginsdk.h"

/* Pull in the import lib for ShellExecuteW automatically so the
 * build script doesn't need to thread shell32.lib through cl/link. */
#pragma comment(lib, "shell32.lib")

#define CEGM_PLUGIN_NAME "CEGM (CheatEngineGM)"
#define CEGM_DASHBOARD_URL L"http://127.0.0.1:27077/"

static int            g_plugin_id    = -1;
static int            g_main_menu_id = -1;
static ExportedFunctions g_exports;

/* "Open CEGM Dashboard" main-menu callback — fires the user's default
 * browser at the broker's local dashboard. The broker is auto-spawned
 * by the CEGM Lua autorun, so by the time CE has finished loading and
 * the user can click the menu item, the URL is live. */
static void __stdcall on_open_dashboard(void)
{
    HINSTANCE rc = ShellExecuteW(
        NULL,
        L"open",
        CEGM_DASHBOARD_URL,
        NULL,
        NULL,
        SW_SHOWNORMAL
    );
    /* ShellExecute returns >32 on success; on failure we fall back to a
     * CE message box so the user sees something. */
    if ((INT_PTR)rc <= 32 && g_exports.ShowMessage) {
        g_exports.ShowMessage(
            "CEGM: failed to open dashboard. "
            "Visit http://127.0.0.1:27077/ manually."
        );
    }
}

/* Required SDK exports ------------------------------------------------ */

BOOL __stdcall CEPlugin_GetVersion(PPluginVersion pv, int sizeofpluginversion)
{
    (void)sizeofpluginversion;
    pv->version    = CESDK_VERSION;
    pv->pluginname = CEGM_PLUGIN_NAME;
    return TRUE;
}

BOOL __stdcall CEPlugin_InitializePlugin(PExportedFunctions ef, int pluginid)
{
    g_exports   = *ef;
    g_plugin_id = pluginid;

    MAINMENUPLUGIN_INIT mm;
    mm.name             = "Open CEGM Dashboard";
    mm.callbackroutine  = on_open_dashboard;
    mm.shortcut         = NULL;

    g_main_menu_id = g_exports.RegisterFunction(g_plugin_id, ptMainMenu, &mm);
    return (g_main_menu_id != 0);
}

BOOL __stdcall CEPlugin_DisablePlugin(void)
{
    if (g_main_menu_id > 0 && g_exports.UnregisterFunction) {
        g_exports.UnregisterFunction(g_plugin_id, g_main_menu_id);
        g_main_menu_id = -1;
    }
    return TRUE;
}

/* DLL stub — nothing to do, but Windows requires the entry point. */
BOOL APIENTRY DllMain(HINSTANCE hModule, DWORD reason, LPVOID lpReserved)
{
    (void)hModule; (void)reason; (void)lpReserved;
    return TRUE;
}
