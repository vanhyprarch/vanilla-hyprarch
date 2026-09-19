-- Vanilla HyprArch managed portable Hyprland configuration.

-- Session environment ---------------------------------------------------------

local function prependPathOnce(inheritedPath, entry)
    local entries = { entry }
    if inheritedPath == "" then
        return entry
    end

    for inheritedEntry in (inheritedPath .. ":"):gmatch("(.-):") do
        if inheritedEntry ~= entry then
            table.insert(entries, inheritedEntry)
        end
    end
    return table.concat(entries, ":")
end

local sessionHome = os.getenv("HOME")
assert(sessionHome ~= nil and sessionHome ~= "", "HOME is not set")
assert(sessionHome:sub(1, 1) == "/", "HOME must be an absolute path")
local inheritedPath = os.getenv("PATH") or ""
-- Public Vanilla commands resolve from one stable per-user executable directory.
hl.env("PATH", prependPathOnce(inheritedPath, sessionHome .. "/.local/bin"))

-- Optional components ---------------------------------------------------------

-- Exact component markers keep optional payloads out of baseline startup.
local function dictationComponentInstalled()
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

-- Cursor environment ----------------------------------------------------------

hl.env("XCURSOR_SIZE", "24")
hl.env("HYPRCURSOR_SIZE", "24")

-- Startup ---------------------------------------------------------------------

-- Centralize the project's session-start decisions in Hyprland's startup hook.
hl.on("hyprland.start", function ()
    hl.exec_cmd("exec " .. sessionHome .. "/.local/bin/vanhyprarch-appearance renderer-start")
    hl.exec_cmd("systemctl --user start hyprpolkitagent")
    hl.exec_cmd("exec " .. sessionHome .. "/.local/bin/vanhyprarch-idle session-start")
    hl.exec_cmd("qs -n -c vanhyprarch")
    if dictationComponentInstalled() then
        hl.exec_cmd("systemctl --user start vanhyprarch-voxtype.service")
    end
end)

-- Appearance ------------------------------------------------------------------

hl.config({
    general = {
        -- The current spacing is the project's deliberate desktop geometry.
        gaps_in = 5,
        gaps_out = {
            top = 10,
            left = 10,
            right = 10,
            bottom = 10,
        },
        border_size = 2,
        col = {
            active_border = { colors = { "rgba(33ccffee)", "rgba(00ff99ee)" }, angle = 45 },
            inactive_border = "rgba(595959aa)",
        },
        resize_on_border = false,
        allow_tearing = false,
        -- Managed pseudo/split controls assume dwindle as the baseline layout.
        layout = "dwindle",
    },
    decoration = {
        -- Square window geometry is an intentional Vanilla HyprArch design choice.
        rounding = 0,
        rounding_power = 2,
        active_opacity = 1.0,
        inactive_opacity = 1.0,
        shadow = {
            enabled = true,
            range = 4,
            render_power = 3,
            color = 0xee1a1a1a,
        },
        blur = {
            enabled = true,
            size = 3,
            passes = 1,
            vibrancy = 0.1696,
        },
    },
    animations = {
        enabled = true,
    },
})

-- Animation profile -----------------------------------------------------------

hl.curve("easeOutQuint", { type = "bezier", points = { { 0.23, 1 }, { 0.32, 1 } } })
hl.curve("linear", { type = "bezier", points = { { 0, 0 }, { 1, 1 } } })
hl.curve("almostLinear", { type = "bezier", points = { { 0.5, 0.5 }, { 0.75, 1 } } })
hl.curve("quick", { type = "bezier", points = { { 0.15, 0 }, { 0.1, 1 } } })
hl.curve("easy", { type = "spring", mass = 1, stiffness = 238.1191, dampening = 24.21279333 })

hl.animation({ leaf = "global", enabled = true, speed = 10, bezier = "default" })
hl.animation({ leaf = "border", enabled = true, speed = 5.39, bezier = "easeOutQuint" })
hl.animation({ leaf = "windows", enabled = true, speed = 4.79, spring = "easy" })
hl.animation({ leaf = "windowsIn", enabled = true, speed = 4.1, spring = "easy", style = "popin 87%" })
hl.animation({ leaf = "windowsOut", enabled = true, speed = 1.49, bezier = "linear", style = "popin 87%" })
hl.animation({ leaf = "fadeIn", enabled = true, speed = 1.73, bezier = "almostLinear" })
hl.animation({ leaf = "fadeOut", enabled = true, speed = 1.46, bezier = "almostLinear" })
hl.animation({ leaf = "fade", enabled = true, speed = 3.03, bezier = "quick" })
hl.animation({ leaf = "layers", enabled = true, speed = 3.81, bezier = "easeOutQuint" })
hl.animation({ leaf = "layersIn", enabled = true, speed = 4, bezier = "easeOutQuint", style = "fade" })
hl.animation({ leaf = "layersOut", enabled = true, speed = 1.5, bezier = "linear", style = "fade" })
hl.animation({ leaf = "fadeLayersIn", enabled = true, speed = 1.79, bezier = "almostLinear" })
hl.animation({ leaf = "fadeLayersOut", enabled = true, speed = 1.39, bezier = "almostLinear" })
hl.animation({ leaf = "workspaces", enabled = true, speed = 1.94, bezier = "almostLinear", style = "fade" })
hl.animation({ leaf = "workspacesIn", enabled = true, speed = 1.21, bezier = "almostLinear", style = "fade" })
hl.animation({ leaf = "workspacesOut", enabled = true, speed = 1.94, bezier = "almostLinear", style = "fade" })
hl.animation({ leaf = "zoomFactor", enabled = true, speed = 7, bezier = "quick" })

-- Layout ----------------------------------------------------------------------

-- Preserve split choices made through the managed dwindle controls.
hl.config({
    dwindle = {
        preserve_split = true,
    },
})

hl.config({
    master = {
        new_status = "master",
    },
})

hl.config({
    scrolling = {
        fullscreen_on_one_column = true,
    },
})

-- Wallpaper ownership ---------------------------------------------------------

hl.config({
    misc = {
        force_default_wallpaper = -1,
        -- Appearance owns wallpaper rendering; never expose Hyprland's native
        -- logo/default background behind Hyprpaper.
        disable_hyprland_logo = true,
    },
})

-- Input ----------------------------------------------------------------------

hl.config({
    input = {
        -- Num Lock is enabled at graphical-session start as a project default.
        numlock_by_default = true,
        follow_mouse = 1,
        sensitivity = 0,
        touchpad = {
            natural_scroll = false,
        },
    },
})

hl.gesture({
    fingers = 3,
    direction = "horizontal",
    action = "workspace",
})

-- Window rules ----------------------------------------------------------------

local suppressMaximizeRule = hl.window_rule({
    name = "suppress-maximize-events",
    match = { class = ".*" },
    suppress_event = "maximize",
})

-- Avoid focus changes from transient empty-class XWayland drag windows.
hl.window_rule({
    name = "fix-xwayland-drags",
    match = {
        class = "^$",
        title = "^$",
        xwayland = true,
        float = true,
        fullscreen = false,
        pin = false,
    },
    no_focus = true,
})

-- Keep Hyprland's emergency launcher floating and clear of the lower edge.
hl.window_rule({
    name = "move-hyprland-run",
    match = { class = "hyprland-run" },
    move = "20 monitor_h-120",
    float = true,
})
