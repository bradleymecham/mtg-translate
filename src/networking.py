import asyncio
import psutil
import ipaddress
import websockets
from aiohttp import web
import aiofiles
from zeroconf.asyncio import AsyncZeroconf
from zeroconf import ServiceInfo
import socket

class NetworkServer:
    def __init__(self, transcriber=None):
        self.clients = set()
        self.transcriber = transcriber
        self.zeroconf = AsyncZeroconf()

        self.ip_addresses = self.get_ip_addresses()
        for iface, iface_type, ip in self.ip_addresses:
            print(f"{iface} ({iface_type}): {ip}")

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

        # Start transcriber if this is the first client
        if len(self.clients) == 1 and self.transcriber:
            if self.transcriber.is_paused:
                self.transcriber.toggle_pause()

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

            # Pause transcriber if no one is left
            if len(self.clients) == 0 and self.transcriber:
                if not self.transcriber.is_paused:
                    self.transcriber.toggle_pause()

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

        if self.ip_addresses:
            # Get IP from 1st interface
            self.server_ip = self.ip_addresses[0][2]

            # Convert IP string to bytes
            ip_bytes =  socket.inet_aton(self.server_ip)

            # Register both HTTP and WebSocket services
            self.http_info = ServiceInfo(
                "_http._tcp.local.",
                "Captions._http._tcp.local.",
                addresses=[ip_bytes],
                port=8080,
                properties={'path': '/', 'version': '1.0'},
                server="captions.local."
            )

            self.ws_info = ServiceInfo(
                "_ws._tcp.local.",
                "Captions._ws._tcp.local.",
                addresses=[ip_bytes],
                port=8765,
                properties={'version': '1.0'},
                server="captions.local."
            )

            await self.zeroconf.async_register_service(self.http_info)
            await self.zeroconf.async_register_service(self.ws_info)
            print(f"\n✓ mDNS registered as 'captions.local' @ {self.server_ip}")
    
    async def start_servers(self):
        # Start WebSocket server
        self.ws_server = (
            await websockets.serve(self.websocket_handler, "0.0.0.0", 8765))
        print("\n✓ WebSocket server started on port 8765")

        # Start HTTP server
        app = web.Application()
        app.router.add_get('/', self.http_handler)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", 8080)
        await site.start()
        print("\n✓ HTTP server started on port 8080")

        print("\nClients can connect by visiting:")
        print("  http://captions.local:8080  (recommended)")
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

