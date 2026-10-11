-- System-wide screenshot assistant. Hammerspoon owns the hotkey and popup.
-- Python owns the OpenAI request. The API key never enters this process.

local M = {}

local log = hs.logger.new("mac-ai-assistant", "info")
local HOME = os.getenv("HOME") or ""
local CONFIG_PATH = HOME .. "/.config/mac-ai-assistant/config.json"
local INSTALL_PATH = HOME .. "/.config/mac-ai-assistant/install.json"

local DEFAULTS = {
  shortcut = { modifiers = { "ctrl", "alt" }, key = "]" },
  popup = { width = 400, max_height = 520, margin = 16 },
}

local state = {
  session = 0,
  busy = false,
  started = false,
  responseId = nil,
  config = nil,
  root = nil,
  hotkey = nil,
  enabled = true,
  menubar = nil,
  webview = nil,
  userContent = nil,
  task = nil,
  captureTimer = nil,
  imagePath = nil,
  pageReady = false,
  pendingJS = {},
}

local function shellQuote(value)
  return "'" .. tostring(value):gsub("'", "'\\''") .. "'"
end

local function readFile(path)
  local handle = io.open(path, "r")
  if not handle then
    return nil
  end
  local contents = handle:read("*a")
  handle:close()
  return contents
end

local function realpath(path)
  local command = "/usr/bin/python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' " .. shellQuote(path)
  local output, ok = hs.execute(command)
  if not ok or not output then
    return path
  end
  return (output:gsub("%s+$", ""))
end

local function moduleDirectory()
  local source = debug.getinfo(1, "S").source or ""
  if source:sub(1, 1) == "@" then
    source = source:sub(2)
  end
  local resolved = realpath(source)
  return resolved:match("^(.*)/[^/]+$") or "."
end

local function loadJSON(path)
  local raw = readFile(path)
  if not raw or raw == "" then
    return nil
  end
  local ok, decoded = pcall(hs.json.decode, raw)
  if ok and type(decoded) == "table" then
    return decoded
  end
  return nil, "invalid"
end

local function loadConfig()
  local config = {
    shortcut = {
      modifiers = { "ctrl", "alt" },
      key = "]",
    },
    popup = {
      width = DEFAULTS.popup.width,
      max_height = DEFAULTS.popup.max_height,
      margin = DEFAULTS.popup.margin,
    },
  }
  local decoded, status = loadJSON(CONFIG_PATH)
  if status == "invalid" then
    hs.notify.show("Screen Assistant", "", "The config file is invalid JSON. Using the default shortcut.")
  elseif type(decoded) == "table" then
    if type(decoded.shortcut) == "table" then
      if type(decoded.shortcut.modifiers) == "table" and #decoded.shortcut.modifiers > 0 then
        config.shortcut.modifiers = decoded.shortcut.modifiers
      end
      if type(decoded.shortcut.key) == "string" and decoded.shortcut.key ~= "" then
        config.shortcut.key = decoded.shortcut.key
      end
    end
    if type(decoded.popup) == "table" then
      for _, field in ipairs({ "width", "max_height", "margin" }) do
        if type(decoded.popup[field]) == "number" then
          config.popup[field] = decoded.popup[field]
        end
      end
    end
  end
  state.config = config
end

local function findRoot()
  local install = loadJSON(INSTALL_PATH)
  if type(install) == "table" and type(install.project_root) == "string" then
    if hs.fs.attributes(install.project_root .. "/scripts/run.sh") then
      state.root = install.project_root
      return
    end
  end
  local parent = moduleDirectory():match("^(.*)/hammerspoon$")
  if parent and hs.fs.attributes(parent .. "/scripts/run.sh") then
    state.root = parent
    return
  end
  state.root = nil
end

local function redact(value)
  local text = tostring(value or "")
  text = text:gsub("sk%-[%w_%-]+", "[redacted]")
  text = text:gsub("Bearer%s+[%w%._%-]+", "Bearer [redacted]")
  return text
end

local function deleteFile(path)
  if path and path ~= "" then
    os.remove(path)
  end
end

