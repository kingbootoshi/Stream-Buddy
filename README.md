# Duck Buddy - Stream Overlay

A PixiJS-powered animated duck character for OBS stream overlays. Features a modular paper-doll rig with multiple states and animations.

## Features

- **Animated Character**: Layered sprite system with body parts (body, head, eyes, mouth, hands, feet, hat)
- **Multiple States**: idle, walk, talk, angryTalk, handsCrossed
- **Natural Behaviors**: Random blinking, idle breathing, walking bobbing
- **OBS Ready**: Transparent background, optimized for browser source overlays
- **Interactive Controls**: Keyboard shortcuts and JavaScript API for state changes

## Quick Start

```bash
npm install
npm run dev
```

Open the served URL in your browser or add it as a Browser Source in OBS.

## Controls

### Keyboard Shortcuts
- `1` - Idle state
- `2` - Walk state  
- `3` - Talk state
- `4` - Angry talk state
- `5` - Hands crossed state
- `h` - Show hat
- `H` - Hide hat

### JavaScript API
```javascript
// Available in browser console or external scripts
window.duckBuddy.setState('talk');
window.duckBuddy.setState('walk');
window.duckBuddy.setHat('hat1');
window.duckBuddy.setHat(null); // Remove hat
```

## Asset Structure

All character assets are located in `public/assets/` and follow a consistent naming convention:

- **Body**: `Body.png`
- **Head**: `Head.png`
- **Eyes**: `Eyes.png`, `Eyes_Blinking1-3.png`, `Eyes_Angry.png`, `Eyes_Happy.png`
- **Mouth**: `Mouth.png`, `Mouth_Talking1-3.png`, `Mouth_Talking_Angry1-3.png`
- **Hands**: `Hands.png`, `Hands_Crossed.png`, `Hands_Pointing.png`
- **Feet**: `Feet.png`, `Feet_Walking1-5.png`
- **Hats**: `Hat1.png`, `Hat2.png`, `Hat3.png`

## Technical Details

- **Engine**: PixiJS v8 with modern initialization API
- **Architecture**: Modular sprite composition with z-index layering
- **Performance**: GPU-accelerated rendering, frame-rate independent timing
- **Compatibility**: Modern browsers with WebGL support

## Development

The character rig is built using a layered sprite system where each body part is an independent `AnimatedSprite`. This allows for:

- Individual part animation (mouth talking, feet walking, eyes blinking)
- Easy texture swapping for different emotions/states
- Efficient GPU rendering with minimal draw calls

### Key Files

- `src/DuckBuddy.ts` - Main character rig and state machine
- `src/main.ts` - Application bootstrap and asset loading
- `src/logger.ts` - Lightweight browser logging utility

## OBS Integration

1. Add Browser Source in OBS
2. Set URL to your dev server (e.g., `http://localhost:5173`)
3. Set Width/Height as needed
4. The background is automatically transparent

## License

MIT License - Feel free to use for your streams and projects!
