-- Vanilla HyprArch managed Hyprland entrypoint.

local home = os.getenv("HOME")
assert(home ~= nil and home ~= "", "HOME is not set")
assert(home:sub(1, 1) == "/", "HOME must be an absolute path")

local configHome = os.getenv("XDG_CONFIG_HOME")
if configHome == nil or configHome == "" then
    configHome = home .. "/.config"
else
    assert(configHome:sub(1, 1) == "/", "XDG_CONFIG_HOME must be an absolute path")
end

local managedHome = configHome .. "/hypr/vanhyprarch"
local userHome = configHome .. "/vanhyprarch"

require(managedHome .. "/core.lua")
require(managedHome .. "/bindings.lua")
require(userHome .. "/machine/hyprland.lua")
require(userHome .. "/overrides/hyprland.lua")
