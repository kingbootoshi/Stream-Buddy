<div align="center">
  
# **Quest Boo — Stream Buddy MVP**

*Your AI-powered pixel duck co-host, live on Twitch!*

<img src="https://github.com/user-attachments/assets/066885cb-7a76-4458-a9e2-57d0b950773e" alt="DuckBooIdling500HeadFeather">
</div>

<div align="center">

## 🦆 Lore

</div>

Quest Boo is no ordinary duck. He’s Boo #99 from the [**Bitcoin Boos**](https://magiceden.us/ordinals/marketplace/bitcoin-boos), a collection of 101 pixel-perfect characters who live in the magical Boo Kingdom on block **775087** of the Bitcoin blockchain 

Created by Bootoshi, Quest Boo is his right winged man in the Kingdom. He’s got the classic Boo rectangle eyes, pink cheeks, and a toughened adventurer’s heart. And a sassy ass attitude :<

<div align="center">

## 🎥 COMING TO LIFE !!!

</div>

[▶ Watch Quest Boo’s debut on Twitter/X](https://x.com/KingBootoshi/status/1966640938450907235)
Quest Boo is officially alive! Animated, AI-driven, and connected to Twitch chat in real time. Viewers can talk to him directly, and Bootoshi can hold voice-to-voice conversations with his AI buddy live on stream.

<div align="center">

## ARCHITECTURE

</div>

Quest Boo is split into two powerful parts:

### **Frontend (Duck Rig + Overlay)**

* Modular **pixel-art rig** (body, head, eyes, mouth, hands, feet, hats).
* State system for moods: `idle`, `walk`, `talk`, `happyTalk`, `angryTalk`, `handsCrossed`.
* Smooth animations (breathing, blinking, walking bobbing).
* Browser-source overlay ready for **OBS**.

### **Backend (AI Brain)**

* Built with **Pipecat AI pipeline** (parallel voice + Twitch branches).
* **Voice to Voice**: Bootoshi speaks → STT → LLM → TTS → Quest Boo replies in his own voice.
* **Twitch Chat Aware**: Viewers type trigger words, Boo responds in real time.
* Parallel design ensures Twitch chat isn’t blocked by mic state.

<div align="center">

## 🛠️ Setup

</div>

### Backend

```bash
cd backend
cp .env.example .env   # add your keys
pip install -r requirements.txt
python main.py
```

### Frontend

```bash
npm install
npm run dev
```

Add the dev server URL as a Browser Source in OBS (transparent background).

<div align="center">

## 🎛️ Controls

</div>

We recommend [Hammerspoon](https://www.hammerspoon.org/) (macOS) for system-wide mic toggling.

Example hotkey (`Cmd+Alt+Space`):

```lua
local overlayKey = "devlocal"
local base = "http://127.0.0.1:8710"
local function post(path) hs.http.asyncPost(base..path, "", { ["X-Overlay-Key"]=overlayKey }, function() end) end
hs.hotkey.bind({"cmd","alt"}, "space", function() post("/api/listen/toggle") end)
```

Once unmuted:

* **Talk to Boo directly with your mic.**
* Or **trigger him from Twitch chat** with configured keywords (`questboo`, `duck`, `chicken`).

<div align="center">

## 📖 Runbook

</div>

1. Start frontend (PixiJS overlay).
2. Start backend (AI pipeline).
3. Add frontend to OBS.
4. Toggle mic → Talk or let chat summon Boo.

Quest Boo will handle the rest.

<div align="center">

## ❤️ FIN

</div>

Quest Boo is the first AI character I’ve ever created (Feb 2023 in Discord) it's always been my dream to turn him into a streaming partner. I wasn't skilled enough though! After two years of grinding engineering with inspiration from Pipecat I've finally taken him on as a project. He reacts, talks, jokes, and *lives* alongside me and my community.

He will be connected to my product, [Daybloom](https://www.daybloom.ai/) to ensure his digital mind continues to grow with every stream 
<div align="center">
<img width="1705" height="1070" alt="image" src="https://github.com/user-attachments/assets/608c6265-a8e4-4ed5-9d5a-7b78c6e3ccf3" />
</div>