local function stopWatchdog()
  if state.watchdog then
    state.watchdog:stop()
    state.watchdog = nil
  end
end

local function cancelWork()
  state.session = (state.session or 0) + 1
  state.busy = false
  state.responseId = nil
  stopWatchdog()
  if state.captureTimer then
    state.captureTimer:stop()
    state.captureTimer = nil
  end
  local imagePath = state.imagePath
  state.imagePath = nil
  state.pendingImage = nil
  local task = state.task
  state.task = nil
  _G.macAIAssistantTask = nil
  if task then
    pcall(function() task:terminate() end)
  end
  deleteFile(imagePath)
end

local function scriptFor(fn, value)
  if value == nil then
    return "window.assistant && window.assistant." .. fn .. "()"
  end
  if type(value) == "boolean" then
    return "window.assistant && window.assistant." .. fn .. "(" .. (value and "true" or "false") .. ")"
  end
  local encoded = hs.base64.encode(tostring(value))
  if not encoded then
    return nil
  end
  encoded = encoded:gsub("%s", "")
  return "window.assistant && window.assistant." .. fn .. "(window.assistant.decodeB64('" .. encoded .. "'))"
end

local function flushJS()
  local pending = state.pendingJS or {}
  state.pendingJS = {}
  for _, item in ipairs(pending) do
    local script = scriptFor(item[1], item[2])
    local view = state.webview
    if script and view then
      pcall(function()
        view:evaluateJavaScript(script)
      end)
    end
  end
end

