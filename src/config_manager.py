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
            "ward", "Aaronic priesthood", "In the name of Jesus Christ",
            "bishopric", "Relief Society", "elders", "deacons",
            "quorum", "testimony", "atonement", "ministering brother",
            "ministering sister", "ministering interview", 
            "Melchizedek priesthood",
            "Dallin H. Oaks", "Henry B. Eyring", "D. Todd Christofferson",
            "Deiter F. Uchtdorf", "David A. Bednar", "Quentin L. Cook",
            "Neil L. Andersen", "Ronald A. Rasband", "Gary E. Stevenson",
            "Dale G. Renlund", "Gerrit W. Gong", "Ulisses Soares",
            "Patrick Kearon", "Gerald Causse", "Eyring", "Uchtdorf", "Bednar",
            "Quentin", "Rasband", "Renlund", "Soares", "Kearon", "Causse",
            "Primary", "Primary songs", "righteous", "area presidency",
            "first presidency", "Quorum of the Twelve", "ordained",
            "Doctrine and Covenants", "first estate", "second estate",
            "Fall of Adam", "exaltation"
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
        
        try:
            self.hw_rate = int(self.config['AUDIO']['hw_rate'])
        except (KeyError, ValueError):
            print("Hardware sample rate unspecified.  Defaulting to 16000")
            self.hw_rate = 16000
        
        try:
            self.input_device_index = int(
                self.config['AUDIO']['input_device_index'])
        except (KeyError, ValueError):
            print("Input device index unspecified. Using system default")
            self.input_device_index = None

        try:
            self.output_device_index = int(
                self.config['AUDIO']['output_device_index'])
        except (KeyError, ValueError):
            print("Output device index unspecified. Using system default")
            self.output_device_index = None

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
