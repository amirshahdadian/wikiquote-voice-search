#!/usr/bin/env python3
"""
Test script for autocomplete with TTS functionality
Demonstrates how partial quote searches trigger text-to-speech output
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.wikiquote_voice.search.service import QuoteSearchService
from src.wikiquote_voice.config import Config
from services.tts_service import TTSService
import time


def test_autocomplete_with_tts():
    """Test autocomplete functionality with TTS output"""
    
    print("\n" + "="*70)
    print("  AUTOCOMPLETE WITH TEXT-TO-SPEECH TEST")
    print("="*70)
    
    # Initialize services
    print("\n📊 Initializing services...")
    search_service = QuoteSearchService(
        Config.NEO4J_URI,
        Config.NEO4J_USERNAME,
        Config.NEO4J_PASSWORD
    )
    
    try:
        search_service.connect()
        print("✅ Connected to Neo4j")
        
        # Build semantic index
        print("🔨 Building semantic search index...")
        search_service.build_semantic_index(sample_size=5000)
        
        # Initialize TTS
        print("🔊 Loading TTS models...")
        tts_service = TTSService(device='cpu')
        
        # Test queries (partial quotes)
        test_queries = [
            "to be or not",
            "imagination is more",
            "the only thing we have",
            "in the end",
            "all you need is"
        ]
        
        print("\n" + "="*70)
        print("  TESTING PARTIAL QUOTE AUTOCOMPLETE + TTS")
        print("="*70)
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n{'─'*70}")
            print(f"Test {i}: '{query}'")
            print(f"{'─'*70}")
            
            # Search for autocomplete results
            results = search_service.search_quotes(query, limit=1)
            
            if results:
                top_match = results[0]
                quote_text = top_match['quote_text']
                author_name = top_match['author_name']
                search_type = top_match.get('search_type', 'unknown')
                
                print(f"\n✅ Top Match Found:")
                print(f"   Quote: \"{quote_text}\"")
                print(f"   Author: {author_name}")
                print(f"   Search Type: {search_type}")
                
                if 'match_position' in top_match:
                    print(f"   Match Position: {top_match['match_position']}")
                
                if 'relevance_score' in top_match:
                    print(f"   Relevance: {top_match['relevance_score']:.2%}")
                
                # Generate TTS
                speech_text = f'"{quote_text}" by {author_name}'
                output_file = f"test_autocomplete_{i}.wav"
                
                print(f"\n🔊 Generating TTS: {output_file}")
                
                try:
                    tts_service.synthesize(
                        text=speech_text,
                        output_path=output_file,
                        pitch_shift=1.0,
                        speaking_rate=0.9
                    )
                    print(f"   ✅ Audio saved to: {output_file}")
                    print(f"   🎵 Speech: {speech_text[:80]}...")
                
                except Exception as e:
                    print(f"   ❌ TTS failed: {e}")
            
            else:
                print(f"\n❌ No matches found for '{query}'")
            
            # Small delay between tests
            time.sleep(0.5)
        
        print("\n" + "="*70)
        print("  TEST COMPLETE!")
        print("="*70)
        print("\n📁 Check the generated .wav files to hear the results!")
        print("💡 In the Streamlit app, this happens automatically when typing partial quotes.\n")
    
    except ImportError as e:
        print(f"\n❌ Missing dependencies: {e}")
        print("\nPlease install:")
        print("  - NeMo toolkit: pip install nemo_toolkit[asr,tts]==1.21.0")
        print("  - scikit-learn: pip install scikit-learn")
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        search_service.close()
        print("\n👋 Test session closed")


def demo_usage():
    """Show example usage in code"""
    print("\n" + "="*70)
    print("  CODE EXAMPLE: Autocomplete with TTS")
    print("="*70)
    
    example_code = '''
# Example: Autocomplete with TTS in your app

from src.wikiquote_voice.search.service import QuoteSearchService
from services.tts_service import TTSService

# Initialize services
search = QuoteSearchService(uri, username, password)
tts = TTSService(device='cpu')

# User types partial quote
user_input = "to be or not"

# Get best match
results = search.search_quotes(user_input, limit=1)

if results:
    top_match = results[0]
    
    # Check if it's a partial quote match
    if 'partial_match' in top_match.get('search_type', ''):
        # Generate speech for the complete quote
        speech_text = f'"{top_match["quote_text"]}" by {top_match["author_name"]}'
        
        # Synthesize to audio
        tts.synthesize(
            text=speech_text,
            output_path="autocomplete.wav",
            speaking_rate=0.9  # Slightly slower for clarity
        )
        
        print(f"🔊 Playing: {speech_text}")
'''
    
    print(example_code)
    print("="*70 + "\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test autocomplete with TTS")
    parser.add_argument('--demo', action='store_true', help="Show code example only")
    args = parser.parse_args()
    
    if args.demo:
        demo_usage()
    else:
        test_autocomplete_with_tts()
