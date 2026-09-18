local function bind(keys, category, action, dispatcher, options)
    local opts = options or {}
    opts.description = category .. " | " .. action
    return hl.bind(keys, dispatcher, opts)
end

local mainMod = "SUPER"

local function dictationComponentInstalled()
    local sessionHome = os.getenv("HOME")
    assert(sessionHome ~= nil and sessionHome ~= "", "HOME is not set")
    local dataHome = os.getenv("XDG_DATA_HOME")
    if dataHome == nil or dataHome == "" or dataHome:sub(1, 1) ~= "/" then
        dataHome = sessionHome .. "/.local/share"
    end

    local marker = io.open(dataHome .. "/vanhyprarch/components/dictation", "r")
    if marker == nil then
        return false
    end
    local content = marker:read("*a")
    marker:close()
    return content == "vanhyprarch-dictation-v1\n"
end

-- Applications
bind(mainMod .. " + RETURN", "Apps", "Terminal", hl.dsp.exec_cmd("foot"))
bind(mainMod .. " + SHIFT + RETURN", "Apps", "Browser", hl.dsp.exec_cmd("firefox"))
bind(mainMod .. " + SHIFT + B", "Apps", "Browser", hl.dsp.exec_cmd("firefox"))
bind(mainMod .. " + SHIFT + F", "Apps", "File manager", hl.dsp.exec_cmd("thunar"))

-- Shell
bind(mainMod .. " + K", "Shell", "Show shortcuts",
    hl.dsp.exec_cmd("qs ipc -c vanhyprarch call vanhyprarch.shortcuts toggle"))
bind(mainMod .. " + SPACE", "Shell", "Open Super + Space",
    hl.dsp.exec_cmd("qs ipc -c vanhyprarch call vanhyprarch.superSpace toggle"))

-- Capture
bind("PRINT", "Capture", "Screenshot", hl.dsp.exec_cmd("vanhyprarch-screenshot"))

-- Optional local dictation
if dictationComponentInstalled() then
    bind("F9", "Dictation", "Start recording",
        hl.dsp.exec_cmd("voxtype record start"))
    bind("F9", "Dictation", "Stop and transcribe",
        hl.dsp.exec_cmd("voxtype record stop"), { release = true })
end

-- Window state
bind(mainMod .. " + W", "Window", "Close window", hl.dsp.window.close())
bind(mainMod .. " + Q", "Window", "Close window", hl.dsp.window.close())
bind(mainMod .. " + T", "Window", "Toggle floating", hl.dsp.window.float({ action = "toggle" }))
bind(mainMod .. " + F", "Window", "Fullscreen", hl.dsp.window.fullscreen({ mode = "fullscreen" }))
bind(mainMod .. " + ALT + F", "Window", "Maximize window", hl.dsp.window.fullscreen({ mode = "maximized" }))
bind(mainMod .. " + P", "Window", "Toggle pseudo", hl.dsp.window.pseudo())
bind(mainMod .. " + J", "Window", "Toggle split", hl.dsp.layout("togglesplit"))

-- Focus and window movement
bind(mainMod .. " + LEFT", "Window", "Focus left", hl.dsp.focus({ direction = "l" }))
bind(mainMod .. " + RIGHT", "Window", "Focus right", hl.dsp.focus({ direction = "r" }))
bind(mainMod .. " + UP", "Window", "Focus up", hl.dsp.focus({ direction = "u" }))
bind(mainMod .. " + DOWN", "Window", "Focus down", hl.dsp.focus({ direction = "d" }))
bind(mainMod .. " + SHIFT + LEFT", "Window", "Swap left", hl.dsp.window.swap({ direction = "l" }))
bind(mainMod .. " + SHIFT + RIGHT", "Window", "Swap right", hl.dsp.window.swap({ direction = "r" }))
bind(mainMod .. " + SHIFT + UP", "Window", "Swap up", hl.dsp.window.swap({ direction = "u" }))
bind(mainMod .. " + SHIFT + DOWN", "Window", "Swap down", hl.dsp.window.swap({ direction = "d" }))

-- Workspaces
for workspace = 1, 5 do
    local key = workspace % 10
    bind(mainMod .. " + " .. key, "Workspace", "Workspace " .. workspace,
        hl.dsp.focus({ workspace = tostring(workspace) }))
    bind(mainMod .. " + SHIFT + " .. key, "Workspace", "Move to workspace " .. workspace,
        hl.dsp.window.move({ workspace = tostring(workspace) }))
    bind(mainMod .. " + SHIFT + ALT + " .. key, "Workspace", "Move silently to workspace " .. workspace,
        hl.dsp.window.move({ workspace = tostring(workspace), follow = false }))
end

bind(mainMod .. " + S", "Workspace", "Toggle scratchpad",
    hl.dsp.workspace.toggle_special("magic"))
bind(mainMod .. " + ALT + S", "Workspace", "Move to scratchpad",
    hl.dsp.window.move({ workspace = "special:magic", follow = false }))

bind(mainMod .. " + TAB", "Workspace", "Next workspace",
    hl.dsp.focus({ workspace = "e+1" }))
bind(mainMod .. " + SHIFT + TAB", "Workspace", "Previous workspace",
    hl.dsp.focus({ workspace = "e-1" }))
bind(mainMod .. " + CTRL + TAB", "Workspace", "Former workspace",
    hl.dsp.focus({ workspace = "previous" }))

bind(mainMod .. " + mouse_down", "Workspace", "Next workspace",
    hl.dsp.focus({ workspace = "e+1" }))
bind(mainMod .. " + mouse_up", "Workspace", "Previous workspace",
    hl.dsp.focus({ workspace = "e-1" }))

-- Mouse window actions
bind(mainMod .. " + mouse:272", "Window", "Move window", hl.dsp.window.drag(),
    { mouse = true })
bind(mainMod .. " + mouse:273", "Window", "Resize window", hl.dsp.window.resize(),
    { mouse = true })

-- Audio hardware keys
bind("XF86AudioRaiseVolume", "Audio", "Volume up",
    hl.dsp.exec_cmd("wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+"),
    { locked = true, repeating = true })
bind("XF86AudioLowerVolume", "Audio", "Volume down",
    hl.dsp.exec_cmd("wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"),
    { locked = true, repeating = true })
bind("XF86AudioMute", "Audio", "Toggle mute",
    hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"),
    { locked = true, repeating = true })
bind("XF86AudioMicMute", "Audio", "Toggle microphone mute",
    hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle"),
    { locked = true, repeating = true })
