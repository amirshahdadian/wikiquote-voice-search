# Autocomplete with Text-to-Speech

## Overview

When users type part of a quote in the search interface, the system automatically:
1. Detects that it's a partial quote (not just keywords)
2. Finds the most likely matching complete quote
3. Outputs the complete quote using text-to-speech

## How It Works

### Detection

The system automatically detects partial quotes vs keyword searches using a heuristic:
- Quote fragments with 3+ words are treated as partial quotes.
- Natural-language commands like `quotes about courage` or `show me Einstein quotes` stay on the normal search path.

### Search Strategy

When a partial quote is detected, the system uses multiple matching strategies:

1. **Exact Substring Match** (highest priority)
   - Finds quotes containing the exact phrase
   - Identifies match position (beginning, middle, or end)

2. **Word Sequence Match**
   - Matches quotes with all words in the same order
   - Accounts for minor variations

3. **Advanced Fuzzy Matching**
   - Finds quotes with high word overlap
   - Position-aware scoring

### TTS Output

The top matching quote is automatically converted to speech:
- Format: `"{quote_text}" by {author_name}`
- Speaking rate: 0.9x (slightly slower for clarity)
- Standard pitch and energy

## Usage in the App

```python
# User types partial quote
query = "to be or not"

# System automatically:
# 1. Detects partial quote
# 2. Searches for matches
# 3. Generates TTS for top result
# 4. Plays audio automatically
```

TTS can be enabled in the voice-enabled UI flow or triggered directly from Python services.

## Code Integration

### Using Search Service Directly

```python
from src.wikiquote_voice.search.service import QuoteSearchService
from services.tts_service import TTSService

# Initialize
search = QuoteSearchService(uri, username, password)
tts = TTSService(device='cpu')

# Search with autocomplete
results = search.search_quotes("imagination is more", limit=1)

if results and 'partial_match' in results[0].get('search_type', ''):
    top_match = results[0]
    
    # Generate speech
    speech_text = f'"{top_match["quote_text"]}" by {top_match["author_name"]}'
    tts.synthesize(text=speech_text, output_path="autocomplete.wav")
```

## Examples

### Example 1: Beginning of Quote
```
Input:  "to be or not"
Output: 🔊 "To be or not to be, that is the question" by William Shakespeare
Match:  beginning
```

### Example 2: Middle of Quote
```
Input:  "the only thing we have"
Output: 🔊 "The only thing we have to fear is fear itself" by Franklin D. Roosevelt
Match:  middle
```

### Example 3: End of Quote
```
Input:  "in the end"
Output: 🔊 "In the end, we will remember not the words of our enemies..." by Martin Luther King Jr.
Match:  end
```

## Testing

Run the test script to see autocomplete with TTS in action:

```bash
# Full demo with TTS generation
python3 scripts/demo_autocomplete_tts.py

# Show code example only
python3 scripts/demo_autocomplete_tts.py --demo
```

## Requirements

- **NeMo Toolkit**: `pip install "nemo-toolkit[asr,tts]>=2.4,<3"`
- Active Neo4j database with quotes indexed
- On Apple Silicon, ASR `auto` prefers PyTorch `mps`, while NeMo-backed TTS stays on CPU by default

## Configuration

### TTS Settings

Default settings for autocomplete TTS:
```python
{
    'pitch_scale': 1.0,      # Normal pitch
    'speaking_rate': 0.9,    # 90% speed (slightly slower)
    'energy_scale': 1.0      # Normal volume
}
```

### Search Settings

Partial quote detection threshold:
```python
min_words = 3  # Minimum words before quote-fragment heuristics apply
```

## Performance

- **Search Time**: ~100-500ms (depending on query complexity)
- **TTS Generation**: ~1-3 seconds (first call slower due to model loading)
- **Audio Quality**: 22050 Hz WAV, mono

## Troubleshooting

### TTS Not Working

1. Check NeMo installation:
   ```bash
   python -c "import importlib.util; print(importlib.util.find_spec('nemo') is not None)"
   ```

2. Check models are loading:
   ```python
   from services.tts_service import TTSService
   tts = TTSService(device='cpu')
   tts.load_models()  # Should not error
   ```

### No Search Results

1. Verify Neo4j connection
2. Run search warmup hook (no semantic index is built in current version):
   ```python
   search_service.build_semantic_index(sample_size=5000)
   ```

### Audio Not Playing

1. Check file was created: `ls -la *.wav`
2. Verify WAV format: `file autocomplete.wav`
3. Test playback: `afplay autocomplete.wav` (macOS)

## Future Enhancements

Potential improvements:
- [ ] Personalized TTS voice per user
- [ ] Multiple language support
- [ ] Emotion/sentiment-aware speech
- [ ] Real-time streaming TTS
- [ ] Audio caching for common quotes
