# **Quest Boo — Stream Buddy MVP**

*Your AI-powered pixel duck co-host, live on Twitch!*

![DuckBooIdling500HeadFeather](https://github.com/user-attachments/assets/066885cb-7a76-4458-a9e2-57d0b950773e)

---

## 🦆 Lore

Quest Boo is no ordinary duck. He’s Boo #99 from the [**Bitcoin Boos**](https://magiceden.us/ordinals/marketplace/bitcoin-boos), a collection of 101 pixel-perfect characters who live in the magical Boo Kingdom on block **775087** of the Bitcoin blockchain 

Created by Bootoshi, Quest Boo is his right winged man in the Kingdom. He’s got the classic Boo rectangle eyes, pink cheeks, and a toughened adventurer’s heart. And a sassy ass attitude :<

---

## 🎥 COMING TO LIFE !!!

<blockquote class="twitter-tweet" data-media-max-width="560"><p lang="en" dir="ltr">LETSSSSSSSSS GOOOOOOOOOOOOOOOOOOOOOOOOOOO !!!!!!<br><br>I GOT MY AI COMPANION CONNECTED TO TWITCH CHAT<br><br>QUEST BOO IS NOW OFFICIALLY MY STREAMING BUDDY YAYYYYYYY <a href="https://t.co/iNqIq41Etc">pic.twitter.com/iNqIq41Etc</a></p>&mdash; BOOTOSHI 👑 (@KingBootoshi) <a href="https://twitter.com/KingBootoshi/status/1966640938450907235?ref_src=twsrc%5Etfw">September 12, 2025</a></blockquote> <script async src="https://platform.twitter.com/widgets.js" charset="utf-8"></script>

Quest Boo is officially alive—animated, AI-driven, and connected to Twitch chat in real time. Viewers can talk to him directly, and Bootoshi can hold voice-to-voice conversations with his AI buddy live on stream.

---

## ARCHITECTURE

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

---

## 🛠️ Setup

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

---

## 🎛️ Controls

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

---

## 📖 Runbook

1. Start frontend (PixiJS overlay).
2. Start backend (AI pipeline).
3. Add frontend to OBS.
4. Toggle mic → Talk or let chat summon Boo.

Quest Boo will handle the rest.

---

## 💡 QUEST BOO IS SPECIAL !!!

Quest Boo is the first AI character I’ve ever created (Feb 2023 in Discord) it's always been my dream to turn him into a streaming partner. I wasn't skilled enough though! After two years of grinding engineering with inspiration from Pipecat I've finally taken him on as a project. He reacts, talks, jokes, and *lives* alongside me and my community.

He will be connected to my product, Daybloom - https://www.daybloom.ai/ - to ensure his digital mind continues to grow with every stream 
