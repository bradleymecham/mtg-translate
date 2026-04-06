import asyncio
import queue
import aioconsole
import concurrent.futures
import argparse
from config_manager import ConfigManager
from transcription import TranscriptionEngine
from translation import TranslationEngine
from networking import LanguagePortServer, NetworkServer
from text_to_speech import TextToSpeechEngine

async def wait_for_keypress(stop_event, translation_queue, cfg, transcriber):
    langs = ", ".join(cfg.LANGUAGE_MAP.keys())
    print("\nCommands:")
    print("  'p' - Pause/Resume Transcription")
    print("  'pc' - Enable/Disable punctuation")
    print("  'm' - Enable/Disable Monitor")
    print("  'nt' - Indicate a New Talk")
    print("  'q' - Quit applicationto quit")
    print(f"  or a lang code ({langs})")
    print("    to specify a new input language")

    while not stop_event.is_set():
        try:
            user_input = (await aioconsole.ainput()).strip().lower()
            if user_input == 'q':
                stop_event.set()
                break
            elif user_input == 'nt':
                translation_queue.put("New Talk")
            elif user_input == 'p':
                transcriber.toggle_pause()
            elif user_input == 'pc':
                transcriber.toggle_punctuation()
            elif user_input == 'm':
                transcriber.toggle_monitor()
            elif user_input in cfg.LANGUAGE_MAP:
                print(f"Switching transcription to: {cfg.LANGUAGE_MAP[user_input].display_name}")
                cfg.curr_lang = user_input
                transcriber.restart_signal()
            else:
                print(f"Unknown command or language code: {user_input}")
        except Exception as e:
            print(f"Error reading input: {e}")

async def audio_broadcast_worker(transcriber, net_server, stop_event, loop):
    """Bridge between the audio queue and the network broadcast."""
    while not stop_event.is_set():
        try:
            # Get 16kHz mono chunk from the queue (thread-safe)
            # We use a timeout so it can check stop_event regularly
            chunk = await loop.run_in_executor(
                None, lambda: transcriber.broadcast_queue.get(timeout=0.5)
            )
            if chunk:
                await net_server.broadcast_binary(chunk)
        except queue.Empty:
            continue
        except Exception as e:
            if not stop_event.is_set():
                print(f"Live audio broadcast error: {e}")
            await asyncio.sleep(0.1)

async def main():
    parser = argparse.ArgumentParser(description="Master Translation Server")
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="Enable debug mode")
    args = parser.parse_args()

    # Setup shared resources
    stop_event = asyncio.Event()
    translation_queue = queue.Queue()
    loop = asyncio.get_running_loop()
    executor = concurrent.futures.ThreadPoolExecutor()

    try:
        # Initialize modules
        cfg = ConfigManager()
        cfg.debug_mode = args.verbose

        transcriber = TranscriptionEngine(cfg, translation_queue, stop_event)
        net = NetworkServer(cfg, transcriber)
        tts = TextToSpeechEngine(cfg, net)

        # Create port servers for each language
        port_servers = {}
    
        print("\n=== Language Port Assignments ===")
        for lang_code in cfg.target_languages:
            lang_info = cfg.LANGUAGE_MAP[lang_code]
            port_server = LanguagePortServer(
                lang_code, lang_info.port, cfg, tts, loop,
                on_client_change = net.update_transcription_state
            )
            print(f"{lang_info.display_name} ({lang_code}): port {lang_info.port}")
            port_servers[lang_code] = port_server

            net.language_servers.append(port_server)
            await port_server.start()

        # Create master translation engine with port servers
        translator = TranslationEngine(cfg, translation_queue, net,
                                       port_servers, stop_event)

        # Start all servers
        await net.register_mDNS()
        await net.start_servers()

        print("\n=== Master Server Ready ===")
        print("Web interface: http://captions.local:8080")
        print("Slaves can connect to language-specific ports listed above\n")

        tasks = [
            loop.run_in_executor(executor, transcriber.audio_stream, loop),
            loop.run_in_executor(executor, transcriber.monitor_loop, loop),
            loop.run_in_executor(executor, transcriber.transcribe_loop, loop),
            loop.run_in_executor(executor, translator.translate_loop, loop),
            asyncio.create_task(
                audio_broadcast_worker(transcriber, net, stop_event, loop)),
            wait_for_keypress(stop_event, translation_queue, cfg, transcriber)
        ]

        await asyncio.gather(*tasks)

    except asyncio.CancelledError:
        pass
    except (FileNotFoundError, KeyError) as e:
        print(f"\n[CONFIGURATION ERROR] {e}")
        print("Please check config.ini and service account JSON file.")
    except Exception as e:
        print(f"\n[UNEXPECTED ERROR] {e}")
    finally:
        print("\nCleaning up resources . . . ")

        # Cancel all background tasks except wait_for_keypress
        if 'tasks' in locals():
            for task in tasks[:-1]:
                task.cancel()

        executor.shutdown(wait=True)

        # Stop language port servers
        if 'port_servers' in locals():
            for port_server in port_servers.values():
                await port_server.stop()

        if 'net' in locals():
            await net.stop_servers()
            await net.unregister_mDNS()

        stop_event.clear()

        print("Master server stopped and resources cleaned up")

if __name__ == "__main__":
    asyncio.run(main())
