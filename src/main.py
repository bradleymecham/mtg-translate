import asyncio
import queue
import aioconsole
import concurrent.futures
from config_manager import ConfigManager
from transcription import TranscriptionEngine
from translation import TranslationEngine
from networking import NetworkServer

async def wait_for_keypress(stop_event, translation_queue, cfg, transcriber):
    print("Commands: 'q' to quit, 'nt' for New Talk,"
        "or a lang code (e.g., 'es', 'en', 'fr','cn','sw')")
    while not stop_event.is_set():
        try:
            user_input = (await aioconsole.ainput()).strip().lower()
            if user_input == 'q':
                stop_event.set()
                break
            elif user_input == 'nt':
                translation_queue.put("New Talk")
            elif user_input in cfg.LANGUAGE_MAP:
                print(f"Switching transcription to: {cfg.LANGUAGE_MAP[user_input].display_name}")
                cfg.curr_lang = user_input # Update the shared config
                transcriber.restart_signal() # Trigger restart in other threads
            else:
                print(f"Unknown command or language code: {user_input}")
        except Exception as e:
            print(f"Error reading input: {e}")


async def main():
    # 1. Setup shared resources
    stop_event = asyncio.Event()
    translation_queue = queue.Queue()
    loop = asyncio.get_running_loop()
    executor = concurrent.futures.ThreadPoolExecutor()

    # 2. Initialize modules
    cfg = ConfigManager()
    net = NetworkServer()
    transcriber = TranscriptionEngine(cfg, translation_queue, stop_event)
    translator = TranslationEngine(cfg, translation_queue, net, stop_event)

    # 3. Start Servers and Tasks
    await net.register_mDNS()
    await net.start_servers()
    
    tasks = [
        loop.run_in_executor(executor, transcriber.audio_stream, loop),
        loop.run_in_executor(executor, transcriber.transcribe_loop, loop),
        loop.run_in_executor(executor, translator.translate_loop, loop),
        wait_for_keypress(stop_event, translation_queue, cfg, transcriber)
    ]
    

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    finally:
        #TODO; cancel tasks (audio_stream, transcribe_loop, translate_loop)
        tasks[0].cancel() # audio_stream
        tasks[1].cancel() # transcribe_loop
        tasks[2].cancel() # translate_loop

        executor.shutdown(wait=True)

        await net.stop_servers()
        await net.unregister_mDNS()

        stop_event.clear()

        print("Server stopped and resources cleaned up")

if __name__ == "__main__":
    asyncio.run(main())
