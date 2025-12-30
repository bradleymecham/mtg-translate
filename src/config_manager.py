import configparser
import os

class ConfigManager:
    def __init__(self, config_file='config.ini'):
        self.config = configparser.ConfigParser()

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
        
        # Language Map stays for reference
        self.LANGUAGE_MAP = {
            "zh-CN": "Chinese (PRC)",
            "en": "English",
            "fr": "French",
            "ja": "Japanese",
            "ru": "Russian",
            "pt": "Portuguese",
            "es": "Spanish",
            "sw": "Swahili" 
            # Add future language codes here
        }
        
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
            code.strip(): self.LANGUAGE_MAP[code.strip()] 
            for code in raw_codes.split(',') 
                if code.strip() in self.LANGUAGE_MAP
        }
