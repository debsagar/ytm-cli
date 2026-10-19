-- Append every track that starts playing to history.tsv next to mpv.conf.
-- One line per play: local time <TAB> url <TAB> artist - title. Read back by "ytm history".

local path = mp.get_opt("ytm-history") or mp.command_native({"expand-path", "~~/history.tsv"})
local last = nil

local function clean(s)
    return (tostring(s or ""):gsub("[\t\r\n]", " "))
end

mp.register_event("file-loaded", function()
    local url = mp.get_property("path", "")
    if url == "" or url == last then return end
    last = url
    local f = io.open(path, "ab")
    if not f then return end
    local title = mp.get_property("media-title", "")
    local artist = mp.get_property("metadata/by-key/artist") or mp.get_property("metadata/by-key/uploader")
    if artist and artist ~= "" then title = artist .. " - " .. title end
    f:write(os.date("%Y-%m-%d %H:%M"), "\t", clean(url), "\t", clean(title), "\n")
    f:close()
end)
