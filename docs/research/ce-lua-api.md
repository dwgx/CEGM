# Research: Cheat Engine 7.5+ Lua API

> Captured 2026-05-03. This document is research output, not authoritative reference. The authoritative source is the Cheat Engine wiki and source. If you find a discrepancy, update the wiki link, not this file. Treat findings as inputs to design — re-verify before relying on a specific signature.

## 1. Plugin Loading Mechanism

CE has no formal plugin system. It uses an **autorun folder**: any `.lua` file dropped into `<CheatEngineInstallDir>\autorun\` is executed at startup, in alphabetical order, before the main form is fully shown.

- **Path**: typically `C:\Program Files\Cheat Engine 7.5\autorun\`. Because the Start-menu shortcut points to a launcher, users find the real install via right-click → "Open file location" → locate the `autorun` subfolder. ([forum: Where is the autorun folder?](https://www.cheatengine.org/forum/viewtopic.php?t=610024))
- **Install procedure**: copy `.lua` files (and any `lua_modules/`, DLLs, assets) into that folder. No manifest, no enable/disable UI; presence in `autorun/` = enabled.
- **Hooking startup events**: scripts redefine globals like `onOpenProcess(processid)` to react to attach. Dark Byte's recommended pattern (chain previous handler, defer GUI work via `createTimer` Interval=1) is in [forum: Possible to Autorun Lua Script?](https://www.cheatengine.org/forum/viewtopic.php?p=5530136). Useful related globals: `getMainForm()`, `getLuaEngine()`, `onAPIPointerChange` ([wiki: Lua](https://wiki.cheatengine.org/index.php?title=Lua)).
- **Sub-folder convention**: most extension authors (e.g., FreeER's CE-Extensions) ship a flat collection of `.lua` files plus a `lua_modules/` directory and rely on `package.path` munging at the top of each script ([github: FreeER/CE-Extensions](https://github.com/FreeER/CE-Extensions)).

## 2. Memory Operations API

| Operation | Function |
|---|---|
| Attach by PID | `openProcess(pid)` |
| Attach by name | `openProcess("game.exe")` or `getProcessIDFromProcessName("game.exe")` |
| List processes | `getProcesslist()` (use a `Strings` object) |
| Create scan object | `createMemScan([progressbar])` returns `MemScan` |
| First scan | `MemScan:firstScan(scanOption, vartype, roundingtype, input1, input2, startaddr, stopaddr, protectionflags, alignmenttype, alignmentparam, isHexInput, isNotABinaryString, isUnicodeScan, iscaseSensitive)` |
| Next scan | `MemScan:nextScan(scanOption, roundingtype, input1, input2, isHexInput, isNotABinaryString, isUnicodeScan, iscaseSensitive, percentage, savedresultname)` |
| Wait for done | `MemScan:waitTillDone()` |
| Get results | `attachedFoundList = createFoundList(memscan); FoundList:initialize(); FoundList.Count; FoundList[i]` |
| AOB scan | `AOBScan(pattern, protectionFlags, alignmentType, alignmentParam)` returns `StringList` (must `:destroy()`) |
| Unique AOB | `AOBScanUnique(pattern, flags)` returns address or nil |
| AOB in module | `AOBScanModule(pattern, moduleName, flags)` |
| Read | `readBytes(addr, n, ReturnAsTable)`, `readSmallInteger`, `readInteger`, `readQword`, `readPointer`, `readFloat`, `readDouble`, `readString(addr, maxLen, wideString)` |
| Write | `writeBytes`, `writeSmallInteger`, `writeInteger`, `writeQword`, `writeFloat`, `writeDouble`, `writeString(addr, str, wideString)` |
| Local-process variants | append `Local` (e.g. `readBytesLocal`) |
| Pointer scan | UI-driven; from Lua use `getMainForm().miPointerscanThis...` or open via `openPointerscanFile`. Custom rescan filter via `cbLuaFilter` ([deepwiki: Pointer Scanner](https://deepwiki.com/cheat-engine/cheat-engine/3.1-pointer-scanner)). Pointer-map generation via `generatePointermap(filename)`. **No first-class `pointerScan()` Lua function** — mostly form-driven. |

**Scan constants**: `soExactValue`, `soBiggerThan`, `soSmallerThan`, `soValueBetween`, `soBiggerThanValue`, `soSmallerThanValue`, `soIncreasedValue`, `soDecreasedValue`, `soChanged`, `soUnchanged`, `soUnknownValue`. Vartypes: `vtByte`, `vtWord`, `vtDword`, `vtQword`, `vtSingle`, `vtDouble`, `vtString`, `vtUnicodeString`, `vtByteArray`, `vtBinary`, `vtAll`. Sources: [wiki: Lua](https://wiki.cheatengine.org/index.php?title=Lua), [wiki: Lua:AOBScan](https://wiki.cheatengine.org/index.php?title=Lua:AOBScan).

## 3. Custom UI

Lua plugins create **floating LCL forms** (Lazarus VCL clones), not docked panels. **There is no public API to dock into the CE main window** — the closest is parenting a control to `getMainForm()` or to one of its child panels, which is undocumented and brittle.

Available factories (all return objects with full property bags):

- `createForm(visible)` — top-level window ([wiki: Form](https://wiki.cheatengine.org/index.php?title=Lua:Class:Form))
- `createPanel(owner)`, `createMemo(owner)`, `createButton(owner)`, `createLabel(owner)`, `createEdit(owner)`, `createListBox(owner)`, `createListView(owner)`, `createTreeView(owner)`, `createGroupBox(owner)`, `createSplitter(owner)`, `createTimer(owner, enabled)`, `createMenuItem(parent)`, `createImage(owner)`, `createTrackBar(owner)`
- Layout: each control has `.Align` (`alClient`, `alLeft`, `alRight`, `alTop`, `alBottom`, `alNone`), `.Anchors`, `.Parent`, `.Width`, `.Height`. Memo + Splitter + Panel `.Align="alClient"/"alLeft"` gives a usable IDE-ish layout.
- Save layout: `Form:saveToFile(filename)` and `createFormFromFile(filename)`.

**Dark theme**: CE 7.5 has no built-in dark theme; the "Disable Dark Mode support" setting only affects Windows title bars. Community solution is the Dark-Theme cheat table that walks the form tree at startup setting `Color`, `Font.Color` per control ([github: visibou/darkthemecheatengine](https://github.com/visibou/darkthemecheatengine), [forum: dark mode?](https://forum.cheatengine.org/viewtopic.php?p=5773472)). Issue [#2527](https://github.com/cheat-engine/cheat-engine/issues/2527) confirms native dark-mode is still open.

## 4. Networking / IPC

**LuaSocket is NOT bundled.** Three options:

1. **Compile LuaSocket against CE's custom `lua53-32.dll`/`lua53-64.dll`** — Dark Byte rebuilt it once and hosted a binary ([forum: external modules](https://www.cheatengine.org/forum/viewtopic.php?p=5312633)). Standard luarocks `socket.core.dll` will fail to load due to header/runtime mismatch.
2. **Shell out + stdio**: `os.execute`, `io.popen(cmd, "r"|"w")` work; pipes are line-buffered. CE-side Lua can spawn a Python/Node helper and exchange JSON over stdin/stdout — no native sockets needed. Most common DIY path. **Note: `io.popen` is unidirectional in standard Lua; bidirectional needs two pipes or a DLL helper.**
3. **WinAPI via `ffi`** — CE provides `getAddressSafe`, `executeCodeLocal`, and via `package.cpath` you can load any DLL; some authors call `WSAStartup`/`socket`/`connect` directly.

For named pipes: `CreateFileW("\\\\.\\pipe\\name", ...)` via `executeCodeLocal` or via a shipped C-DLL works but is non-trivial.

Sources: [forum: LuaSocket](https://www.cheatengine.org/forum/viewtopic.php?t=603914), [forum: Luasocket for CE6.5+](https://www.cheatengine.org/forum/viewtopic.php?p=5690229).

## 5. Threading Model

CE Lua is **single-threaded on the main UI/Lua thread by default**. Anything CPU-heavy or `sleep()` directly in the Lua engine freezes the UI.

| API | Purpose |
|---|---|
| `createThread(fn, ...args)` | Spawn worker thread; `fn` receives `(thread, ...args)`. Default `freeOnTerminate=true`. **Shared Lua state** with main thread — synchronization required. |
| `createThreadSuspended(fn, ...)` | Same but call `:resume()` later. |
| `createThreadNewState(fn)` | Worker has its **own Lua state** — no shared globals, no synchronization needed. Best for CPU-bound. |
| `thread:synchronize(fn)` | Blocking call that runs `fn` on main thread; returns its result. **Required for all GUI access.** |
| `synchronize(fn)` (global) / `queue(fn)` | `synchronize` blocks; `queue` fire-and-forget. |
| `checkSynchronize()` | Drains pending `queue` calls; call from your main-thread loop. |
| `createTimer(owner, enabled)` | Main-thread polling, `OnTimer`, `Interval`. Resolution ~15 ms on Windows. |
| `sleep(ms)` | OS sleep — **never call on main thread**. |

**Blocking offenders on main thread**: `MemScan:waitTillDone()`, `AOBScan` on the whole address space, `executeCodeLocal` of long routines, `sleep`, `os.execute` (sync), large `readBytes` with table return.

Sources: [wiki: Thread](https://wiki.cheatengine.org/index.php?title=Lua:Class:Thread), [forum: Thread class](https://www.cheatengine.org/forum/viewtopic.php?t=608951), [issue #1093](https://github.com/cheat-engine/cheat-engine/issues/1093).

## 6. JSON Handling

**No JSON shipped.** Bundle your own. Community consensus is **`dkjson.lua`** (pure Lua, single file, MIT) — zero dependencies, works in any Lua 5.x, copy-pasted into the plugin or required from `<plugin>/lua_modules/`. `cjson` works but requires a CE-compatible binary build (same compile-against-CE-headers headache as LuaSocket). dkjson is the safe default. ([forum: JSON modules for lua](https://www.cheatengine.org/forum/viewtopic.php?t=588814)).

## 7. Cheat Table (.CT) Format

CT files are **plain XML by default** (CE saves with no compression unless the trainer uses `.CETrainer`, which is XOR+zlib-wrapped XML — see [cetrainer-unpacker docs](https://github.com/AlexAltea/cetrainer-unpacker/blob/master/docs/cetrainer.md)).

Minimum valid table:

```xml
<?xml version="1.0" encoding="utf-8"?>
<CheatTable CheatEngineTableVersion="38">
  <CheatEntries>
    <CheatEntry>
      <ID>0</ID>
      <Description>"Health"</Description>
      <VariableType>4 Bytes</VariableType>
      <Address>"game.exe"+1A2B3C</Address>
    </CheatEntry>
  </CheatEntries>
  <UserdefinedSymbols/>
