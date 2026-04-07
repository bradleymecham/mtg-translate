import asyncio
import psutil
import ipaddress
import websockets
from aiohttp import web
import aiofiles
from zeroconf.asyncio import AsyncZeroconf
from zeroconf import ServiceInfo
import socket
import json
import qrcode
import io
import os


class LanguagePortServer:
    """Manages individual port servers for each language"""
    def __init__(self, lang_code, port, config, tts_engine, loop, on_client_change=None):
        self.lang_code = lang_code
        self.port = port
        self.config = config
        self.tts_engine = tts_engine
        self.loop = loop
        self.clients = set()
        self.server = None
        self.on_client_change = on_client_change

    async def handle_client(self, reader, writer):
        """Handle a new slave connection"""
        addr = writer.get_extra_info('peername')
        print(f"[{self.lang_code}:{self.port}] Slave connected from {addr}")
        self.clients.add((reader, writer))

        if self.on_client_change:
            self.on_client_change()

        try:
            # Keep connection alive and wait for disconnect
            while True:
                data = await reader.read(100)
                if not data:
                    break
                await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[{self.lang_code}:{self.port}] Connection error: {e}")
        finally:
            print(f"[{self.lang_code}:{self.port}] Slave disconnected from {addr}")
            self.clients.discard((reader, writer))
            writer.close()
            await writer.wait_closed()

            if self.on_client_change:
                self.on_client_change()

    async def start(self):
        """Start the port server"""
        self.server = await asyncio.start_server(
            self.handle_client, '0.0.0.0', self.port)
        lang_name = self.config.LANGUAGE_MAP[self.lang_code].display_name
        print(f"✓ Language server started: {lang_name} on port {self.port}")

    async def stop(self):
        """Stop the port server"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def broadcast_audio(self, payload):
        """Broadcast audio to all connected slaves"""
        if not payload:
            return  # No payload, we shouldn't be here
        if not self.clients:
            return  # No clients, skip broadcast

        # Serialize to JSON and encode
        json_data = json.dumps(payload).encode('utf-8')
        # Send length prefix (4 bytes) followed by data
        length_prefix = len(json_data).to_bytes(4, byteorder='big')
        full_message = length_prefix + json_data

        # Broadcast to all connected clients
        disconnected = []
        for reader, writer in self.clients:
            try:
                writer.write(full_message)
                await writer.drain()
            except Exception as e:
                print(f"[{self.lang_code}:{self.port}] Error sending to client: {e}")
                disconnected.append((reader, writer))

        # Remove disconnected clients
        for client in disconnected:
            self.clients.discard(client)

class NetworkServer:
    def __init__(self, config, transcriber=None):
        self.clients = set()
        self.config = config
        self.transcriber = transcriber
        self.zeroconf = AsyncZeroconf()
        self.language_servers = []

        self.ip_addresses = self.get_ip_addresses()
        for iface, iface_type, ip in self.ip_addresses:
            print(f"{iface} ({iface_type}): {ip}")

    def update_transcription_state(self):
            """Centralized logic to start/stop Google Speech based on any client activity."""
            if not self.transcriber:
                return

            # 1. Count Web users
            web_count = len(self.clients)

            # 2. Count Slave users across ALL language ports
            slave_count = sum(len(lp.clients) for lp in self.language_servers)

            total_active = web_count + slave_count

            # 3. Decision Engine
            if total_active > 0 and self.transcriber.is_paused:
                print(f"--- Client detected ({total_active} total). Activating transcription. ---")
                self.transcriber.toggle_pause()
            elif total_active == 0 and not self.transcriber.is_paused:
                print("--- No clients remaining. Sleeping transcription. ---")
                self.transcriber.toggle_pause()

    def get_interface_type(self,interface_name):
        name = interface_name.lower()
        if "wi-fi" in name or "wlan" in name or "wifi" in name:
            return "Wi-Fi"
        elif "eth" in name or "en" in name:
            return "Ethernet"
        else:
            return "Unknown"


    def get_ip_addresses(self):
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        result = []

        for interface, addr_list in addrs.items():
            if not stats.get(interface) or not stats[interface].isup:
                continue
            for addr in addr_list:
                if addr.family == socket.AF_INET:
                    ip = addr.address
                    ip_obj = ipaddress.ip_address(ip)
                    if ip_obj.is_loopback or ip_obj.is_link_local:
                        continue
                    interface_type = self.get_interface_type(interface)
                    result.append((interface, interface_type, ip))
        return result

    def generate_server_qr(self, url):

        # Ensure the directory exists
        img_dir = "static/img"
        if not os.path.exists(img_dir):
            os.makedirs(img_dir)

        # Create high-res QR for a 240x240 display / phone
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        img_path = os.path.join(img_dir, "server_qr.png")
        img.save(img_path)

        print(f"✓ QR Code generated for {url} at {img_path}")


    def print_qr_to_terminal(self,url):
        # Create the QR object
        qr = qrcode.QRCode(version=1, box_size=1, border=2)
        qr.add_data(url)
        qr.make(fit=True)

        # We use a StringIO buffer to capture the output
        f = io.StringIO()
        qr.print_ascii(out=f, invert=True) # invert=True makes it work in dark terminals
        f.seek(0)

        print("\n" + "="*40)
        print(" SCAN TO CONNECT TO THIS server")
        print("="*40 + "\n")
        print(f.read())
        print(f"URL: {url}\n")
        print("="*40 + "\n")

    async def http_handler(self, request):
        # Serve the HTML client file
        try:
            async with aiofiles.open('static/TranslationClient.html',
                mode='r') as f:
                    html_content = await f.read()
            return web.Response(text=html_content, content_type='text/html')
        except FileNotFoundError:
            return web.Response(text="TranslationClient.html not found", 
                                status=404)
        pass

    async def websocket_handler(self, websocket):
        print(f"Client connected: {websocket.remote_address}")
        self.clients.add(websocket)
        self.update_transcription_state()

        try:
            async for message in websocket:
                pass
        except websockets.exceptions.ConnectionClosedError: 
            # This catches the specific "browser fell asleep" scenario
            pass
        except Exception as e:
            print(f"Note: Client connection closed unexpectedly or reset ({e})")
        finally:
            print(f"Client disconnected: {websocket.remote_address}")
            self.clients.remove(websocket)
            self.update_transcription_state()

    async def broadcast_message(self, message):
        if self.clients:
            await asyncio.wait([asyncio.create_task(client.send(message)) 
                for client in self.clients])

    async def broadcast_binary(self, data):
        """Broadcasts raw binary audio to all connected websocket clients."""
        if self.clients:
            # Use gather to send to everyone at once.
            # return_exceptions=True shields against individual client failures.
            await asyncio.gather(
                *[client.send(data) for client in self.clients],
                return_exceptions=True
            )

    async def register_mDNS(self):

        # Get the first non-loopback IP for mDNS registration
        self.server_ip = None
        self.http_info = None
        self.ws_info = None

        FQDN = f"{self.config.mdns_name.lower()}.local."
        service_prefix = self.config.mdns_name.capitalize()

        if self.ip_addresses:
            # Get IP from 1st interface
            self.server_ip = self.ip_addresses[0][2]

            # Convert IP string to bytes
            ip_bytes =  socket.inet_aton(self.server_ip)

            # Register both HTTP and WebSocket services
            self.http_info = ServiceInfo(
                "_http._tcp.local.",
                "{service_prefix}._http._tcp.local.",
                addresses=[ip_bytes],
                port=8080,
                properties={'path': '/', 'version': '1.0'},
                server=FQDN
            )

            self.ws_info = ServiceInfo(
                "_ws._tcp.local.",
                "{service_prefix}._ws._tcp.local.",
                addresses=[ip_bytes],
                port=8765,
                properties={'version': '1.0'},
                server=FQDN
            )

            await self.zeroconf.async_register_service(self.http_info)
            await self.zeroconf.async_register_service(self.ws_info)
            print(f"\n✓ mDNS registered as '{FQDN}' @ {self.server_ip}")
            
            url = f"http://{FQDN.rstrip('.')}:8080"
            self.print_qr_to_terminal(url)
            self.generate_server_qr(url)

    async def start_servers(self):
        # Start WebSocket server
        self.ws_server = (
            await websockets.serve(self.websocket_handler, "0.0.0.0", 8765))
        print("\n✓ WebSocket server started on port 8765")

        # Start HTTP server
        app = web.Application()
        app.router.add_static('/static/', path='static', name='static')
        app.router.add_get('/', self.http_handler)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", 8080)
        await site.start()
        print("\n✓ HTTP server started on port 8080")

        print("\nClients can connect by visiting:")
        print(f"  http://{self.config.mdns_name}.local:8080  (recommended)")
        for iface, iface_type, ip in self.ip_addresses:
            print(f"  http://{ip}:8080")
        print("\n")

    async def stop_servers(self):
        self.ws_server.close()
        await self.ws_server.wait_closed()

        await self.runner.cleanup()


    async def unregister_mDNS(self):
            if self.server_ip and self.http_info and self.ws_info:
                await self.zeroconf.async_unregister_service(self.http_info)
                await self.zeroconf.async_unregister_service(self.ws_info)
            await self.zeroconf.async_close()

