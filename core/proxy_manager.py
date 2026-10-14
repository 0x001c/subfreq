import hashlib
from typing import List, Dict, Optional


class ProxyManager:
    def __init__(self, proxy_file: str):
        self.proxies = self._load_proxies(proxy_file)

    def _load_proxies(self, path: str) -> List[Dict]:
        proxies = []
        try:
            with open(path, 'r') as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        continue

                    scheme = "http"
                    body = raw
                    if "://" in raw:
                        scheme, body = raw.split("://", 1)

                    parts = body.split(":")
                    if len(parts) == 4:
                        host, port, user, password = parts
                        proxies.append({
                            "server": f"{scheme}://{host}:{port}",
                            "username": user,
                            "password": password
                        })
                    elif len(parts) == 2:
                        host, port = parts
                        proxies.append({
                            "server": f"{scheme}://{host}:{port}"
                        })
                    else:
                        # Skip malformed lines
                        continue
        except FileNotFoundError:
            print(f"Proxy file not found: {path}")
        return proxies

    def get_proxy_for_account(self, username: str) -> Optional[Dict]:
        """
        Returns a sticky proxy for the given username.
        Uses hashing to ensure the same username always gets the same proxy.
        """
        if not self.proxies:
            return None
        
        # Create a consistent hash of the username
        hash_object = hashlib.md5(username.encode())
        hash_int = int(hash_object.hexdigest(), 16)
        
        # Select proxy based on hash
        index = hash_int % len(self.proxies)
        return self.proxies[index]
