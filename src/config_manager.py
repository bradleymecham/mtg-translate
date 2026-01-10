import configparser
import os
from dataclasses import dataclass

@dataclass
class LanguageInfo:
    display_name: str
    speech_code: str
    translation_code: str
    # Future options
    # rtl: bool = False
    # font_preference: str = "Arial"
    # formal_mode: bool = False
    # requires_special_chars: bool = False
    # gender_variants: bool = False
    # tone_markers: bool = False
    # voice_gender: bool # For TTS

class ConfigManager:
    def __init__(self, config_file='config.ini'):
        self.config = configparser.ConfigParser()

        # Language Map stays for reference
        self.LANGUAGE_MAP = {
            "cn": LanguageInfo("Chinese (PRC)","cmn-Hans-CN","zh-Hans"),
            "en": LanguageInfo("English","en-US","en"),
            "fr": LanguageInfo("French","fr","fr"),
            "ja": LanguageInfo("Japanese","ja-JP","ja"),
            "ru": LanguageInfo("Russian","ru-RU","ru"),
            "pt": LanguageInfo("Portuguese","pt-BR","pt-BR"),
            "es": LanguageInfo("Spanish","es-US","es-US"),
            "es2": LanguageInfo("Spanish (Mexico)","es-MX","es-MX"),
            "sw": LanguageInfo("Swahili","sw","sw"),
            "sw2": LanguageInfo("Swahili (Kenya)","sw-KE","sw")
            # Add future language codes here
        }

        # Default transcription to English for now; can put in config file next
        self.curr_lang = 'en'
        
        self.base_keywords = [
            "Ward", "Aaronic Priesthood", "In the name of Jesus Christ",
            "Bishopric", "Relief Society", "Elders", "Deacons",
            "Quorum", "Testimony", "Atonement", "Gospel",
            "Melchizedek Priesthood"
        ]

        # Read custom words from config.ini
        try:
            custom_raw = self.config['SPEECH']['custom_keywords']
            custom_list = [
                word.strip() for word in custom_raw.split(',') if word.strip()]
        except (KeyError, ValueError):
            custom_list = []

        # Merge both lists for the final set of hints
        self.church_keywords = self.base_keywords + custom_list

        # TODO: If config file is not present, throw an error
        file_read = self.config.read(config_file)
        
        if not file_read:
            raise FileNotFoundError(
             f"Error: Config file not found. Expected file: {config_file}")
        
        # Load core settings
        try:
            self.google_credentials = (
                self.config['AUTHENTICATION']['google_credentials_json'])

        except (KeyError, ValueError):
            print("Google Credentials value required")
            raise
            
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.google_credentials
        
        try:
            self.num_channels = int(self.config['AUDIO']['num_channels'])
        except (KeyError, ValueError):
            print("Number of audio channels unspecified.  Defaulting to 1")
            self.num_channels = 1
        
                
        # Read in language codes -- default to English if none are specified
        try:
            raw_codes = (
                self.config['TRANSLATION']['target_language_codes'])
        except (KeyError, ValueError):
            print(
                "Valid 'target_language_codes' not found in config.ini. "
                "Defaulting to English.")
            raw_codes = "en"

        self.target_languages = {
            code.strip(): self.LANGUAGE_MAP[code.strip()].display_name
            for code in raw_codes.split(',') 
                if code.strip() in self.LANGUAGE_MAP
        }