local function callJS(fn, value)
  if not state.webview then
    return
  end
  if not state.pageReady then
    state.pendingJS[#state.pendingJS + 1] = { fn, value }
    return
  end
  state.pendingJS = { { fn, value } }
  flushJS()
end

local function popupRect(screen)
  local popup = (state.config and state.config.popup) or DEFAULTS.popup
  local frame = screen:frame()
  local width = popup.width
  local height = math.min(popup.max_height, frame.h - (popup.margin * 2))
  if height < 220 then
    height = math.min(220, frame.h)
  end
  return {
    x = frame.x + frame.w - width - popup.margin,
    y = frame.y + popup.margin,
    w = width,
    h = height,
  }
end

local function closePopup()
  local view = state.webview
  state.webview = nil
  state.userContent = nil
  state.pageReady = false
  state.pendingJS = {}
  cancelWork()
  if view then
    pcall(function() view:delete() end)
  end
end

local function onWebMessage(message)
  local body = message
  if type(message) == "table" and type(message.body) == "table" then
    body = message.body
  end
  if type(body) ~= "table" then
    return
  end
  if body.action == "close" then
    closePopup()
  elseif body.action == "copy" then
    hs.pasteboard.setContents(tostring(body.text or ""))
    callJS("flash", "Copied.")
  elseif body.action == "followup" then
    M.followup(tostring(body.text or ""))
  elseif body.action == "again" then
    M.captureAgain()
  end
end

local function ensurePopup(screen)
  if state.webview then
    state.webview:frame(popupRect(screen))
    state.webview:show()
    state.webview:bringToFront(false)
    return
  end

  local html = readFile(moduleDirectory() .. "/popup.html")
  if not html then
    hs.notify.show("Screen Assistant", "", "The popup interface file is missing.")
    return
  end

  local userContent = hs.webview.usercontent.new("macAI")
  userContent:setCallback(function(message)
    local ok, err = pcall(onWebMessage, message)
    if not ok then
      log.e("popup message failed: " .. redact(err))
    end
  end)

  local view = hs.webview.new(popupRect(screen), { developerExtrasEnabled = false }, userContent)
  view:windowStyle({ "titled", "closable", "utility", "nonactivating" })
  view:windowTitle("Jarvis")
  view:titleVisibility("visible")
  view:level(hs.drawing.windowLevels.floating)
  pcall(function()
    view:behaviorAsLabels({ "canJoinAllSpaces", "stationary", "ignoresCycle" })
  end)
  view:allowTextEntry(true)
  view:closeOnEscape(true)
  view:shadow(true)
  view:deleteOnClose(true)
  if hs.host.interfaceStyle then
    view:darkMode(hs.host.interfaceStyle() == "Dark")
  end
  view:windowCallback(function(action)
    if action == "closing" and state.webview == view then
      state.webview = nil
      state.userContent = nil
      state.pageReady = false
      state.pendingJS = {}
      cancelWork()
    end
  end)
  view:policyCallback(function(kind, _, details)
    if kind == "navigationAction" and details and details.navigationType == "linkActivated" then
      local url = details.request and details.request.URL
      if type(url) == "string" and url ~= "" then
        hs.urlevent.openURL(url)
      end
      return false
    end
    if kind == "newWindow" then
      return false
    end
    return true
  end)
  view:navigationCallback(function(action)
    if action == "didFinishNavigation" and state.webview == view then
      state.pageReady = true
      flushJS()
    end
  end)

  state.userContent = userContent
  state.webview = view
  state.pageReady = false
  state.pendingJS = {}
  view:html(html)
  view:show()
  view:bringToFront(false)

  hs.timer.doAfter(0.4, function()
    if state.webview == view and not state.pageReady then
      state.pageReady = true
      flushJS()
    end
  end)
end

local function presentLoading(screen)
  ensurePopup(screen)
  callJS("reset")
end

local function presentError(screen, message)
  state.busy = false
  ensurePopup(screen or hs.mouse.getCurrentScreen() or hs.screen.mainScreen())
  callJS("showError", redact(message))
end

local function decodeResult(stdout)
  if type(stdout) ~= "string" then
    return nil
  end
  local trimmed = stdout:match("^%s*(.-)%s*$")
  if not trimmed or trimmed == "" then
    return nil
  end
  local ok, decoded = pcall(hs.json.decode, trimmed)
  if ok and type(decoded) == "table" then
    return decoded
  end
  local last = trimmed:match("([^\n]+)%s*$")
  if last then
    ok, decoded = pcall(hs.json.decode, last)
    if ok and type(decoded) == "table" then
      return decoded
    end
  end
  return nil
end

local function applyResult(session, stdOut, stdErr)
  deleteFile(state.pendingImage)
  state.pendingImage = nil
  stopWatchdog()
  state.task = nil
  _G.macAIAssistantTask = nil
  state.busy = false

  if session ~= state.session or not state.webview then
    return
  end

  local payload = decodeResult(stdOut)
  if not payload then
    local detail = redact(stdErr)
    if detail == "" then
      detail = redact(stdOut)
    end
    if #detail > 240 then
      detail = detail:sub(1, 240)
    end
    if detail == "" then
      detail = "The assistant closed without a result."
    end
    callJS("showError", "The assistant returned an unexpected response. " .. detail)
    return
  end
  if payload.ok then
    state.responseId = payload.response_id or ""
    callJS("showAnswer", tostring(payload.text or ""))
    log.i("request finished")
  else
    log.i("request failed: " .. tostring(payload.code))
    callJS("showError", redact(payload.error or "The request failed."))
  end
end

local function runPython(session, args, imagePath)
  if not state.root then
    deleteFile(imagePath)
    presentError(state.screen, "The assistant is not installed. Run scripts/install.sh.")
    return
  end
  local script = state.root .. "/scripts/run.sh"
  if not hs.fs.attributes(script) then
    deleteFile(imagePath)
    presentError(state.screen, "scripts/run.sh is missing. Re-run scripts/install.sh.")
    return
  end
  local command = { script }
  for _, arg in ipairs(args) do
    command[#command + 1] = tostring(arg)
  end

  state.pendingImage = imagePath
  local task = hs.task.new("/bin/bash", function(_, stdOut, stdErr)
    local ok, err = pcall(applyResult, session, stdOut, stdErr)
    if not ok then
      state.busy = false
      state.task = nil
      _G.macAIAssistantTask = nil
      stopWatchdog()
      log.e("result failed: " .. redact(err))
      callJS("showError", "The answer could not be shown. Try the shortcut again.")
    end
    return false
  end, command)

  if not task then
    deleteFile(imagePath)
    presentError(state.screen, "Could not start the OpenAI request.")
    return
  end
  task:setWorkingDirectory(state.root)
  state.task = task
  _G.macAIAssistantTask = task
  if not task:start() then
    state.task = nil
    _G.macAIAssistantTask = nil
    deleteFile(imagePath)
    presentError(state.screen, "Could not start the OpenAI request.")
    return
  end

  stopWatchdog()
  state.watchdog = hs.timer.doAfter(180, function()
    state.watchdog = nil
    if session ~= state.session or not state.busy then
      return
    end
    if state.task then
      pcall(function() state.task:terminate() end)
    end
    state.busy = false
    state.task = nil
    _G.macAIAssistantTask = nil
    deleteFile(imagePath)
    callJS("showError", "The request took too long and was stopped. Check the internet connection and try again.")
  end)
end

local function temporaryPNG()
  local directory = hs.fs.temporaryDirectory() or "/tmp/"
  if directory:sub(-1) ~= "/" then
    directory = directory .. "/"
  end
  return directory .. "mac-ai-assistant-" .. tostring(os.time()) .. "-" .. tostring(math.random(100000, 999999)) .. ".png"
end

local function captureScreen(screen)
  local image = screen:snapshot()
  if not image then
    return nil, "Could not capture the screen. Enable Screen Recording for Hammerspoon in System Settings → Privacy & Security → Screen Recording, then quit and reopen Hammerspoon."
  end
  local size = image:size()
  if not size or not size.w or size.w < 2 or not size.h or size.h < 2 then
    return nil, "The screenshot was empty. Enable Screen Recording for Hammerspoon, then quit and reopen Hammerspoon."
  end
  local path = temporaryPNG()
  local saved = image:saveToFile(path)
  local attributes = hs.fs.attributes(path)
  if saved == false or not attributes or not attributes.size or attributes.size < 32 then
    deleteFile(path)
    return nil, "Could not save the screenshot. Enable Screen Recording for Hammerspoon, then quit and reopen Hammerspoon."
  end
  return path
end

function M.captureAgain()
  if state.busy then
    callJS("flash", "A request is already running.")
    return
  end
  if not state.responseId or state.responseId == "" then
    callJS("showError", "Wait for an answer before adding another screenshot.")
    return
  end

  state.busy = true
  state.session = state.session + 1
  local session = state.session
  local previousId = state.responseId
  state.screen = hs.mouse.getCurrentScreen() or hs.screen.mainScreen()
  callJS("setBusy", true)

  local function capture()
    if session ~= state.session then
      return
    end
    local path, err = captureScreen(state.screen)
    if not path then
      presentError(state.screen, err)
      return
    end
    state.imagePath = path
    local shown, showErr = pcall(function()
      ensurePopup(state.screen)
      callJS("addUser", "Another screenshot")
      runPython(session, {
        "analyze",
        "--image",
        path,
        "--previous-id",
        previousId,
        "--config",
        CONFIG_PATH,
      }, path)
    end)
    if not shown then
      state.busy = false
      deleteFile(path)
      log.e("popup failed: " .. redact(showErr))
      hs.notify.show("Screen Assistant", "", "The popup could not open. " .. redact(showErr))
    end
  end

  if state.webview and state.webview:isVisible() then
    state.webview:hide()
    state.captureTimer = hs.timer.doAfter(0.15, function()
      state.captureTimer = nil
      capture()
    end)
  else
    capture()
  end
end

function M.followup(text)
  text = (text or ""):gsub("^%s+", ""):gsub("%s+$", "")
  if text == "" then
    return
  end
  if state.busy then
    callJS("flash", "A request is already running.")
    return
  end
  if not state.responseId or state.responseId == "" then
    callJS("showError", "Take a screenshot before asking a follow-up.")
    return
  end
  state.busy = true
  state.session = state.session + 1
  local session = state.session
  callJS("addUser", text)
  runPython(session, {
    "followup",
    "--previous-id",
    state.responseId,
    "--text",
    text,
    "--config",
    CONFIG_PATH,
  })
end

function M.trigger(force)
  if not state.enabled and not force then
    return
  end
  if state.busy then
    if state.webview then
      callJS("flash", "A request is already running.")
    end
    return
  end

  state.busy = true
  state.responseId = nil
  state.session = state.session + 1
  local session = state.session
  state.screen = hs.mouse.getCurrentScreen() or hs.screen.mainScreen()

  local function capture()
    if session ~= state.session then
      return
    end
    local path, err = captureScreen(state.screen)
    if not path then
      presentError(state.screen, err)
      return
    end
    state.imagePath = path
    local shown, showErr = pcall(function()
      presentLoading(state.screen)
      runPython(session, {
        "analyze",
        "--image",
        path,
        "--config",
        CONFIG_PATH,
      }, path)
    end)
    if not shown then
      state.busy = false
      deleteFile(path)
      log.e("popup failed: " .. redact(showErr))
      hs.notify.show("Screen Assistant", "", "The popup could not open. " .. redact(showErr))
    end
  end

  if state.webview and state.webview:isVisible() then
    state.webview:hide()
    state.captureTimer = hs.timer.doAfter(0.15, function()
      state.captureTimer = nil
      capture()
    end)
  else
    capture()
  end
end

local function shortcutLabel()
  local shortcut = (state.config and state.config.shortcut) or DEFAULTS.shortcut
  local symbols = { ctrl = "⌃", alt = "⌥", shift = "⇧", cmd = "⌘" }
  local label = ""
  for _, modifier in ipairs(shortcut.modifiers or {}) do
    label = label .. (symbols[modifier] or modifier)
  end
  return label .. tostring(shortcut.key or "]")
end

local function bindHotkey()
  if state.hotkey then
    state.hotkey:delete()
    state.hotkey = nil
  end
  local shortcut = state.config.shortcut
  local ok, hotkeyOrErr = pcall(function()
    return hs.hotkey.bind(shortcut.modifiers, shortcut.key, function()
      M.trigger()
    end)
  end)
  if not ok or not hotkeyOrErr then
    log.e("hotkey failed: " .. redact(hotkeyOrErr))
    hs.notify.show(
      "Screen Assistant",
      "",
      "Could not bind " .. shortcutLabel() .. ". Check shortcut.modifiers and shortcut.key in the config file."
    )
    return
  end
  state.hotkey = hotkeyOrErr
  if not state.enabled then
    state.hotkey:disable()
  end
end

local function menuItems()
  local enabledTitle = state.enabled and "Disable shortcut" or "Enable shortcut"
  return {
    {
      title = "Ask about this screen  " .. shortcutLabel(),
      fn = function()
        M.trigger(true)
      end,
    },
    {
      title = enabledTitle,
      fn = function()
        state.enabled = not state.enabled
        if state.hotkey then
          if state.enabled then
            state.hotkey:enable()
          else
            state.hotkey:disable()
          end
        end
      end,
    },
    {
      title = "Reload config",
      fn = function()
        loadConfig()
        bindHotkey()
      end,
    },
    { title = "-" },
    {
      title = "Quit Screen Assistant",
      fn = function()
        M.stop()
      end,
    },
  }
end

local function warnAccessibility()
  if hs.accessibilityState and hs.accessibilityState(false) == false then
    hs.notify.show(
      "Screen Assistant",
      "",
      "Turn on Accessibility for Hammerspoon so the keyboard shortcut works in every app."
    )
  end
end

function M.start()
  M.stop()
  state.enabled = true
  loadConfig()
  findRoot()
  bindHotkey()
  state.menubar = hs.menubar.new()
  if state.menubar then
    state.menubar:setTitle("AI")
    state.menubar:setTooltip("Screen Assistant")
    state.menubar:setMenu(function()
      return menuItems()
    end)
  end
  state.started = true
  _G.macAIAssistantStop = M.stop
  warnAccessibility()
  log.i("Screen Assistant started (" .. shortcutLabel() .. ")")
end

function M.stop()
  closePopup()
  if state.hotkey then
    state.hotkey:delete()
    state.hotkey = nil
  end
  if state.menubar then
    state.menubar:delete()
    state.menubar = nil
  end
  state.started = false
  state.enabled = false
end

return M
