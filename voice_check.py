import os
from google.cloud import texttospeech
from google.oauth2 import service_account

def list_swahili_voices(key_path):
    # Explicitly load the service account credentials
    try:
        creds = service_account.Credentials.from_service_account_file(key_path)
        client = texttospeech.TextToSpeechClient(credentials=creds)
        
        # Request the list of available voices
        response = client.list_voices()

        print(f"{'Voice Name':<35} | {'Gender':<10} | {'Quality'}")
        print("-" * 70)

        found_any = False
        for voice in response.voices:
            # Filtering for Swahili (sw)
            if "sw" in voice.language_codes[0]:
                found_any = True
                gender = texttospeech.SsmlVoiceGender(voice.ssml_gender).name
                
                # Determine "Quality" based on naming convention
                quality = "Standard"
                if "Wavenet" in voice.name: quality = "High (WaveNet)"
                if "Neural2" in voice.name: quality = "Ultra (Neural2)"
                if "Chirp" in voice.name: quality = "Studio (Chirp)"

                print(f"{voice.name:<35} | {gender:<10} | {quality}")
        
        if not found_any:
            print("No Swahili voices found. Ensure the TTS API is enabled for this project.")

    except Exception as e:
        print(f"Failed to authenticate or fetch voices: {e}")

if __name__ == "__main__":
    # Update this path if the file is in a different subdirectory
    KEY_FILE = "englishtexttojapanese-4f53c87fe8c3.json"
    list_swahili_voices(KEY_FILE)
