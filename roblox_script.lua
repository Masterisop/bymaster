-- Roblox Join Coordinator Script
-- Execute this in your Roblox instance (requires HttpService access)
--
-- HOW IT WORKS:
-- 1. The script registers your Roblox instance with the coordinator server
-- 2. It sends heartbeats every few seconds so the dashboard knows you're online
-- 3. When someone clicks "MASS JOIN" on the dashboard, this script receives
--    a "join" command and searches all visible GUI for buttons containing "Join"
-- 4. It clicks all matching buttons using VirtualInputManager
--
-- SETUP:
-- Change SERVER_URL below to your deployed backend URL

local SERVER_URL = "http://localhost:8000"  -- <-- CHANGE THIS
local POLL_INTERVAL = 3  -- seconds between heartbeats

local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")
local player = Players.LocalPlayer

local clientId = nil

-- Register with the server
local function register()
    local ok, res = pcall(function()
        local gameName = "Unknown"
        pcall(function()
            gameName = game:GetService("MarketplaceService"):GetProductInfo(game.PlaceId).Name
        end)

        local body = HttpService:JSONEncode({
            username = player.Name,
            game_name = gameName
        })
        local response = HttpService:RequestAsync({
            Url = SERVER_URL .. "/api/register",
            Method = "POST",
            Headers = { ["Content-Type"] = "application/json" },
            Body = body
        })
        local data = HttpService:JSONDecode(response.Body)
        return data.client_id
    end)
    if ok then
        clientId = res
        print("[JoinCoord] Registered with ID: " .. clientId)
    else
        warn("[JoinCoord] Registration failed: " .. tostring(res))
    end
end

-- Find and click all GUI elements containing "Join" text
local function clickJoinButtons()
    local found = 0
    local playerGui = player:FindFirstChild("PlayerGui")
    if not playerGui then return 0 end

    local function searchGui(parent)
        for _, child in ipairs(parent:GetDescendants()) do
            if child:IsA("TextButton") or child:IsA("TextLabel") or child:IsA("ImageButton") then
                local text = ""
                if child:IsA("TextButton") or child:IsA("TextLabel") then
                    text = child.Text or ""
                end
                if string.lower(text):find("join") then
                    if child:IsA("TextButton") or child:IsA("ImageButton") then
                        local absPos = child.AbsolutePosition
                        local absSize = child.AbsoluteSize
                        local centerX = absPos.X + absSize.X / 2
                        local centerY = absPos.Y + absSize.Y / 2

                        -- Click using VirtualInputManager
                        pcall(function()
                            local vim = game:GetService("VirtualInputManager")
                            vim:SendMouseButtonEvent(centerX, centerY, 0, true, game, 0)
                            wait(0.05)
                            vim:SendMouseButtonEvent(centerX, centerY, 0, false, game, 0)
                        end)

                        found = found + 1
                        print("[JoinCoord] Clicked: " .. child:GetFullName())
                    end
                end
            end
        end
    end

    searchGui(playerGui)

    -- Also search CoreGui if accessible
    pcall(function()
        searchGui(game:GetService("CoreGui"))
    end)

    return found
end

-- Process commands from server
local function processCommands(commands)
    for _, cmd in ipairs(commands) do
        if cmd.action == "join" then
            print("[JoinCoord] Executing JOIN command...")
            local count = clickJoinButtons()
            -- Report result back to server
            pcall(function()
                HttpService:RequestAsync({
                    Url = SERVER_URL .. "/api/result",
                    Method = "POST",
                    Headers = { ["Content-Type"] = "application/json" },
                    Body = HttpService:JSONEncode({
                        client_id = clientId,
                        success = count > 0,
                        message = count > 0
                            and ("Clicked " .. count .. " join button(s)")
                            or "No join buttons found on screen"
                    })
                })
            end)
        end
    end
end

-- Heartbeat loop — polls server for commands
local function heartbeatLoop()
    while clientId and wait(POLL_INTERVAL) do
        local ok, res = pcall(function()
            local gameName = "Unknown"
            pcall(function()
                gameName = game:GetService("MarketplaceService"):GetProductInfo(game.PlaceId).Name
            end)

            local response = HttpService:RequestAsync({
                Url = SERVER_URL .. "/api/heartbeat",
                Method = "POST",
                Headers = { ["Content-Type"] = "application/json" },
                Body = HttpService:JSONEncode({
                    client_id = clientId,
                    username = player.Name,
                    game_name = gameName
                })
            })
            return HttpService:JSONDecode(response.Body)
        end)

        if ok and res and res.commands then
            if #res.commands > 0 then
                processCommands(res.commands)
            end
        elseif not ok then
            warn("[JoinCoord] Heartbeat failed: " .. tostring(res))
        end
    end
end

-- Clean up on game close
game:BindToClose(function()
    if clientId then
        pcall(function()
            HttpService:RequestAsync({
                Url = SERVER_URL .. "/api/disconnect",
                Method = "POST",
                Headers = { ["Content-Type"] = "application/json" },
                Body = HttpService:JSONEncode({ client_id = clientId })
            })
        end)
    end
end)

-- Start
register()
if clientId then
    heartbeatLoop()
end