</CheatTable>
```

Optional children: `<Offsets><Offset>568</Offset></Offsets>` (pointer chains), `<LuaScript>...</LuaScript>` (table-level Lua, Ctrl+Alt+L), `<AssemblerScript>...</AssemblerScript>`, `<Hotkeys>`, `<GroupHeader>1</GroupHeader>`.

Lua APIs:

- `getAddressList()` returns `AddressList`
- `AddressList:createMemoryRecord()` returns new `MemoryRecord`
- `MemoryRecord` properties: `.Description`, `.Address` (string), `.Type` (vtDword etc.), `.Value`, `.Active`, `.Offsets[i]`, methods `getAddress()`, `setAddress(str, offsetTable)`, `setValue(string)`, `getValue()`, `delete()`
- `getAddressList().getMemoryRecordByDescription(name)` for lookup

Sources: [wiki: Cheat_Tables](https://wiki.cheatengine.org/index.php?title=Cheat_Engine:Cheat_Tables), [docs.fileformat: CT](https://docs.fileformat.com/game/ct/).

## 8. Distribution

How existing plugins ship today (no centralized registry):

- **Single-file Lua** dropped into `autorun/` — most common for small extensions; e.g., FreeER's CE-Extensions (51+ standalone `.lua` files).
- **Embedded in a `.CT` cheat-table** — for game-specific trainers; the `<LuaScript>` runs at table-open. Distributed as a single `.CT` (XML) or `.CETrainer` (encrypted, packaged via File → Save As).
- **ZIP bundle for multi-file plugins**: a folder with `main.lua` + `lib/*.lua` + `*.dll`, user unzips into `autorun/`. Used by larger projects.
- **DLLs**: rare for pure Lua plugins; mostly used to ship pre-compiled native helpers (`socket.core.dll`, custom scanners) loaded via `package.cpath`.

There's no auto-updater, no signing, no plugin registry. README + GitHub release ZIP is the norm.

## 9. Known Limitations / Gotchas

- **Main-thread blocking is the #1 bug.** Always wrap scans in `createThread` and use `synchronize` to push results back.
- **Address-list races**: `AddressList` can be mutated by the user via the GUI between Lua callback invocations. Iterate by index with bounds re-checked, never cache `MemoryRecord` references across yields/timer ticks.
- **Scan-result invalidation**: each `MemScan:firstScan/nextScan` invalidates the previous `FoundList`. Must `:initialize()` a new `FoundList` after every scan; reading old indices crashes CE.
- **`StringList` from `AOBScan` must be `:destroy()`-ed** or you leak — CE does not garbage-collect native objects ([wiki: Lua:AOBScan](https://wiki.cheatengine.org/index.php?title=Lua:AOBScan)).
- **Encoding**: Lua strings are byte-buffers; on non-English Windows, `ansiToUtf8` / `utf8ToAnsi` are required for filenames, process names from `getProcesslist()`, and `readString` (which has a `wideString` flag) ([forum: UTF-8 vs UTF-16 scanning](https://www.cheatengine.org/forum/viewtopic.php?t=594292), [issue #103](https://github.com/cheat-engine/cheat-engine/issues/103)).
- **Custom Lua DLL incompatibility**: CE ships its own `lua53-32/64.dll` with patched headers — generic luarocks binaries crash-load. Always rebuild C modules against CE's headers.
- **`createMemScan(progressbar)` requires the progressbar arg even if nil**, otherwise some builds segfault.
- **32 vs 64-bit**: `cheatengine-i386.exe` and `cheatengine-x86_64.exe` are separate processes with separate `autorun/` runs and different `lua_modules` paths. Plugins must handle both bitnesses.
- **`onOpenProcess` not chained**: many naive plugins replace the global, breaking other autorun scripts. Always save and call `originalOnOpenProcess`.
- **Pointer scans are GUI-driven**: there's no clean Lua API to start one programmatically with all options; drive the form (`PointerscanForm`) or save/load `.PTR` files and post-process.

## Sources

- [Cheat Engine Lua wiki](https://wiki.cheatengine.org/index.php?title=Lua)
- [wiki: Tutorials:Lua:Basics](https://wiki.cheatengine.org/index.php?title=Tutorials:Lua:Basics)
- [wiki: Lua:AOBScan](https://wiki.cheatengine.org/index.php?title=Lua:AOBScan)
- [wiki: Lua:Class:Thread](https://wiki.cheatengine.org/index.php?title=Lua:Class:Thread)
- [wiki: Lua:Class:Form](https://wiki.cheatengine.org/index.php?title=Lua:Class:Form)
- [wiki: Cheat_Engine:Cheat_Tables](https://wiki.cheatengine.org/index.php?title=Cheat_Engine:Cheat_Tables)
- [forum: Possible to Autorun Lua Script?](https://www.cheatengine.org/forum/viewtopic.php?p=5530136)
- [forum: Where is the autorun folder?](https://www.cheatengine.org/forum/viewtopic.php?t=610024)
- [forum: Using external modules (luasockets!)](https://www.cheatengine.org/forum/viewtopic.php?p=5312633)
- [forum: LuaSocket](https://www.cheatengine.org/forum/viewtopic.php?t=603914)
- [forum: JSON modules for lua](https://www.cheatengine.org/forum/viewtopic.php?t=588814)
- [forum: Thread class in CE](https://www.cheatengine.org/forum/viewtopic.php?t=608951)
- [forum: UTF-8 vs UTF-16 scanning](https://www.cheatengine.org/forum/viewtopic.php?t=594292)
- [github: cheat-engine/cheat-engine](https://github.com/cheat-engine/cheat-engine)
- [github: FreeER/CE-Extensions](https://github.com/FreeER/CE-Extensions)
- [github: visibou/darkthemecheatengine](https://github.com/visibou/darkthemecheatengine)
- [github issue: dark mode #2527](https://github.com/cheat-engine/cheat-engine/issues/2527)
- [github issue: createNativeThread vs createTimer #1093](https://github.com/cheat-engine/cheat-engine/issues/1093)
- [github: AlexAltea/cetrainer-unpacker](https://github.com/AlexAltea/cetrainer-unpacker/blob/master/docs/cetrainer.md)
- [deepwiki: Pointer Scanner](https://deepwiki.com/cheat-engine/cheat-engine/3.1-pointer-scanner)
- [docs.fileformat: CT](https://docs.fileformat.com/game/ct/)
